"""Tool-use loop — single fixed model (Sonnet 4.6).

Model is pinned to Sonnet for every turn: no Haiku default, no Opus
escalation, no mid-conversation tier switching. Switching models between
turns (and inside one turn) broke voice consistency, so the conversational
layer now runs on exactly one model. (Vladimir, 2026-05-21.)

The old escalation branches below are kept but inert — they are all guarded
by `tier == "haiku"`, which never holds anymore.
"""

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
from src.tools.model_tools import (
    consume_escalation_signal,
    reset_escalation_signal,
    set_current_tier,
)
from src.tools.registry import (
    TOOL_SCHEMAS,
    collect_files,
    execute_tool,
    reset_file_collector,
)

# Tools that always need Sonnet — they produce final artifacts and we don't
# cheap out on them. Includes business-advisor toolkit: these tools spawn their
# own focused sub-LLM calls with methodology, but Sonnet orchestrates them more
# reliably (one call, no loops, no "actually let me write it myself" override).
HEAVY_TOOLS = {
    "generate_pptx",
    "generate_docx",
    "generate_pdf",
    "generate_chart",
    "generate_image",
    "mac_bridge_run",
    "draft_outreach",
    "research_company",
    "prep_meeting",
    "summarize_call",
    "competitive_brief",
    "business_brief",
    "instagram_post_pack",
    "reels_script",
    "hook_bank",
    "caption_for_artwork",
    "content_calendar",
    "insta_audit",
}

# Phrases in user text that hint "this is non-trivial, use Sonnet".
HEAVY_KEYWORDS_RE = re.compile(
    r"(?i)\b("
    r"подумай|разверни|глубже|детально|развёрнуто|подробно|тщательно|"
    r"проанализируй|стратегия|архитектур|спроектируй|концепц|сложн"
    r")\b"
)

# Phrases that mean "this is a question about Vladimir's past" — second-brain
# territory. Haiku tends to answer from thin air instead of calling
# recall_history, so we force Sonnet, which reliably calls the recall tools.
RECALL_KEYWORDS_RE = re.compile(
    r"(?i)("
    r"помнишь|вспомни|напомни|помниш|"
    r"кто так(ой|ая|ие)|что за |"
    r"что я (думал|говорил|решал|писал|хотел|планировал)|"
    r"к чему я пришёл|к чему пришли|мы обсуждали|"
    r"что было с |что у меня было|раньше я|"
    r"из истории|из архива|второй мозг|второго мозга"
    r")"
)

# Manual switch commands — parsed in handlers.py before this loop runs.
# Kept here as constants for visibility.
SWITCH_TO_SONNET_RE = re.compile(
    r"(?i)\b(переключ\w* на сонет|включи сонет|/sonnet|давай на сонет)\b"
)
SWITCH_TO_HAIKU_RE = re.compile(
    r"(?i)\b(верн\w* на хайку|переключ\w* на хайку|включи хайку|/haiku|"
    r"возвращайся на хайку|давай на хайку)\b"
)
WHICH_MODEL_RE = re.compile(
    r"(?i)\b(кака\w* модел|с какой модел|какую модел|/which|какая ллм|"
    r"на какой ллм|чем сейчас отвечаешь)\b"
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
                "forced_model",
                "sonnet_simple_streak",
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


def _tier_block() -> str:
    return (
        "# Модель\n"
        "Ты работаешь на одной закреплённой модели — Claude Sonnet 4.6. "
        "Переключений между моделями нет. Если спросят «какая модель / на чём "
        "ты сейчас» — отвечай: Sonnet 4.6, не выдумывай.\n"
    )


_MD_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
_MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_MD_ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+?)\*(?!\*)")
_MD_BULLET_RE = re.compile(r"^\s*[-*]\s+", re.MULTILINE)
_MD_UNDERLINE_RE = re.compile(r"__(.+?)__", re.DOTALL)


def _strip_markdown(text: str) -> str:
    if not text:
        return text
    text = _MD_HEADING_RE.sub("", text)
    text = _MD_BOLD_RE.sub(r"\1", text)
    text = _MD_UNDERLINE_RE.sub(r"\1", text)
    text = _MD_ITALIC_RE.sub(r"\1", text)
    text = _MD_BULLET_RE.sub("• ", text)
    return text


