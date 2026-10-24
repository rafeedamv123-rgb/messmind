from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session, joinedload

from app.models.entities import (
    ChangeKind,
    MealSession,
    MealSessionStatus,
    MealType,
    MenuChangeLog,
    MenuItem,
    MenuItemVersion,
    PreMealFeedback,
    WeeklyMenuPlan,
    WeeklyPlanStatus,
)
from app.services.meal_timing import get_mess_settings, is_meal_started


def _meal_types() -> list[MealType]:
    return [MealType.breakfast, MealType.lunch, MealType.dinner]


def get_or_create_weekly_plan(
    db: Session, mess_id: int, week_start: date
) -> WeeklyMenuPlan:
    plan = (
        db.query(WeeklyMenuPlan)
        .filter(
            WeeklyMenuPlan.mess_id == mess_id,
            WeeklyMenuPlan.week_start_date == week_start,
        )
        .first()
    )
    if plan:
        return plan
    plan = WeeklyMenuPlan(mess_id=mess_id, week_start_date=week_start)
    db.add(plan)
    db.flush()
    for offset in range(7):
        day = week_start + timedelta(days=offset)
        for meal_type in _meal_types():
            session = MealSession(
                mess_id=mess_id,
                weekly_plan_id=plan.id,
                meal_date=day,
                meal_type=meal_type,
                status=MealSessionStatus.draft,
            )
            db.add(session)
    db.commit()
    db.refresh(plan)
    return plan


def _ensure_menu_version(
    db: Session, item: MenuItem, dish_name: str, notes: str | None
) -> MenuItemVersion:
    current = (
        db.query(MenuItemVersion)
        .filter(
            MenuItemVersion.menu_item_id == item.id,
            MenuItemVersion.is_current.is_(True),
        )
        .first()
    )
    if current and current.dish_name == dish_name and (current.notes or "") == (notes or ""):
        return current
    if current:
        current.is_current = False
        current.superseded_at = datetime.utcnow()
        version_number = current.version_number + 1
        _mark_premeal_stale_for_item(db, item.id)
    else:
        version_number = 1
    version = MenuItemVersion(
        menu_item_id=item.id,
        version_number=version_number,
        dish_name=dish_name,
        notes=notes,
        is_current=True,
    )
    db.add(version)
    db.flush()
    return version


def _mark_premeal_stale_for_item(db: Session, menu_item_id: int) -> None:
    version_ids = [
        v.id
        for v in db.query(MenuItemVersion)
        .filter(MenuItemVersion.menu_item_id == menu_item_id)
        .all()
    ]
    if not version_ids:
        return
    (
        db.query(PreMealFeedback)
        .filter(PreMealFeedback.menu_item_version_id.in_(version_ids))
        .update({PreMealFeedback.is_stale_for_old_version: True}, synchronize_session=False)
    )


def add_dish(
    db: Session,
    meal_session_id: int,
    dish_name: str,
    notes: str | None,
    manager_id: int,
    exceptional: bool = False,
) -> MenuItem:
    session = db.get(MealSession, meal_session_id)
    if session is None:
        raise ValueError("Meal session not found")
    settings = get_mess_settings(db, session.mess_id)
    started = is_meal_started(session.meal_date, session.meal_type, settings)
    if started and not exceptional:
        raise PermissionError("Meal has started; use exceptional correction")
    if started and exceptional and session.status != MealSessionStatus.locked:
        session.status = MealSessionStatus.locked

    sort_order = (
        db.query(MenuItem)
        .filter(MenuItem.meal_session_id == meal_session_id, MenuItem.is_removed.is_(False))
        .count()
    )
    item = MenuItem(meal_session_id=meal_session_id, sort_order=sort_order)
    db.add(item)
    db.flush()
    _ensure_menu_version(db, item, dish_name, notes)
    _bump_session_version(db, session, manager_id, exceptional, f"Added dish: {dish_name}", item.id)
    db.commit()
    db.refresh(item)
    return item


def update_dish(
    db: Session,
    menu_item_id: int,
    dish_name: str,
    notes: str | None,
    manager_id: int,
    exceptional: bool = False,
) -> MenuItemVersion:
    item = db.get(MenuItem, menu_item_id)
    if item is None or item.is_removed:
        raise ValueError("Menu item not found")
    session = db.get(MealSession, item.meal_session_id)
    assert session is not None
    settings = get_mess_settings(db, session.mess_id)
    if is_meal_started(session.meal_date, session.meal_type, settings) and not exceptional:
        raise PermissionError("Meal has started; use exceptional correction")

    version = _ensure_menu_version(db, item, dish_name, notes)
    _bump_session_version(
        db,
        session,
        manager_id,
        exceptional,
        f"Updated dish to: {dish_name}",
        item.id,
    )
    db.commit()
    return version


