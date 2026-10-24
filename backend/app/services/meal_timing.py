from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.config import DISPLAY_TZ
from app.models.entities import MealSession, MealType, MessSettings

MEAL_START_ATTR = {
    MealType.breakfast: "breakfast_start",
    MealType.lunch: "lunch_start",
    MealType.dinner: "dinner_start",
}


def meal_start_datetime(
    meal_date: date, meal_type: MealType, settings: MessSettings
) -> datetime:
    start_time: time = getattr(settings, MEAL_START_ATTR[meal_type])
    local = datetime.combine(meal_date, start_time, tzinfo=DISPLAY_TZ)
    return local


def pre_meal_cutoff_datetime(
    meal_date: date, meal_type: MealType, settings: MessSettings
) -> datetime:
    start = meal_start_datetime(meal_date, meal_type, settings)
    return start - timedelta(minutes=settings.pre_meal_cutoff_minutes_before)


def now_local() -> datetime:
    return datetime.now(DISPLAY_TZ)


def is_meal_started(
    meal_date: date, meal_type: MealType, settings: MessSettings, at: datetime | None = None
) -> bool:
    at = at or now_local()
    return at >= meal_start_datetime(meal_date, meal_type, settings)


def is_pre_meal_open(
    meal_date: date, meal_type: MealType, settings: MessSettings, at: datetime | None = None
) -> bool:
    at = at or now_local()
    if is_meal_started(meal_date, meal_type, settings, at):
        return False
    return at < pre_meal_cutoff_datetime(meal_date, meal_type, settings)


def get_mess_settings(db: Session, mess_id: int) -> MessSettings:
    settings = db.query(MessSettings).filter(MessSettings.mess_id == mess_id).first()
    if settings is None:
        settings = MessSettings(mess_id=mess_id)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def auto_lock_due_meals(db: Session) -> int:
    """Lock published/updated meal sessions whose start time has passed."""
    from app.models.entities import MealSessionStatus

    locked = 0
    sessions = (
        db.query(MealSession)
        .filter(
            MealSession.status.in_(
                [MealSessionStatus.published, MealSessionStatus.updated]
            )
        )
        .all()
    )
    for session in sessions:
        settings = get_mess_settings(db, session.mess_id)
        if is_meal_started(session.meal_date, session.meal_type, settings):
            session.status = MealSessionStatus.locked
            session.locked_at = datetime.utcnow()
            locked += 1
    if locked:
        db.commit()
    return locked
