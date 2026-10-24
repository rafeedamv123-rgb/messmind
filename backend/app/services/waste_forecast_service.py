import json
from dataclasses import dataclass

import numpy as np
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import MealSession, MealWasteRecord, WasteForecast
from app.services.premeal_analytics import build_meal_premeal_forecast


@dataclass
class WastePredictionResult:
    predicted_waste_kg: float | None
    interval_low: float | None
    interval_high: float | None
    model_type: str
    insufficient_data: bool
    message: str
    feature_summary: dict


def _comparable_meals(db: Session, session: MealSession) -> list[tuple[MealSession, float]]:
    rows = (
        db.query(MealSession, MealWasteRecord)
        .join(MealWasteRecord, MealWasteRecord.meal_session_id == MealSession.id)
        .filter(
            MealSession.mess_id == session.mess_id,
            MealSession.meal_type == session.meal_type,
            MealSession.meal_date < session.meal_date,
        )
        .order_by(MealSession.meal_date.desc())
        .limit(60)
        .all()
    )
    return [(s, w.total_waste_kg) for s, w in rows]


def predict_meal_waste(db: Session, meal_session_id: int) -> WastePredictionResult:
    settings = get_settings()
    session = db.get(MealSession, meal_session_id)
    if session is None:
        raise ValueError("Meal session not found")

    forecast = build_meal_premeal_forecast(db, meal_session_id)
    comparables = _comparable_meals(db, session)

    avg_low_rating_pct = _avg_metric(
        forecast.dishes, lambda d: d.low_rating_pct_of_respondents or 0.0
    )
    avg_skip_pct = _avg_metric(forecast.dishes, lambda d: d.skip_pct_of_respondents or 0.0)

    feature_summary = {
        "mess_id": session.mess_id,
        "meal_type": session.meal_type.value,
        "day_of_week": session.meal_date.weekday(),
        "pre_meal_response_count": forecast.total_responses,
        "avg_low_rating_pct_of_respondents": avg_low_rating_pct,
        "avg_skip_pct_of_respondents": avg_skip_pct,
        "historical_meals_available": len(comparables),
    }

    if len(comparables) < 5:
        return WastePredictionResult(
            predicted_waste_kg=None,
            interval_low=None,
            interval_high=None,
            model_type="rule_baseline",
            insufficient_data=True,
            message="Not enough historical data to estimate waste in kg",
            feature_summary=feature_summary,
        )

    wastes = np.array([w for _, w in comparables], dtype=float)
    baseline_mean = float(np.mean(wastes))
    baseline_std = float(np.std(wastes)) if len(wastes) > 1 else baseline_mean * 0.15

    dissatisfaction_signal = (avg_low_rating_pct + avg_skip_pct) / 200.0
    adjusted = baseline_mean * (1.0 + 0.35 * dissatisfaction_signal)

    model_type = "interpretable_baseline"
    if len(comparables) >= settings.min_historical_meals_for_ml:
        try:
            from sklearn.ensemble import RandomForestRegressor

            X, y = _build_ml_matrix(db, comparables)
            if len(y) >= settings.min_historical_meals_for_ml:
                model = RandomForestRegressor(n_estimators=100, random_state=42)
                model.fit(X, y)
                x_target = np.array(
                    [
                        [
                            session.meal_date.weekday(),
                            avg_low_rating_pct,
                            avg_skip_pct,
                            forecast.total_responses,
                        ]
                    ]
                )
                adjusted = float(model.predict(x_target)[0])
                model_type = "random_forest_regression"
        except Exception:
            pass

    interval_low = max(0.0, adjusted - 1.28 * baseline_std)
    interval_high = adjusted + 1.28 * baseline_std

    return WastePredictionResult(
        predicted_waste_kg=round(adjusted, 2),
        interval_low=round(interval_low, 2),
        interval_high=round(interval_high, 2),
        model_type=model_type,
        insufficient_data=False,
        message="Meal-level waste estimate using historical comparable meals and current pre-meal signals.",
        feature_summary=feature_summary,
    )


def _avg_metric(dishes, fn) -> float:
    if not dishes:
        return 0.0
    return sum(fn(d) for d in dishes) / len(dishes)


def _build_ml_matrix(db: Session, comparables: list[tuple[MealSession, float]]):
    X_rows = []
    y_rows = []
    for sess, waste in comparables:
        fc = build_meal_premeal_forecast(db, sess.id)
        X_rows.append(
            [
                sess.meal_date.weekday(),
                _avg_metric(fc.dishes, lambda d: d.low_rating_pct_of_respondents or 0.0),
                _avg_metric(fc.dishes, lambda d: d.skip_pct_of_respondents or 0.0),
                fc.total_responses,
            ]
        )
        y_rows.append(waste)
    return np.array(X_rows), np.array(y_rows)


def persist_forecast(db: Session, meal_session_id: int, result: WastePredictionResult) -> WasteForecast:
    row = WasteForecast(
        meal_session_id=meal_session_id,
        predicted_waste_kg=result.predicted_waste_kg,
        prediction_interval_low=result.interval_low,
        prediction_interval_high=result.interval_high,
        model_type=result.model_type,
        feature_summary=json.dumps(result.feature_summary),
        insufficient_data=result.insufficient_data,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@dataclass
class WasteReductionEstimate:
    current_menu_predicted_kg: float | None
    alternative_predicted_kg: float | None
    estimated_difference_kg: float | None
    interval_low: float | None
    interval_high: float | None
    assumptions: list[str]
    insufficient_data: bool
    label: str = "estimated potential waste reduction"


def estimate_potential_waste_reduction(
    db: Session,
    meal_session_id: int,
    alternative_low_rating_pct: float,
    alternative_skip_pct: float,
) -> WasteReductionEstimate:
    current = predict_meal_waste(db, meal_session_id)
    assumptions = [
        "Estimates apply to total meal waste in kg, not per-dish allocation.",
        "Skip intentions are not treated as measured waste events.",
        "Alternative scenario uses manager-supplied expected satisfaction metrics.",
    ]
    if current.insufficient_data or current.predicted_waste_kg is None:
        return WasteReductionEstimate(
            current_menu_predicted_kg=None,
            alternative_predicted_kg=None,
            estimated_difference_kg=None,
            interval_low=None,
            interval_high=None,
            assumptions=assumptions,
            insufficient_data=True,
        )

    session = db.get(MealSession, meal_session_id)
    assert session is not None
    comparables = _comparable_meals(db, session)
    wastes = np.array([w for _, w in comparables], dtype=float)
    baseline_mean = float(np.mean(wastes))
    baseline_std = float(np.std(wastes)) if len(wastes) > 1 else baseline_mean * 0.15

    alt_signal = (alternative_low_rating_pct + alternative_skip_pct) / 200.0
    alt_pred = baseline_mean * (1.0 + 0.35 * alt_signal)
    diff = current.predicted_waste_kg - alt_pred

    return WasteReductionEstimate(
        current_menu_predicted_kg=current.predicted_waste_kg,
        alternative_predicted_kg=round(alt_pred, 2),
        estimated_difference_kg=round(diff, 2),
        interval_low=round(diff - baseline_std, 2),
        interval_high=round(diff + baseline_std, 2),
        assumptions=assumptions + [
            "Difference is an estimated potential waste reduction, not confirmed savings.",
        ],
        insufficient_data=False,
    )
