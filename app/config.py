from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

UNITS_PER_PRICE_BLOCK = 1_000

API_CALL_PRICE_PER_1K = 2_000
INPUT_PRICE_PER_1K = 150_000
CACHED_INPUT_PRICE_PER_1K = 75_000
OUTPUT_PRICE_PER_1K = 600_000

class Settings(BaseSettings):
    database_url: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5432/metering"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()