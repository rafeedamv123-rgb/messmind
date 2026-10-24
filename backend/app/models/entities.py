import enum
from datetime import date, datetime, time
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class UserRole(str, enum.Enum):
    student = "student"
    manager = "manager"


class MealType(str, enum.Enum):
    breakfast = "breakfast"
    lunch = "lunch"
    dinner = "dinner"


class WeeklyPlanStatus(str, enum.Enum):
    draft = "draft"
    published = "published"
    updated = "updated"


class MealSessionStatus(str, enum.Enum):
    draft = "draft"
    published = "published"
    updated = "updated"
    locked = "locked"
    completed = "completed"


class EatLikelihood(str, enum.Enum):
    definitely_eat = "definitely_eat"
    probably_eat = "probably_eat"
    not_sure = "not_sure"
    probably_skip = "probably_skip"
    definitely_skip = "definitely_skip"


class ChangeKind(str, enum.Enum):
    pre_meal_edit = "pre_meal_edit"
    exceptional_correction = "exceptional_correction"


class RiskLevel(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class RecommendationStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"
    deferred = "deferred"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole))
    mess_id: Mapped[Optional[int]] = mapped_column(ForeignKey("mess.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    mess: Mapped[Optional["Mess"]] = relationship(back_populates="users")


class Mess(Base):
    __tablename__ = "mess"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    users: Mapped[list["User"]] = relationship(back_populates="mess")
    settings: Mapped[Optional["MessSettings"]] = relationship(
        back_populates="mess", uselist=False
    )
    weekly_plans: Mapped[list["WeeklyMenuPlan"]] = relationship(back_populates="mess")


class MessSettings(Base):
    __tablename__ = "mess_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mess_id: Mapped[int] = mapped_column(ForeignKey("mess.id"), unique=True)
    breakfast_start: Mapped[time] = mapped_column(Time, default=time(7, 0))
    lunch_start: Mapped[time] = mapped_column(Time, default=time(12, 0))
    dinner_start: Mapped[time] = mapped_column(Time, default=time(19, 0))
    pre_meal_cutoff_minutes_before: Mapped[int] = mapped_column(Integer, default=30)
    min_responses_for_risk_alert: Mapped[int] = mapped_column(Integer, default=5)
    email_notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    push_notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    mess: Mapped["Mess"] = relationship(back_populates="settings")


class WeeklyMenuPlan(Base):
    __tablename__ = "weekly_menu_plans"
    __table_args__ = (UniqueConstraint("mess_id", "week_start_date", name="uq_mess_week"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mess_id: Mapped[int] = mapped_column(ForeignKey("mess.id"), index=True)
    week_start_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[WeeklyPlanStatus] = mapped_column(
        Enum(WeeklyPlanStatus), default=WeeklyPlanStatus.draft
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    mess: Mapped["Mess"] = relationship(back_populates="weekly_plans")
    meal_sessions: Mapped[list["MealSession"]] = relationship(back_populates="weekly_plan")


class MealSession(Base):
    __tablename__ = "meal_sessions"
    __table_args__ = (
        UniqueConstraint("mess_id", "meal_date", "meal_type", name="uq_meal_session"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mess_id: Mapped[int] = mapped_column(ForeignKey("mess.id"), index=True)
    weekly_plan_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("weekly_menu_plans.id"), nullable=True
    )
    meal_date: Mapped[date] = mapped_column(Date, index=True)
    meal_type: Mapped[MealType] = mapped_column(Enum(MealType))
    status: Mapped[MealSessionStatus] = mapped_column(
        Enum(MealSessionStatus), default=MealSessionStatus.draft
    )
    menu_version: Mapped[int] = mapped_column(Integer, default=1)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    weekly_plan: Mapped[Optional["WeeklyMenuPlan"]] = relationship(
        back_populates="meal_sessions"
    )
    menu_items: Mapped[list["MenuItem"]] = relationship(back_populates="meal_session")
    waste_record: Mapped[Optional["MealWasteRecord"]] = relationship(
        back_populates="meal_session", uselist=False
    )


class MenuItem(Base):
    __tablename__ = "menu_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meal_session_id: Mapped[int] = mapped_column(ForeignKey("meal_sessions.id"), index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    replaced_menu_item_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("menu_items.id"), nullable=True
    )
    is_removed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    meal_session: Mapped["MealSession"] = relationship(back_populates="menu_items")
    versions: Mapped[list["MenuItemVersion"]] = relationship(back_populates="menu_item")
    replaced_item: Mapped[Optional["MenuItem"]] = relationship(remote_side=[id])


class MenuItemVersion(Base):
    __tablename__ = "menu_item_versions"
    __table_args__ = (
        UniqueConstraint("menu_item_id", "version_number", name="uq_item_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    menu_item_id: Mapped[int] = mapped_column(ForeignKey("menu_items.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    dish_name: Mapped[str] = mapped_column(String(255))
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    superseded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    menu_item: Mapped["MenuItem"] = relationship(back_populates="versions")
    pre_meal_feedback: Mapped[list["PreMealFeedback"]] = relationship(
        back_populates="menu_item_version"
    )


class MenuChangeLog(Base):
    __tablename__ = "menu_change_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meal_session_id: Mapped[int] = mapped_column(ForeignKey("meal_sessions.id"), index=True)
    menu_item_id: Mapped[Optional[int]] = mapped_column(ForeignKey("menu_items.id"), nullable=True)
    change_kind: Mapped[ChangeKind] = mapped_column(Enum(ChangeKind))
    summary: Mapped[str] = mapped_column(Text)
    manager_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PreMealFeedback(Base):
    __tablename__ = "pre_meal_feedback"
    __table_args__ = (
        UniqueConstraint(
            "menu_item_version_id",
            "student_id",
            name="uq_premeal_student_version",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    menu_item_version_id: Mapped[int] = mapped_column(
        ForeignKey("menu_item_versions.id"), index=True
    )
    meal_session_id: Mapped[int] = mapped_column(ForeignKey("meal_sessions.id"), index=True)
    student_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False)
    preference_rating: Mapped[int] = mapped_column(Integer)
    eat_likelihood: Mapped[EatLikelihood] = mapped_column(Enum(EatLikelihood))
    dissatisfaction_reasons: Mapped[str] = mapped_column(Text, default="")
    appetite_reasons: Mapped[str] = mapped_column(Text, default="")
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_stale_for_old_version: Mapped[bool] = mapped_column(Boolean, default=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    menu_item_version: Mapped["MenuItemVersion"] = relationship(
        back_populates="pre_meal_feedback"
    )


class PostMealFeedback(Base):
    __tablename__ = "post_meal_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    menu_item_version_id: Mapped[int] = mapped_column(
        ForeignKey("menu_item_versions.id"), index=True
    )
    meal_session_id: Mapped[int] = mapped_column(ForeignKey("meal_sessions.id"), index=True)
    student_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False)
    taste_rating: Mapped[int] = mapped_column(Integer)
    actually_ate: Mapped[bool] = mapped_column(Boolean)
    wasted_food: Mapped[bool] = mapped_column(Boolean, default=False)
    dissatisfaction_reasons: Mapped[str] = mapped_column(Text, default="")
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MealWasteRecord(Base):
    __tablename__ = "meal_waste_records"
    __table_args__ = (UniqueConstraint("meal_session_id", name="uq_waste_meal"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meal_session_id: Mapped[int] = mapped_column(ForeignKey("meal_sessions.id"), unique=True)
    total_waste_kg: Mapped[float] = mapped_column(Float)
    recorded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    meal_session: Mapped["MealSession"] = relationship(back_populates="waste_record")


class WasteForecast(Base):
    __tablename__ = "waste_forecasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meal_session_id: Mapped[int] = mapped_column(ForeignKey("meal_sessions.id"), index=True)
    predicted_waste_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    prediction_interval_low: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    prediction_interval_high: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    model_type: Mapped[str] = mapped_column(String(64))
    feature_summary: Mapped[str] = mapped_column(Text, default="")
    insufficient_data: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ForecastEvaluation(Base):
    __tablename__ = "forecast_evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    waste_forecast_id: Mapped[int] = mapped_column(ForeignKey("waste_forecasts.id"))
    actual_waste_kg: Mapped[float] = mapped_column(Float)
    absolute_error: Mapped[float] = mapped_column(Float)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ManagerRecommendation(Base):
    __tablename__ = "manager_recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meal_session_id: Mapped[int] = mapped_column(ForeignKey("meal_sessions.id"), index=True)
    menu_item_id: Mapped[Optional[int]] = mapped_column(ForeignKey("menu_items.id"), nullable=True)
    suggestion: Mapped[str] = mapped_column(Text)
    risk_level: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel))
    trigger_metrics: Mapped[str] = mapped_column(Text)
    status: Mapped[RecommendationStatus] = mapped_column(
        Enum(RecommendationStatus), default=RecommendationStatus.pending
    )
    replacement_dish: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    decided_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ManagerNotification(Base):
    __tablename__ = "manager_notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mess_id: Mapped[int] = mapped_column(ForeignKey("mess.id"), index=True)
    meal_session_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("meal_sessions.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(32), default="normal")
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    external_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ComplaintRecord(Base):
    __tablename__ = "complaint_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mess_id: Mapped[int] = mapped_column(ForeignKey("mess.id"), index=True)
    meal_session_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("meal_sessions.id"), nullable=True
    )
    raw_text: Mapped[str] = mapped_column(Text)
    ai_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_topics: Mapped[str] = mapped_column(Text, default="")
    ai_unavailable: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DailyReportSnapshot(Base):
    __tablename__ = "daily_report_snapshots"
    __table_args__ = (UniqueConstraint("mess_id", "report_date", name="uq_daily_report"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mess_id: Mapped[int] = mapped_column(ForeignKey("mess.id"), index=True)
    report_date: Mapped[date] = mapped_column(Date)
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WeeklyReportSnapshot(Base):
    __tablename__ = "weekly_report_snapshots"
    __table_args__ = (
        UniqueConstraint("mess_id", "week_start_date", name="uq_weekly_report"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mess_id: Mapped[int] = mapped_column(ForeignKey("mess.id"), index=True)
    week_start_date: Mapped[date] = mapped_column(Date)
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WasteAnomalyFlag(Base):
    __tablename__ = "waste_anomaly_flags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meal_session_id: Mapped[int] = mapped_column(ForeignKey("meal_sessions.id"), index=True)
    expected_waste_kg: Mapped[float] = mapped_column(Float)
    actual_waste_kg: Mapped[float] = mapped_column(Float)
    z_score: Mapped[float] = mapped_column(Float)
    is_anomaly: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
