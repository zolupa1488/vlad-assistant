"""Handler: text + voice + document → Claude tool-use → reply (text + optional files).

Adds: (a) background typing-indicator that keeps the "печатает..." alive for the
entire duration of the LLM turn, and (b) manual model-tier switches via natural-
language commands ("переключи на сонет" / "вернись на хайку" / "/sonnet" / "/haiku").
"""

from __future__ import annotations

import asyncio
import os
import re
import tempfile
import time

from loguru import logger

# In-memory dedup of (chat_id, reply_text_prefix) → ts to prevent the same
# reply being shipped twice in a row inside ~5 seconds.
_recent_replies: dict[tuple[int, str], float] = {}
_DEDUP_WINDOW_S = 5.0


def _is_duplicate_reply(chat_id: int, text: str) -> bool:
    key = (chat_id, text[:120])
    now = time.time()
    for k, ts in list(_recent_replies.items()):
        if now - ts > _DEDUP_WINDOW_S:
            del _recent_replies[k]
    if key in _recent_replies:
        return True
    _recent_replies[key] = now
    return False

from src.brain.tool_use_loop import (
    SWITCH_TO_HAIKU_RE,
    SWITCH_TO_SONNET_RE,
    WHICH_MODEL_RE,
    respond,
)
from src.config import settings
from src.db import messages as messages_db
from src.db import state as db_state
from src.files.parser import parse_file
from src.telegram.adapter import IncomingMessage, TelegramAdapter
from src.voice.transcriber import transcribe_file


async def _transcribe_voice(adapter: TelegramAdapter, file_id: str) -> str:
    fd, tmp_path = tempfile.mkstemp(suffix=".ogg", dir="/app/data")
    os.close(fd)
    try:
        await adapter.download_file(file_id, tmp_path)
        return await transcribe_file(tmp_path, language="ru")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


async def _read_document(
    adapter: TelegramAdapter, file_id: str, file_name: str | None
) -> tuple[str, str]:
    """Return (filename_used, parsed_text)."""
    safe_name = file_name or "document"
    suffix = os.path.splitext(safe_name)[1] or ".bin"
    fd, tmp_path = tempfile.mkstemp(suffix=suffix, dir="/app/data")
    os.close(fd)
    try:
        await adapter.download_file(file_id, tmp_path)
        text = await parse_file(tmp_path, name_hint=safe_name)
        return safe_name, text
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


async def _ship_files(adapter: TelegramAdapter, chat_id: int, files: list[dict]) -> None:
    for f in files:
        path = f.get("path")
        kind = f.get("kind")
        name = f.get("name")
        if not path or not os.path.exists(path):
            continue
        try:
            if kind == "image":
                await adapter.send_photo(chat_id=chat_id, file_path=path, caption=name)
            else:
                await adapter.send_document(
                    chat_id=chat_id, file_path=path, caption=name
                )
        except Exception:
            logger.exception("failed to ship file {}", path)


async def _keep_typing(adapter: TelegramAdapter, chat_id: int) -> None:
    """Hold the Telegram 'typing...' indicator alive while the brain works.

    Telegram clears the typing chat-action after ~5 seconds. We refresh every
    4 seconds until the surrounding task cancels us.
    """
    try:
        while True:
            try:
                await adapter.set_typing(chat_id)
            except Exception:
                # Network blip — ignore, next tick will retry.
                pass
            await asyncio.sleep(4.0)
    except asyncio.CancelledError:
        raise


async def _handle_model_switch_commands(
    adapter: TelegramAdapter, chat_id: int, text: str
) -> bool:
    """Return True if the message was a meta-command and was handled here
    (no LLM call needed)."""
    if SWITCH_TO_SONNET_RE.search(text):
        await db_state.set_value(chat_id, "forced_model", "sonnet")
        await db_state.clear(chat_id, "sonnet_simple_streak")
        await adapter.send_message(
            chat_id, "⚡️ Понял, ставлю Sonnet 4. Скажи «вернись на хайку» когда хватит."
        )
        logger.info("manual switch → sonnet (chat_id={})", chat_id)
        return True
    if SWITCH_TO_HAIKU_RE.search(text):
        await db_state.clear(chat_id, "forced_model")
        await db_state.clear(chat_id, "sonnet_simple_streak")
        await adapter.send_message(chat_id, "🪄 Понял, возвращаюсь на Haiku 4.5.")
        logger.info("manual switch → haiku (chat_id={})", chat_id)
        return True
    return False


