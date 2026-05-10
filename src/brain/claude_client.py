"""OpenAI-compatible client pointed at OpenRouter.

OpenRouter exposes Anthropic Claude (and many others) behind the OpenAI chat
completions API, including tool use. We use the OpenAI SDK as the transport.
"""

from openai import AsyncOpenAI

from src.config import settings


def make_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        default_headers={
            "HTTP-Referer": "https://github.com/zolupa1488/vlad-assistant",
            "X-Title": "Vlad Assistant",
        },
    )
