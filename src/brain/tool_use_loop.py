"""Main Claude tool-use loop with session-state and pinned-fact context injection."""

from __future__ import annotations

from typing import Any

from loguru import logger

from src.brain.claude_client import make_client
from src.brain.persona import OWNER_HINT, STRANGER_HINT, SYSTEM_PROMPT
from src.config import settings
from src.db import memory as db_memory
from src.db import state as db_state
from src.tools.memory_tools import set_chat_id
from src.tools.registry import (
    TOOL_SCHEMAS,
    collect_files,
    execute_tool,
    reset_file_collector,
)


def _format_state_block(state: dict[str, str], facts: list[str]) -> str:
    lines: list[str] = []
    if state:
        lines.append("# Текущий контекст")
        if state.get("active_spreadsheet_title") or state.get("active_spreadsheet_id"):
            title = state.get("active_spreadsheet_title", "")
            sid = state.get("active_spreadsheet_id", "")
            lines.append(f"- Активная таблица: {title} (id={sid})")
        if state.get("active_sheet"):
            lines.append(f"- Активный лист: {state['active_sheet']}")
        if state.get("current_focus"):
            lines.append(f"- Фокус: {state['current_focus']}")
        for k, v in state.items():
            if k in {"active_spreadsheet_id", "active_spreadsheet_title",
                     "active_sheet", "current_focus"}:
                continue
            lines.append(f"- {k}: {v}")
        lines.append("")

    if facts:
        lines.append("# Что я помню (закреплённые факты)")
        for f in facts:
            lines.append(f"- {f}")
        lines.append(
            "Если этого не хватает — дёрни recall(query) с ключевым словом."
        )
        lines.append("")

    return "\n".join(lines).strip()


async def respond(
    *,
    user_text: str,
    is_owner: bool,
    history: list[dict[str, Any]],
    chat_id: int,
) -> tuple[str, list[dict[str, Any]]]:
    """Run the tool-use loop. Returns (final_text, files_to_send)."""
    reset_file_collector()
    set_chat_id(chat_id)
    client = make_client()

    role_hint = OWNER_HINT if is_owner else STRANGER_HINT

    state = await db_state.get_all(chat_id)
    pinned = await db_memory.list_recent(chat_id, limit=5)
    state_block = _format_state_block(state, pinned)

    system_msg = f"{SYSTEM_PROMPT}\n\n# Контекст текущего диалога\n{role_hint}"
    if state_block:
        system_msg += f"\n\n{state_block}"

    messages: list[dict[str, Any]] = [{"role": "system", "content": system_msg}]
    for h in history:
        if h.get("role") in {"user", "assistant"} and h.get("content"):
            messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": user_text})

    final_text = ""
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
            final_text = (msg.content or "").strip()
            logger.info("brain done after {} hop(s); reply_len={}", hop, len(final_text))
            break

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
    else:
        logger.warning("hit max_tool_hops={} without final answer", settings.max_tool_hops)
        final_text = "Хм, что-то застрял в инструментах. Можешь переформулировать?"

    files = collect_files()
    if files:
        logger.info("turn produced {} file(s) to ship", len(files))

    return final_text or "(пустой ответ)", files
