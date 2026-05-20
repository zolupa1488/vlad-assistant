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

    # --- LLM routing — pure OpenRouter, two tiers ---
    openrouter_api_key: str
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Three-tier routing — Haiku default, Sonnet mid, Opus for deep thinking.
    # Актуальные модели на май 2026 (Opus 4.7 — $5/$25, втрое дешевле старой Opus 4).
    haiku_model: str = "anthropic/claude-haiku-4-5"
    sonnet_model: str = "anthropic/claude-sonnet-4.6"
    opus_model: str = "anthropic/claude-opus-4.7"  # для recall / рефлексии / личного
    llm_model: str = "anthropic/claude-sonnet-4.6"  # legacy alias — points to sonnet
    llm_fallback_model: str = "anthropic/claude-sonnet-4.6"

    max_history_messages: int = 10
    max_response_tokens: int = 4000
    max_tool_hops: int = 15

    # Tier escalation tuning.
    escalation_hop_threshold: int = 3
    auto_rollback_simple_turns: int = 5

    # Anthropic direct API kept as optional override (not used by default).
    # If both anthropic_api_key AND anthropic_primary_for_sonnet=True are set,
    # Sonnet calls go through Anthropic's OpenAI-compat endpoint first, with
    # OpenRouter as fallback. Default OFF — pure OpenRouter is simpler.
    anthropic_api_key: str | None = None
    anthropic_base_url: str = "https://api.anthropic.com/v1/"
    anthropic_model: str = "claude-sonnet-4-5-20250929"
    anthropic_primary_for_sonnet: bool = False

    # --- Storage ---
    database_url: str = "sqlite+aiosqlite:////app/data/bot.db"
    qdrant_url: str | None = None
    redis_url: str | None = None

    # --- Google (OAuth user-token flow) ---
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None
    google_oauth_refresh_token: str | None = None

    # --- Figma REST API (read-only fallback when Mac Bridge is down) ---
    figma_token: str | None = None

    # --- Mac Bridge (Claude Code via cloudflared tunnel for MCP access) ---
    mac_bridge_url: str | None = None
    mac_bridge_token: str | None = None
    mac_bridge_timeout: float = 300.0  # 5 min — Claude Code на сложных задачах долгий

    # --- Image generation via OpenRouter (nano-banana) ---
    image_model: str = "google/gemini-2.5-flash-image-preview"
    image_gen_enabled: bool = True

    # --- Composio (Instagram live stats via Composio integration platform) ---
    # composio_api_key is a secret — set it as a Railway env var, never in code.
    composio_api_key: str | None = None
    composio_user_id: str = "vladimir"


settings = Settings()
