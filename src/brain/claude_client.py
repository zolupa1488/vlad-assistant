"""Two-tier LLM client — Haiku (default) + Sonnet (escalation), both via OpenRouter.

Tier selection is decided by the caller (tool-use loop) based on heuristics,
manual overrides, or explicit `escalate_to_sonnet` tool calls. This module
just routes the request to the right model string.

Optional override: if `ANTHROPIC_API_KEY` is set AND `anthropic_primary_for_sonnet`
is true in config, Sonnet calls go through Anthropic's OpenAI-compatible
endpoint first with OpenRouter as fallback. Default OFF — pure OpenRouter is
simpler and avoids managing two billings.
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from openai import AsyncOpenAI

from src.config import settings


class TieredClient:
    """OpenAI-SDK client that routes to haiku/sonnet tiers via OpenRouter (default)
    or Anthropic direct (optional)."""

    def __init__(self) -> None:
        self.openrouter = AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            default_headers={
                "HTTP-Referer": "https://github.com/zolupa1488/vlad-assistant",
                "X-Title": "Vlad Assistant",
            },
        )

        self.anthropic: AsyncOpenAI | None = None
        if settings.anthropic_api_key and settings.anthropic_primary_for_sonnet:
            self.anthropic = AsyncOpenAI(
                api_key=settings.anthropic_api_key,
                base_url=settings.anthropic_base_url,
            )
            logger.info(
                "tiered client: anthropic primary for sonnet ON (model={})",
                settings.anthropic_model,
            )
        else:
            logger.info("tiered client: pure openrouter (haiku + sonnet)")

    async def chat_complete(
        self,
        *,
        tier: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
    ):
        """Run a chat completion on the given tier ('haiku' or 'sonnet').

        For 'sonnet': if Anthropic primary is configured, try Anthropic first,
        fall back to OpenRouter on error. Otherwise — OpenRouter directly.

        For 'haiku': always OpenRouter.
        """
        kwargs: dict[str, Any] = {
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        if tier == "sonnet" and self.anthropic is not None:
            try:
                resp = await self.anthropic.chat.completions.create(
                    model=settings.anthropic_model,
                    **kwargs,
                )
                logger.debug("llm route=anthropic tier=sonnet ok")
                return resp
            except Exception as e:
                logger.warning(
                    "anthropic primary failed ({}: {}) — falling back to openrouter",
                    type(e).__name__,
                    str(e)[:240],
                )

        model_id = (
            settings.haiku_model if tier == "haiku" else settings.sonnet_model
        )
        resp = await self.openrouter.chat.completions.create(
            model=model_id,
            **kwargs,
        )
        logger.debug("llm route=openrouter tier={} model={} ok", tier, model_id)
        return resp


def make_client() -> TieredClient:
    return TieredClient()
