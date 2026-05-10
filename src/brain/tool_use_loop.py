"""Main Claude tool-use loop with session-state and pinned-fact context injection."""

from __future__ import annotations

import re
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
            if k in {
                "active_spreadsheet_id",
                "active_spreadsheet_title",
                "active_sheet",
                "current_focus",
            }:
                continue
            lines.append(f"- {k}: {v}")
        lines.append("")

    if facts:
        lines.append("# Что я помню (закреплённые факты)")
        for f in facts:
            lines.append(f"- {f}")
        lines.append("Если этого не хватает — дёрни recall(query) с ключевым словом.")
        lines.append("")

    return "\n".join(lines).strip()


_MD_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
_MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_MD_ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+?)\*(?!\*)")
_MD_BULLET_RE = re.compile(r"^\s*[-*]\s+", re.MULTILINE)
_MD_UNDERLINE_RE = re.compile(r"__(.+?)__", re.DOTALL)


def _strip_markdown(text: str) -> str:
    """Strip markdown that Telegram doesn't render — Claude sometimes drifts into
    asterisk-bold and bullet-lists despite the prompt."""
    if not text:
        return text
    text = _MD_HEADING_RE.sub("", text)
    text = _MD_BOLD_RE.sub(r"\1", text)
    text = _MD_UNDERLINE_RE.sub(r"\1", text)
    text = _MD_ITALIC_RE.sub(r"\1", text)
    text = _MD_BULLET_RE.sub("• ", text)
    return text


def _summarize_progress(messages: list[dict[str, Any]]) -> str:
    """If we hit max_tool_hops, build a short progress note from what tools
    actually returned so the user gets useful output, not a generic 'stuck'."""
    notes: list[str] = []
    for m in messages:
        if m.get("role") != "tool":
            continue
        content = (m.get("content") or "").strip()
        if not content or content.startswith("error executing"):
            continue
        snippet = content[:300].replace("\n", " ")
        notes.append(f"• {snippet}")
        if len(notes) >= 5:
            break
    if not notes:
        return "застрял в цикле инструментов и не успел собрать ответ"
    return "вот что успел собрать до того как упёрся в лимит:\n\n" + "\n".join(notes)


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
    hit_limit = False

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
            logger.info(
                "brain done after {} hop(s); reply_len={}", hop, len(final_text)
            )
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
        hit_limit = True
        logger.warning("hit max_tool_hops={} without final answer", settings.max_tool_hops)
        # Try one final message with no tools to wrap up
        try:
            response = await client.chat.completions.create(
                model=settings.llm_model,
                messages=messages
                + [
                    {
                        "role": "user",
                        "content": (
                            "Заверши ответ по тому, что уже собрано. Без новых tool calls."
                        ),
                    }
                ],
                max_tokens=settings.max_response_tokens,
            )
            final_text = (response.choices[0].message.content or "").strip()
        except Exception:
            logger.exception("wrap-up call failed")
            final_text = ""

        if not final_text:
            final_text = (
                "Запутался в цепочке шагов — " + _summarize_progress(messages)
            )

    if not final_text:
        final_text = "(пустой ответ)"

    final_text = _strip_markdown(final_text)
    if hit_limit:
        logger.info("returned soft fallback (hit limit, len={})", len(final_text))

    files = collect_files()
    if files:
        logger.info("turn produced {} file(s) to ship", len(files))

    return final_text, files
