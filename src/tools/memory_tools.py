"""Claude-side tools for session state + long-term memory."""

from __future__ import annotations

import json
from contextvars import ContextVar

from src.db import memory as db_memory
from src.db import state as db_state

# Set by the brain at the start of every turn so tools can find the chat.
_chat_id_ctx: ContextVar[int | None] = ContextVar("chat_id_ctx", default=None)


def set_chat_id(chat_id: int) -> None:
    _chat_id_ctx.set(chat_id)


def _chat_id() -> int:
    cid = _chat_id_ctx.get()
    if cid is None:
        raise RuntimeError("chat_id not set in context — brain bug")
    return cid


# ── Session state ─────────────────────────────────────────────────────────


async def set_active_spreadsheet(spreadsheet_id: str, title: str | None = None) -> str:
    """Mark a spreadsheet as currently in focus. Future read/write tool calls can
    omit the id — the assistant will reuse this one until you switch."""
    cid = _chat_id()
    await db_state.set_value(cid, "active_spreadsheet_id", spreadsheet_id)
    if title:
        await db_state.set_value(cid, "active_spreadsheet_title", title)
    return f"ok, активная таблица: {title or spreadsheet_id}"


async def set_active_sheet(sheet_name: str) -> str:
    """Remember which sheet/tab inside the active spreadsheet you're working with."""
    cid = _chat_id()
    await db_state.set_value(cid, "active_sheet", sheet_name)
    return f"ok, активный лист: {sheet_name}"


async def set_focus(topic: str) -> str:
    """Pin a free-form description of what's currently the focus of the conversation."""
    cid = _chat_id()
    await db_state.set_value(cid, "current_focus", topic)
    return f"ok, фокус: {topic}"


async def clear_focus() -> str:
    """Drop the current focus (no longer working on this topic)."""
    cid = _chat_id()
    await db_state.clear(cid, "current_focus")
    await db_state.clear(cid, "active_spreadsheet_id")
    await db_state.clear(cid, "active_spreadsheet_title")
    await db_state.clear(cid, "active_sheet")
    return "ok, контекст сброшен"


# ── Long-term memory ──────────────────────────────────────────────────────


async def remember(fact: str) -> str:
    """Pin a fact in long-term memory. Use when the user shares something
    durable — names of partners, recurring constraints, project meanings."""
    cid = _chat_id()
    fid = await db_memory.add(cid, fact)
    return json.dumps({"ok": True, "memory_id": fid, "fact": fact}, ensure_ascii=False)


async def recall(query: str | None = None) -> str:
    """Search the user's pinned facts. Pass a substring/keyword query, or
    omit to get the 10 most recent facts."""
    cid = _chat_id()
    if query:
        facts = await db_memory.search(cid, query, limit=10)
    else:
        facts = await db_memory.list_recent(cid, limit=10)
    if not facts:
        return "(в памяти ничего не найдено)"
    return "\n".join(f"- {f}" for f in facts)


async def forget(query: str) -> str:
    """Delete pinned facts that match the query."""
    cid = _chat_id()
    n = await db_memory.delete_matching(cid, query)
    return f"удалено фактов: {n}"
