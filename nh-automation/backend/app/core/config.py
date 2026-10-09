"""Application configuration, loaded from environment variables (see .env.example)."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process-wide configuration. One instance, cached by get_settings()."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"

    database_url: str = "postgresql+psycopg://nh_app:change-me@localhost:5432/nh_automation"

    secret_key: str = "dev-secret-change-me"
    session_cookie_name: str = "nh_session"
    csrf_cookie_name: str = "nh_csrf"
    allowed_origins: str = "http://localhost:5173"

    # NFR-7a: single timezone setting, UTC stored, this used for display/"today".
    tz: str = "America/Mazatlan"

    plc_allowed_networks: str = "192.168.50.0/24"

    backup_dir: str = "/backups"
    backup_retention_days: int = 30

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
