"""
Application configuration via pydantic-settings.
All settings are loaded from environment variables or .env file.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for TalentCopilot backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Database ────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://talentcopilot:talentcopilot@localhost:5432/talentcopilot"
    database_url_sync: str = "postgresql+psycopg2://talentcopilot:talentcopilot@localhost:5432/talentcopilot"

    # ── Redis ───────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── JWT ─────────────────────────────────────────────────
    jwt_secret_key: str = "CHANGE_ME_TO_A_RANDOM_64_CHAR_HEX_STRING"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_minutes: int = 10080  # 7 days

    # ── OpenAI / LLM ───────────────────────────────────────
    openai_api_key: str = ""
    llm_model_name: str = "gpt-4o-mini"

    # ── GitHub ──────────────────────────────────────────────
    github_token: str = ""

    # ── Rate Limiting ───────────────────────────────────────
    rate_limit_chat: str = "30/minute"
    rate_limit_ingestion: str = "5/minute"

    # ── Memory ──────────────────────────────────────────────
    memory_window_size: int = 20
    summary_threshold: int = 50

    # ── File Upload ─────────────────────────────────────────
    max_upload_size_mb: int = 10
    allowed_extensions: str = "pdf,docx"

    @property
    def allowed_extensions_list(self) -> List[str]:
        return [ext.strip().lower() for ext in self.allowed_extensions.split(",")]

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache()
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