def replace_dish(
    db: Session,
    old_menu_item_id: int,
    new_dish_name: str,
    notes: str | None,
    manager_id: int,
    exceptional: bool = False,
) -> MenuItem:
    old = db.get(MenuItem, old_menu_item_id)
    if old is None:
        raise ValueError("Menu item not found")
    session = db.get(MealSession, old.meal_session_id)
    assert session is not None
    old.is_removed = True
    new_item = MenuItem(
        meal_session_id=session.id,
        sort_order=old.sort_order,
        replaced_menu_item_id=old.id,
    )
    db.add(new_item)
    db.flush()
    _ensure_menu_version(db, new_item, new_dish_name, notes)
    _mark_premeal_stale_for_item(db, old.id)
    _bump_session_version(
        db,
        session,
        manager_id,
        exceptional,
        f"Replaced dish with: {new_dish_name}",
        new_item.id,
    )
    db.commit()
    db.refresh(new_item)
    return new_item


def remove_dish(
    db: Session, menu_item_id: int, manager_id: int, exceptional: bool = False
) -> None:
    item = db.get(MenuItem, menu_item_id)
    if item is None:
        raise ValueError("Menu item not found")
    session = db.get(MealSession, item.meal_session_id)
    assert session is not None
    settings = get_mess_settings(db, session.mess_id)
    if is_meal_started(session.meal_date, session.meal_type, settings) and not exceptional:
        raise PermissionError("Meal has started; use exceptional correction")
    item.is_removed = True
    _mark_premeal_stale_for_item(db, item.id)
    _bump_session_version(
        db, session, manager_id, exceptional, "Removed dish", item.id
    )
    db.commit()


def _bump_session_version(
    db: Session,
    session: MealSession,
    manager_id: int,
    exceptional: bool,
    summary: str,
    menu_item_id: int | None,
) -> None:
    if session.status in (MealSessionStatus.published, MealSessionStatus.updated):
        session.status = MealSessionStatus.updated
        session.menu_version += 1
        plan = db.get(WeeklyMenuPlan, session.weekly_plan_id) if session.weekly_plan_id else None
        if plan and plan.status == WeeklyPlanStatus.published:
            plan.status = WeeklyPlanStatus.updated
    db.add(
        MenuChangeLog(
            meal_session_id=session.id,
            menu_item_id=menu_item_id,
            change_kind=(
                ChangeKind.exceptional_correction
                if exceptional
                else ChangeKind.pre_meal_edit
            ),
            summary=summary,
            manager_id=manager_id,
        )
    )


def publish_weekly_plan(db: Session, plan_id: int) -> WeeklyMenuPlan:
    plan = (
        db.query(WeeklyMenuPlan)
        .options(joinedload(WeeklyMenuPlan.meal_sessions))
        .filter(WeeklyMenuPlan.id == plan_id)
        .first()
    )
    if plan is None:
        raise ValueError("Weekly plan not found")
    now = datetime.utcnow()
    plan.status = WeeklyPlanStatus.published
    plan.published_at = now
    for session in plan.meal_sessions:
        if session.status == MealSessionStatus.draft:
            session.status = MealSessionStatus.published
            session.published_at = now
    db.commit()
    db.refresh(plan)
    return plan


def student_visible_sessions(db: Session, mess_id: int, week_start: date) -> list[MealSession]:
    plan = get_or_create_weekly_plan(db, mess_id, week_start)
    if plan.status == WeeklyPlanStatus.draft:
        return []
    end = week_start + timedelta(days=6)
    return (
        db.query(MealSession)
        .filter(
            MealSession.mess_id == mess_id,
            MealSession.meal_date >= week_start,
            MealSession.meal_date <= end,
            MealSession.status.in_(
                [
                    MealSessionStatus.published,
                    MealSessionStatus.updated,
                    MealSessionStatus.locked,
                    MealSessionStatus.completed,
                ]
            ),
        )
        .order_by(MealSession.meal_date, MealSession.meal_type)
        .all()
    )


def current_dish_versions(db: Session, meal_session_id: int) -> list[MenuItemVersion]:
    items = (
        db.query(MenuItem)
        .filter(MenuItem.meal_session_id == meal_session_id, MenuItem.is_removed.is_(False))
        .order_by(MenuItem.sort_order)
        .all()
    )
    versions: list[MenuItemVersion] = []
    for item in items:
        version = (
            db.query(MenuItemVersion)
            .filter(
                MenuItemVersion.menu_item_id == item.id,
                MenuItemVersion.is_current.is_(True),
            )
            .first()
        )
        if version:
            versions.append(version)
    return versions