async def handle_message(adapter: TelegramAdapter, message: IncomingMessage) -> None:
    user_id = message.user_id
    chat_id = message.chat_id
    text = (message.text or "").strip()
    caption = (message.caption or "").strip()
    composed_text = ""
    voice_marker = ""
    file_marker = ""

    # ── Voice → Whisper ───────────────────────────────────────────
    if not text and message.voice_file_id:
        try:
            await adapter.set_typing(chat_id)
            transcribed = await _transcribe_voice(adapter, message.voice_file_id)
        except Exception as e:
            logger.exception("voice transcription failed")
            await adapter.send_message(
                chat_id, f"Не получилось распознать голосовое: {type(e).__name__}"
            )
            return
        if not transcribed:
            await adapter.send_message(
                chat_id, "Голосовое получилось пустое — повтори, пожалуйста."
            )
            return
        text = transcribed
        voice_marker = "[голосовое] "

    # ── Document → parser → text context ──────────────────────────
    if message.document_file_id:
        try:
            await adapter.set_typing(chat_id)
            fname, parsed = await _read_document(
                adapter, message.document_file_id, message.document_file_name
            )
        except Exception as e:
            logger.exception("document parsing failed")
            await adapter.send_message(
                chat_id, f"Не получилось прочитать файл: {type(e).__name__}: {e}"
            )
            return
        if not parsed.strip():
            await adapter.send_message(chat_id, f"Файл {fname} оказался пустым.")
            return
        file_marker = f"[файл: {fname}]\n"
        user_question = caption or text or "Прочитай этот файл и кратко расскажи о чём он."
        composed_text = (
            f"{voice_marker}{user_question}\n\n"
            f"--- содержимое файла {fname} ---\n{parsed}\n--- конец файла ---"
        )

    if not composed_text:
        composed_text = (voice_marker + (text or caption)).strip()

    if not composed_text:
        await adapter.send_message(
            chat_id, "Понимаю текст, голосовые и файлы (PDF/DOCX/XLSX/CSV/TXT)."
        )
        return

    # ── Manual model-tier switches (intercept before LLM) ─────────
    if await _handle_model_switch_commands(adapter, chat_id, composed_text):
        return

    is_owner = user_id == settings.owner_telegram_user_id
    logger.info(
        "incoming user_id={} chat_id={} owner={} {}{}text={!r}",
        user_id, chat_id, is_owner, voice_marker, file_marker,
        composed_text[:200],
    )

    history = await messages_db.recent(chat_id)
    history_text = (voice_marker + file_marker + (caption or text or "")).strip() or composed_text[:500]
    await messages_db.append(
        chat_id=chat_id, user_id=user_id, role="user", text=history_text
    )

    # Start the "печатает..." keep-alive in the background and run the brain.
    typing_task = asyncio.create_task(_keep_typing(adapter, chat_id))
    announcements: list[str] = []
    try:
        try:
            reply, files, announcements = await respond(
                user_text=composed_text,
                is_owner=is_owner,
                history=history,
                chat_id=chat_id,
            )
        except Exception as e:
            logger.exception("brain failed")
            reply = (
                "Прости, что-то сломалось внутри. Попробуй ещё раз через минуту.\n\n"
                f"(debug: {type(e).__name__})"
            )
            files = []
    finally:
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass

    # Tier-change announcements come first, separate from the main reply.
    for note in announcements:
        try:
            await adapter.send_message(chat_id, note)
        except Exception:
            logger.exception("failed to send tier announcement")

    if _is_duplicate_reply(chat_id, reply):
        logger.warning("dedup: dropping duplicate reply to chat_id={}", chat_id)
        return

    await adapter.send_message(chat_id, reply)
    if files:
        await _ship_files(adapter, chat_id, files)

    await messages_db.append(
        chat_id=chat_id, user_id=0, role="assistant", text=reply
    )
