"""Main Claude tool-use loop.

One LLM call → if it requested tools, execute them, feed results back → repeat
until Claude returns a plain content response or we hit max_tool_hops.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from src.brain.claude_client import make_client
from src.brain.persona import OWNER_HINT, STRANGER_HINT, SYSTEM_PROMPT
from src.config import settings
from src.tools.registry import TOOL_SCHEMAS, execute_tool


async def respond(
    *,
    user_text: str,
    is_owner: bool,
    history: list[dict[str, Any]],
) -> str:
    """Run the tool-use loop and return the final assistant message text."""
    client = make_client()

    role_hint = OWNER_HINT if is_owner else STRANGER_HINT
    system_msg = f"{SYSTEM_PROMPT}\n\n# Контекст текущего диалога\n{role_hint}"

    messages: list[dict[str, Any]] = [{"role": "system", "content": system_msg}]
    # only forward user/assistant turns (not tool turns) from history
    for h in history:
        if h.get("role") in {"user", "assistant"} and h.get("content"):
            messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": user_text})

    for hop in range(settings.max_tool_hops):
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            max_tokens=settings.max_response_tokens,
        )
        msg = response.choices[0].message

        if not msg.tool_calls:
            text = (msg.content or "").strip()
            logger.info("brain done after {} hop(s); reply_len={}", hop, len(text))
            return text or "(пустой ответ)"

        # record assistant turn that requested tools
        messages.append(
            {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
            }
        )

        for tc in msg.tool_calls:
            name = tc.function.name
            args_json = tc.function.arguments or "{}"
            logger.info("tool_call name={} args={}", name, args_json[:200])
            result = await execute_tool(name, args_json)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                }
            )

    logger.warning("hit max_tool_hops={} without final answer", settings.max_tool_hops)
    return "Хм, что-то застрял в инструментах. Можешь переформулировать?"
