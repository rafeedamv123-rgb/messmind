from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict

DISPLAY_TZ = ZoneInfo("Asia/Kolkata")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "MessMind"
    database_url: str = "sqlite:///./messmind.db"
    secret_key: str = "dev-secret-change-in-production"
    access_token_expire_minutes: int = 60 * 24
    ai_complaint_url: str | None = None
    ai_complaint_api_key: str | None = None
    min_responses_reliable_forecast: int = 10
    min_historical_meals_for_ml: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
