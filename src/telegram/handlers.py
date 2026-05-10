"""Handler: text + voice + document → Claude tool-use → reply (text + optional files)."""

from __future__ import annotations

import os
import tempfile

from loguru import logger

from src.brain.tool_use_loop import respond
from src.config import settings
from src.db import messages as messages_db
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
                await adapter.send_document(chat_id=chat_id, file_path=path, caption=name)
        except Exception:
            logger.exception("failed to ship file {}", path)


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
        # The user's question is in caption (or text if also sent), parsed file is context
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

    is_owner = user_id == settings.owner_telegram_user_id
    logger.info(
        "incoming user_id={} chat_id={} owner={} {}{}text={!r}",
        user_id,
        chat_id,
        is_owner,
        voice_marker,
        file_marker,
        composed_text[:200],
    )

    history = await messages_db.recent(chat_id)
    # Save the human-readable form (without giant file dump) to history.
    history_text = (voice_marker + file_marker + (caption or text or "")).strip() or composed_text[:500]
    await messages_db.append(
        chat_id=chat_id, user_id=user_id, role="user", text=history_text
    )

    await adapter.set_typing(chat_id)
    try:
        reply, files = await respond(
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

    await adapter.send_message(chat_id, reply)
    if files:
        await _ship_files(adapter, chat_id, files)

    await messages_db.append(
        chat_id=chat_id, user_id=0, role="assistant", text=reply
    )
