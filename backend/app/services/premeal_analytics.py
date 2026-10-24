import json
from collections import Counter
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import EatLikelihood, MealSession, MenuItemVersion, PreMealFeedback
from app.services.menu_service import current_dish_versions

LOW_RATING_MAX = 2
SKIP_LIKELIHOODS = {EatLikelihood.probably_skip, EatLikelihood.definitely_skip}


@dataclass
class DishForecastRow:
    menu_item_version_id: int
    menu_item_id: int
    dish_name: str
    response_count: int
    average_rating: float | None
    low_rating_count: int
    low_rating_pct_of_respondents: float | None
    skip_count: int
    skip_pct_of_respondents: float | None
    top_dissatisfaction_reasons: list[tuple[str, int]]


@dataclass
class MealPreMealForecast:
    meal_session_id: int
    unique_respondents: int | None
    total_responses: int
    has_authenticated_respondents: bool
    reliable_forecast: bool
    menu_version: int
    change_count: int
    dishes: list[DishForecastRow]
    insufficient_data_message: str | None


def _parse_reasons(raw: str) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x) for x in data]
    except json.JSONDecodeError:
        pass
    return [p.strip() for p in raw.split(",") if p.strip()]


def dish_feedback_for_version(
    db: Session, version_id: int, include_stale: bool = False
) -> list[PreMealFeedback]:
    q = db.query(PreMealFeedback).filter(PreMealFeedback.menu_item_version_id == version_id)
    if not include_stale:
        q = q.filter(PreMealFeedback.is_stale_for_old_version.is_(False))
    return q.all()


def build_meal_premeal_forecast(db: Session, meal_session_id: int) -> MealPreMealForecast:
    from app.models.entities import MenuChangeLog

    settings = get_settings()
    session = db.get(MealSession, meal_session_id)
    if session is None:
        raise ValueError("Meal session not found")

    versions = current_dish_versions(db, meal_session_id)
    dish_rows: list[DishForecastRow] = []
    all_feedback: list[PreMealFeedback] = []

    for version in versions:
        feedback = dish_feedback_for_version(db, version.id)
        all_feedback.extend(feedback)
        count = len(feedback)
        if count == 0:
            dish_rows.append(
                DishForecastRow(
                    menu_item_version_id=version.id,
                    menu_item_id=version.menu_item_id,
                    dish_name=version.dish_name,
                    response_count=0,
                    average_rating=None,
                    low_rating_count=0,
                    low_rating_pct_of_respondents=None,
                    skip_count=0,
                    skip_pct_of_respondents=None,
                    top_dissatisfaction_reasons=[],
                )
            )
            continue
        ratings = [f.preference_rating for f in feedback]
        low_count = sum(1 for r in ratings if r <= LOW_RATING_MAX)
        skip_count = sum(1 for f in feedback if f.eat_likelihood in SKIP_LIKELIHOODS)
        reason_counter: Counter[str] = Counter()
        for f in feedback:
            reason_counter.update(_parse_reasons(f.dissatisfaction_reasons))
        dish_rows.append(
            DishForecastRow(
                menu_item_version_id=version.id,
                menu_item_id=version.menu_item_id,
                dish_name=version.dish_name,
                response_count=count,
                average_rating=sum(ratings) / count,
                low_rating_count=low_count,
                low_rating_pct_of_respondents=100.0 * low_count / count,
                skip_count=skip_count,
                skip_pct_of_respondents=100.0 * skip_count / count,
                top_dissatisfaction_reasons=reason_counter.most_common(5),
            )
        )

    authenticated_ids = {
        f.student_id for f in all_feedback if f.student_id is not None and not f.is_anonymous
    }
    unique_respondents = len(authenticated_ids) if authenticated_ids else None
    total_responses = len(all_feedback)
    reliable = total_responses >= settings.min_responses_reliable_forecast

    changes = (
        db.query(MenuChangeLog).filter(MenuChangeLog.meal_session_id == meal_session_id).count()
    )

    insufficient = None
    if total_responses == 0:
        insufficient = "No pre-meal responses yet for this meal."

    return MealPreMealForecast(
        meal_session_id=meal_session_id,
        unique_respondents=unique_respondents,
        total_responses=total_responses,
        has_authenticated_respondents=bool(authenticated_ids),
        reliable_forecast=reliable,
        menu_version=session.menu_version,
        change_count=changes,
        dishes=sorted(
            dish_rows,
            key=lambda d: (d.low_rating_pct_of_respondents or 0, d.skip_pct_of_respondents or 0),
            reverse=True,
        ),
        insufficient_data_message=insufficient,
    )


def pct_of_respondents(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return 100.0 * numerator / denominator


def historical_dish_comparison(
    db: Session,
    mess_id: int,
    meal_type,
    dish_name: str,
    limit: int = 10,
) -> dict:
    """Aggregate post-meal and pre-meal history for the same dish name."""
    from app.models.entities import MealSession, MealType, PostMealFeedback

    sessions = (
        db.query(MealSession)
        .filter(MealSession.mess_id == mess_id, MealSession.meal_type == meal_type)
        .order_by(MealSession.meal_date.desc())
        .limit(limit * 3)
        .all()
    )
    pre_ratings: list[float] = []
    post_ratings: list[float] = []
    for session in sessions:
        for version in current_dish_versions(db, session.id):
            if version.dish_name.lower() != dish_name.lower():
                continue
            pre = dish_feedback_for_version(db, version.id)
            if pre:
                pre_ratings.extend(f.preference_rating for f in pre)
            post = (
                db.query(PostMealFeedback)
                .filter(PostMealFeedback.menu_item_version_id == version.id)
                .all()
            )
            if post:
                post_ratings.extend(p.taste_rating for p in post)
            if len(pre_ratings) >= limit * 5:
                break
    return {
        "dish_name": dish_name,
        "meal_type": meal_type.value if isinstance(meal_type, MealType) else str(meal_type),
        "historical_pre_meal_avg": (
            sum(pre_ratings) / len(pre_ratings) if pre_ratings else None
        ),
        "historical_pre_meal_sample": len(pre_ratings),
        "historical_post_meal_avg": (
            sum(post_ratings) / len(post_ratings) if post_ratings else None
        ),
        "historical_post_meal_sample": len(post_ratings),
    }
