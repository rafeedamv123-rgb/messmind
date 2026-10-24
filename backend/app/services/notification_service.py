from sqlalchemy.orm import Session

from app.models.entities import ManagerNotification, MessSettings
from app.services.premeal_analytics import build_meal_premeal_forecast
from app.services.risk_service import assess_meal_risk


def maybe_create_risk_notification(db: Session, meal_session_id: int, mess_id: int) -> ManagerNotification | None:
    settings = db.query(MessSettings).filter(MessSettings.mess_id == mess_id).first()
    min_responses = settings.min_responses_for_risk_alert if settings else 5

    forecast = build_meal_premeal_forecast(db, meal_session_id)
    if forecast.total_responses < min_responses:
        return None

    risk = assess_meal_risk(db, meal_session_id)
    if risk.overall_risk.value == "low":
        return None

    existing = (
        db.query(ManagerNotification)
        .filter(
            ManagerNotification.meal_session_id == meal_session_id,
            ManagerNotification.title.like("Pre-meal risk%"),
        )
        .first()
    )
    if existing:
        return existing

    external_sent = False
    if settings and (settings.email_notifications_enabled or settings.push_notifications_enabled):
        external_sent = False  # Integration hook; no external send without provider

    note = ManagerNotification(
        mess_id=mess_id,
        meal_session_id=meal_session_id,
        title=f"Pre-meal risk warning ({risk.overall_risk.value.upper()})",
        body=(
            f"Rule-based assessment flagged {risk.overall_risk.value} risk with "
            f"{forecast.total_responses} pre-meal responses (unique authenticated respondents: "
            f"{forecast.unique_respondents if forecast.unique_respondents is not None else 'n/a'})."
        ),
        priority="high" if risk.overall_risk.value == "high" else "normal",
        external_sent=external_sent,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note
