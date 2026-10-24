import json
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.entities import (
    DailyReportSnapshot,
    MealSession,
    MealWasteRecord,
    WeeklyReportSnapshot,
)
from app.services.anomaly_service import detect_waste_anomaly
from app.services.premeal_analytics import build_meal_premeal_forecast
from app.services.waste_forecast_service import predict_meal_waste


def build_daily_report(db: Session, mess_id: int, report_date: date) -> dict:
    sessions = (
        db.query(MealSession)
        .filter(MealSession.mess_id == mess_id, MealSession.meal_date == report_date)
        .all()
    )
    meals = []
    total_waste = 0.0
    for session in sessions:
        waste = (
            db.query(MealWasteRecord)
            .filter(MealWasteRecord.meal_session_id == session.id)
            .first()
        )
        forecast = build_meal_premeal_forecast(db, session.id)
        prediction = predict_meal_waste(db, session.id)
        anomaly = None
        if waste:
            total_waste += waste.total_waste_kg
            flag = detect_waste_anomaly(db, session.id)
            if flag:
                anomaly = {
                    "is_anomaly": flag.is_anomaly,
                    "z_score": flag.z_score,
                    "expected_waste_kg": flag.expected_waste_kg,
                }
        meals.append(
            {
                "meal_session_id": session.id,
                "meal_type": session.meal_type.value,
                "status": session.status.value,
                "pre_meal_responses": forecast.total_responses,
                "predicted_waste_kg": prediction.predicted_waste_kg,
                "actual_waste_kg": waste.total_waste_kg if waste else None,
                "anomaly": anomaly,
            }
        )
    payload = {
        "mess_id": mess_id,
        "report_date": report_date.isoformat(),
        "meals": meals,
        "total_waste_kg": total_waste,
    }
    snap = (
        db.query(DailyReportSnapshot)
        .filter(
            DailyReportSnapshot.mess_id == mess_id,
            DailyReportSnapshot.report_date == report_date,
        )
        .first()
    )
    if snap:
        snap.payload_json = json.dumps(payload)
    else:
        db.add(
            DailyReportSnapshot(
                mess_id=mess_id, report_date=report_date, payload_json=json.dumps(payload)
            )
        )
    db.commit()
    return payload


def build_weekly_report(db: Session, mess_id: int, week_start: date) -> dict:
    end = week_start + timedelta(days=6)
    days = []
    cursor = week_start
    total_waste = 0.0
    while cursor <= end:
        daily = build_daily_report(db, mess_id, cursor)
        total_waste += daily["total_waste_kg"]
        days.append(daily)
        cursor += timedelta(days=1)
    payload = {
        "mess_id": mess_id,
        "week_start_date": week_start.isoformat(),
        "days": days,
        "total_waste_kg": total_waste,
    }
    snap = (
        db.query(WeeklyReportSnapshot)
        .filter(
            WeeklyReportSnapshot.mess_id == mess_id,
            WeeklyReportSnapshot.week_start_date == week_start,
        )
        .first()
    )
    if snap:
        snap.payload_json = json.dumps(payload)
    else:
        db.add(
            WeeklyReportSnapshot(
                mess_id=mess_id,
                week_start_date=week_start,
                payload_json=json.dumps(payload),
            )
        )
    db.commit()
    return payload
