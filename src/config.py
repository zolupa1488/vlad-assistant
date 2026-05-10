"""Centralised configuration via pydantic-settings.

Reads from environment variables (Railway Shared Variables in production,
`.env` file locally via docker-compose).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Telegram ---
    telegram_bot_token: str
    owner_telegram_user_id: int

    # --- LLM (OpenRouter) ---
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "anthropic/claude-opus-4"
    llm_fallback_model: str = "anthropic/claude-sonnet-4"

    # --- Storage (used from Phase 1+) ---
    database_url: str | None = None
    qdrant_url: str | None = None
    redis_url: str | None = None


settings = Settings()
