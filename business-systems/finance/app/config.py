"""财务 ERP 仿真业务系统配置。"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    APP_NAME: str = "财务ERP 仿真业务系统"
    PORT: int = 8003
    DATABASE_URL: str = "postgresql+asyncpg://postgres:123456@localhost:5432/finance_db"
    SERVICE_TOKEN: str = "biz-svc-2026-token"
    CORS_ORIGINS: str = "*"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
