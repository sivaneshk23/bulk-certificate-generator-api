from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Bulk Certificate Generator API"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/certificates"
    redis_url: str = "redis://localhost:6379/0"
    processing_mode: str = "celery"
    storage_dir: str = "storage/certificates"
    max_recipients_per_job: int = Field(default=5000, ge=1, le=50000)
    log_level: str = "INFO"
    cors_origins: str = "*"
    font_regular_path: str | None = None
    font_bold_path: str | None = None
    font_tamil_path: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
