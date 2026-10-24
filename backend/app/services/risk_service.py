from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.entities import MealSession, PostMealFeedback, PreMealFeedback, RiskLevel
from app.services.menu_service import current_dish_versions
from app.services.premeal_analytics import (
    LOW_RATING_MAX,
    SKIP_LIKELIHOODS,
    build_meal_premeal_forecast,
    dish_feedback_for_version,
)


@dataclass
class DishRiskAssessment:
    menu_item_id: int
    dish_name: str
    risk_level: RiskLevel
    triggers: list[str]


@dataclass
class MealRiskAssessment:
    meal_session_id: int
    overall_risk: RiskLevel
    dish_risks: list[DishRiskAssessment]
    methodology: str


def _historical_low_rating_streak(db: Session, mess_id: int, dish_name: str, meal_type) -> int:
    sessions = (
        db.query(MealSession)
        .filter(MealSession.mess_id == mess_id, MealSession.meal_type == meal_type)
        .order_by(MealSession.meal_date.desc())
        .limit(8)
        .all()
    )
    streak = 0
    for session in sessions:
        found = False
        for version in current_dish_versions(db, session.id):
            if version.dish_name.lower() != dish_name.lower():
                continue
            feedback = dish_feedback_for_version(db, version.id)
            if not feedback:
                continue
            avg = sum(f.preference_rating for f in feedback) / len(feedback)
            if avg <= 2.5:
                streak += 1
                found = True
            break
        if not found:
            break
    return streak


def assess_meal_risk(db: Session, meal_session_id: int) -> MealRiskAssessment:
    forecast = build_meal_premeal_forecast(db, meal_session_id)
    session = db.get(MealSession, meal_session_id)
    assert session is not None

    dish_risks: list[DishRiskAssessment] = []
    max_level = RiskLevel.low

    for row in forecast.dishes:
        triggers: list[str] = []
        score = 0
        if row.response_count >= 3 and row.average_rating is not None and row.average_rating <= 2.2:
            triggers.append(
                f"Low average pre-meal preference rating ({row.average_rating:.1f}/5, n={row.response_count})"
            )
            score += 2
        if row.skip_pct_of_respondents is not None and row.skip_pct_of_respondents >= 40:
            triggers.append(
                f"High percentage of respondents expecting to skip ({row.skip_pct_of_respondents:.1f}% of {row.response_count} responses)"
            )
            score += 2
        if row.low_rating_pct_of_respondents is not None and row.low_rating_pct_of_respondents >= 50:
            triggers.append(
                f"High percentage of respondents with low preference ratings 1-2 ({row.low_rating_pct_of_respondents:.1f}% of {row.response_count} responses)"
            )
            score += 1

        streak = _historical_low_rating_streak(
            db, session.mess_id, row.dish_name, session.meal_type
        )
        if streak >= 2:
            triggers.append(
                f"Repeated low pre-meal ratings for this dish in {streak} recent comparable meals"
            )
            score += 1

        post_negative = (
            db.query(PostMealFeedback)
            .filter(
                PostMealFeedback.menu_item_version_id == row.menu_item_version_id,
                PostMealFeedback.taste_rating <= LOW_RATING_MAX,
            )
            .count()
        )
        if post_negative >= 3:
            triggers.append(
                f"Historical post-meal dissatisfaction on this menu version ({post_negative} low ratings)"
            )
            score += 1

        if score >= 4:
            level = RiskLevel.high
        elif score >= 2:
            level = RiskLevel.medium
        else:
            level = RiskLevel.low

        if level == RiskLevel.high:
            max_level = RiskLevel.high
        elif level == RiskLevel.medium and max_level != RiskLevel.high:
            max_level = RiskLevel.medium

        if triggers:
            dish_risks.append(
                DishRiskAssessment(
                    menu_item_id=row.menu_item_id,
                    dish_name=row.dish_name,
                    risk_level=level,
                    triggers=triggers,
                )
            )

    return MealRiskAssessment(
        meal_session_id=meal_session_id,
        overall_risk=max_level,
        dish_risks=sorted(
            dish_risks,
            key=lambda d: {"high": 3, "medium": 2, "low": 1}[d.risk_level.value],
            reverse=True,
        ),
        methodology=(
            "Rule-based risk assessment (Stage 1). Transparent thresholds on pre-meal ratings, "
            "skip intentions, and historical patterns. Not a trained ML probability."
        ),
    )


def recommendation_text_for_dish(dish_name: str, triggers: list[str]) -> str:
    suggestions = []
    joined = " ".join(triggers).lower()
    if "spicy" in joined or "bland" in joined or "taste" in joined:
        suggestions.append("Review the recipe or spice level.")
    if "cooking quality" in joined:
        suggestions.append("Investigate repeated complaints about cooking quality.")
    if "skip" in joined or "low average" in joined:
        suggestions.append("Consider a suitable alternative dish and compare similar dishes with better historical ratings.")
    suggestions.append(
        "Monitor actual waste after the meal to check whether the predicted problem occurred."
    )
    return f"For {dish_name}: " + " ".join(suggestions)
