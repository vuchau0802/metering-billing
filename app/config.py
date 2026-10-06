from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

UNITS_PER_PRICE_BLOCK = 1_000

API_CALL_PRICE_PER_1K = 2_000
INPUT_PRICE_PER_1K = 150_000
CACHED_INPUT_PRICE_PER_1K = 75_000
OUTPUT_PRICE_PER_1K = 600_000
API_CALL_OVERAGE_PRICE_PER_1K = 3_000
AI_TOKEN_OVERAGE_PRICE_PER_1K = 750_000


class Settings(BaseSettings):
    database_url: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5432/metering"
    )

    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_pro_price_id: str | None = None
    app_base_url: str = "http://localhost:8004"

    usage_alert_transport: Literal[
        "logging",
        "smtp",
    ] = "logging"

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_use_starttls: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
