from datetime import date, datetime, time
from enum import Enum

from pydantic import BaseModel, Field


class MealTypeEnum(str, Enum):
    breakfast = "breakfast"
    lunch = "lunch"
    dinner = "dinner"


class EatLikelihoodEnum(str, Enum):
    definitely_eat = "definitely_eat"
    probably_eat = "probably_eat"
    not_sure = "not_sure"
    probably_skip = "probably_skip"
    definitely_skip = "definitely_skip"


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    mess_id: int | None

    class Config:
        from_attributes = True


class MessOut(BaseModel):
    id: int
    name: str
    code: str

    class Config:
        from_attributes = True


class MessSettingsOut(BaseModel):
    breakfast_start: time
    lunch_start: time
    dinner_start: time
    pre_meal_cutoff_minutes_before: int
    min_responses_for_risk_alert: int
    email_notifications_enabled: bool
    push_notifications_enabled: bool

    class Config:
        from_attributes = True


class MessSettingsUpdate(BaseModel):
    breakfast_start: time | None = None
    lunch_start: time | None = None
    dinner_start: time | None = None
    pre_meal_cutoff_minutes_before: int | None = Field(default=None, ge=0, le=180)
    min_responses_for_risk_alert: int | None = Field(default=None, ge=1, le=500)
    email_notifications_enabled: bool | None = None
    push_notifications_enabled: bool | None = None


class DishVersionOut(BaseModel):
    id: int
    menu_item_id: int
    version_number: int
    dish_name: str
    notes: str | None
    replaced_from_item_id: int | None = None


class MealSessionOut(BaseModel):
    id: int
    mess_id: int
    meal_date: date
    meal_type: MealTypeEnum
    status: str
    menu_version: int


class WeeklyPlanOut(BaseModel):
    id: int
    mess_id: int
    week_start_date: date
    status: str


class PreMealFeedbackIn(BaseModel):
    menu_item_version_id: int
    preference_rating: int = Field(ge=1, le=5)
    eat_likelihood: EatLikelihoodEnum
    dissatisfaction_reasons: list[str] = Field(default_factory=list)
    appetite_reasons: list[str] = Field(default_factory=list)
    comment: str | None = None
    anonymous: bool = False


class PreMealFeedbackOut(BaseModel):
    id: int
    menu_item_version_id: int
    preference_rating: int
    eat_likelihood: EatLikelihoodEnum
    is_stale_for_old_version: bool
    submitted_at: datetime
    saved: bool = True


class PostMealFeedbackIn(BaseModel):
    menu_item_version_id: int
    taste_rating: int = Field(ge=1, le=5)
    actually_ate: bool
    wasted_food: bool = False
    dissatisfaction_reasons: list[str] = Field(default_factory=list)
    comment: str | None = None
    anonymous: bool = False


class WasteRecordIn(BaseModel):
    total_waste_kg: float = Field(ge=0)
    notes: str | None = None


class RecommendationDecisionIn(BaseModel):
    status: str
    replacement_dish: str | None = None