def _summarize_progress(messages: list[dict[str, Any]]) -> str:
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
) -> tuple[str, list[dict[str, Any]], list[str]]:
    """Run the tool-use loop. Returns (final_text, files, announcements).

    `announcements` is a list of short strings that handlers should post as
    separate messages — e.g. "*Сонет вышел на пятно: ...*" or
    "*Хайку вышел на пятно: на Sonnet 5 простых ходов прошло, откатываюсь.*"
    """
    reset_file_collector()
    reset_escalation_signal()
    set_chat_id(chat_id)
    client = make_client()

    role_hint = OWNER_HINT if is_owner else STRANGER_HINT

    state = await db_state.get_all(chat_id)
    pinned = await db_memory.list_recent(chat_id, limit=5)
    state_block = _format_state_block(state, pinned)

    # --- Model: pinned to Sonnet ----------------------------------------
    # One fixed model for every turn — no Haiku default, no Opus escalation,
    # no mid-conversation switching. This is what keeps the voice consistent.
    tier = "sonnet"
    forced_active = False
    set_current_tier(tier)
    announcements: list[str] = []

    # --- Build messages -------------------------------------------------
    system_msg = (
        f"{SYSTEM_PROMPT}\n\n# Контекст текущего диалога\n{role_hint}"
        f"\n\n{_tier_block()}"
    )
    if state_block:
        system_msg += f"\n\n{state_block}"

    messages: list[dict[str, Any]] = [{"role": "system", "content": system_msg}]
    for h in history:
        if h.get("role") in {"user", "assistant"} and h.get("content"):
            messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": user_text})

    final_text = ""
    hit_limit = False
    used_heavy = False
    hops_done = 0

    # --- Tool-use loop --------------------------------------------------
    for hop in range(settings.max_tool_hops):
        hops_done = hop + 1
        response = await client.chat_complete(
            tier=tier,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            max_tokens=settings.max_response_tokens,
        )
        msg = response.choices[0].message

        if not msg.tool_calls:
            final_text = (msg.content or "").strip()
            logger.info(
                "brain done after {} hop(s); tier={} reply_len={}",
                hop, tier, len(final_text),
            )
            break

        messages.append(
            {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
            }
        )

        # Pre-scan tool calls for tier triggers (heavy tools, escalation).
        for tc in msg.tool_calls:
            name = tc.function.name
            if name in HEAVY_TOOLS:
                used_heavy = True
                if tier == "haiku":
                    announcements.append(
                        f"⚡️ *Сонет вышел на пятно: тяжёлая операция ({name})*"
                    )
                    tier = "sonnet"
                    set_current_tier(tier)
                    logger.info("tier→sonnet: heavy tool {}", name)

        # Execute the calls.
        for tc in msg.tool_calls:
            name = tc.function.name
            args_json = tc.function.arguments or "{}"
            logger.info(
                "tool_call tier={} name={} args={}", tier, name, args_json[:200]
            )
            result = await execute_tool(name, args_json)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                }
            )

        # Post-scan: Haiku might have asked to escalate.
        sig = consume_escalation_signal()
        if sig and sig.get("target") == "sonnet" and tier == "haiku":
            reason = sig.get("reason") or "запрос модели"
            announcements.append(f"⚡️ *Сонет вышел на пятно: {reason}*")
            tier = "sonnet"
            set_current_tier(tier)
            logger.info("tier→sonnet: self-escalation ({})", reason)

        # Hop-count escalation — long chains of tool calls.
        if (
            tier == "haiku"
            and hop + 1 >= settings.escalation_hop_threshold
        ):
            announcements.append(
                "⚡️ *Сонет вышел на пятно: длинная цепочка инструментов*"
            )
            tier = "sonnet"
            set_current_tier(tier)
            logger.info("tier→sonnet: hop threshold reached")
    else:
        hit_limit = True
        logger.warning(
            "hit max_tool_hops={} without final answer", settings.max_tool_hops
        )
        try:
            response = await client.chat_complete(
                tier=tier,
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
            final_text = "Запутался в цепочке шагов — " + _summarize_progress(messages)

    if not final_text:
        final_text = "(пустой ответ)"
    final_text = _strip_markdown(final_text)

    # --- Auto-rollback ---------------------------------------------------
    # If user manually forced Sonnet and this turn was simple (no heavy tools,
    # ≤2 hops), increment streak. After N streaks in a row → unforce and announce.
    if forced_active:
        if not used_heavy and hops_done <= 2:
            streak = int(state.get("sonnet_simple_streak", "0") or "0") + 1
            await db_state.set_value(
                chat_id, "sonnet_simple_streak", str(streak)
            )
            if streak >= settings.auto_rollback_simple_turns:
                await db_state.clear(chat_id, "forced_model")
                await db_state.clear(chat_id, "sonnet_simple_streak")
                announcements.append(
                    f"🪄 *Хайку вышел на пятно: на Sonnet {streak} простых ходов "
                    f"подряд, откатываюсь обратно. Скажи «на сонет» когда нужно.*"
                )
                logger.info("auto-rollback: forced_model cleared after {} streak", streak)
        else:
            await db_state.clear(chat_id, "sonnet_simple_streak")

    if hit_limit:
        logger.info("returned soft fallback (hit limit, len={})", len(final_text))

    files = collect_files()
    if files:
        logger.info("turn produced {} file(s) to ship", len(files))

    return final_text, files, announcements
