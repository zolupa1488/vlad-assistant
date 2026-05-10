"""Centralised configuration via pydantic-settings."""

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
    openrouter_api_key: str
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Default to Sonnet for cost; switch to Opus via Railway env (LLM_MODEL=...).
    llm_model: str = "anthropic/claude-sonnet-4"
    llm_fallback_model: str = "anthropic/claude-3.5-sonnet"
    max_history_messages: int = 10
    max_response_tokens: int = 2000
    max_tool_hops: int = 6

    # --- Storage ---
    database_url: str = "sqlite+aiosqlite:////app/data/bot.db"
    qdrant_url: str | None = None
    redis_url: str | None = None


settings = Settings()
