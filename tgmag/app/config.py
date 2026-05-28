from __future__ import annotations

from functools import cached_property
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = Field(..., alias="BOT_TOKEN")
    tg_api_id: int = Field(..., alias="TG_API_ID")
    tg_api_hash: str = Field(..., alias="TG_API_HASH")
    admin_ids: list[int] = Field(..., alias="ADMIN_IDS")
    database_url: str = Field(..., alias="DATABASE_URL")
    fernet_key: str = Field(..., alias="FERNET_KEY")
    session_dir: Path = Field(default=Path("./data/sessions"), alias="SESSION_DIR")
    backup_dir: Path = Field(default=Path("./data/backups"), alias="BACKUP_DIR")
    default_rate_max_actions: int = Field(default=8, alias="DEFAULT_RATE_MAX_ACTIONS")
    default_rate_per_seconds: int = Field(default=60, alias="DEFAULT_RATE_PER_SECONDS")
    default_jitter_min: int = Field(default=2, alias="DEFAULT_JITTER_MIN")
    default_jitter_max: int = Field(default=6, alias="DEFAULT_JITTER_MAX")
    service_monitor_interval_seconds: int = Field(default=300, alias="SERVICE_MONITOR_INTERVAL_SECONDS")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    mini_app_enabled: bool = Field(default=False, alias="MINI_APP_ENABLED")
    mini_app_host: str = Field(default="127.0.0.1", alias="MINI_APP_HOST")
    mini_app_port: int = Field(default=8080, alias="MINI_APP_PORT")
    mini_app_public_url: str = Field(default="", alias="MINI_APP_PUBLIC_URL")
    mini_app_auth_max_age_seconds: int = Field(default=86400, alias="MINI_APP_AUTH_MAX_AGE_SECONDS")

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, value: object) -> list[int]:
        if isinstance(value, list):
            return [int(v) for v in value]
        if isinstance(value, int):
            return [value]
        if isinstance(value, str):
            return [int(v.strip()) for v in value.split(",") if v.strip()]
        raise ValueError("ADMIN_IDS must be a comma separated list or integer")

    @cached_property
    def sync_database_url(self) -> str:
        return self.database_url.replace("+asyncpg", "")


settings = Settings()
