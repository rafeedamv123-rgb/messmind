import numpy as np
from sqlalchemy.orm import Session

from app.models.entities import MealSession, MealWasteRecord, WasteAnomalyFlag


def detect_waste_anomaly(db: Session, meal_session_id: int, z_threshold: float = 2.0) -> WasteAnomalyFlag | None:
    session = db.get(MealSession, meal_session_id)
    if session is None:
        return None
    waste = (
        db.query(MealWasteRecord)
        .filter(MealWasteRecord.meal_session_id == meal_session_id)
        .first()
    )
    if waste is None:
        return None

    history = (
        db.query(MealWasteRecord)
        .join(MealSession, MealSession.id == MealWasteRecord.meal_session_id)
        .filter(
            MealSession.mess_id == session.mess_id,
            MealSession.meal_type == session.meal_type,
            MealSession.meal_date < session.meal_date,
        )
        .all()
    )
    if len(history) < 5:
        expected = waste.total_waste_kg
        z = 0.0
        is_anomaly = False
    else:
        values = np.array([h.total_waste_kg for h in history], dtype=float)
        expected = float(np.mean(values))
        std = float(np.std(values)) or 1.0
        z = (waste.total_waste_kg - expected) / std
        is_anomaly = abs(z) >= z_threshold

    flag = WasteAnomalyFlag(
        meal_session_id=meal_session_id,
        expected_waste_kg=expected,
        actual_waste_kg=waste.total_waste_kg,
        z_score=float(z),
        is_anomaly=is_anomaly,
    )
    db.add(flag)
    db.commit()
    db.refresh(flag)
    return flag
