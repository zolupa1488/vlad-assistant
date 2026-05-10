"""Handler: voice → Whisper → Claude tool-use → reply."""

from __future__ import annotations

import os
import tempfile

from loguru import logger

from src.brain.tool_use_loop import respond
from src.config import settings
from src.db import messages as messages_db
from src.telegram.adapter import IncomingMessage, TelegramAdapter
from src.voice.transcriber import transcribe_file


async def _transcribe_voice(adapter: TelegramAdapter, file_id: str) -> str:
    """Download a voice file and run it through Whisper."""
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


async def handle_message(adapter: TelegramAdapter, message: IncomingMessage) -> None:
    user_id = message.user_id
    chat_id = message.chat_id
    text = (message.text or "").strip()
    voice_marker = ""

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

    if not text:
        await adapter.send_message(
            chat_id,
            "Понимаю текст и голосовые. Картинки и файлы — в следующих фазах.",
        )
        return

    is_owner = user_id == settings.owner_telegram_user_id
    logger.info(
        "incoming user_id={} chat_id={} owner={} {}text={!r}",
        user_id,
        chat_id,
        is_owner,
        voice_marker,
        text[:200],
    )

    history = await messages_db.recent(chat_id)
    await messages_db.append(
        chat_id=chat_id, user_id=user_id, role="user", text=voice_marker + text
    )

    await adapter.set_typing(chat_id)
    try:
        reply = await respond(user_text=voice_marker + text, is_owner=is_owner, history=history)
    except Exception as e:
        logger.exception("brain failed")
        reply = (
            "Прости, что-то сломалось внутри. Попробуй ещё раз через минуту.\n\n"
            f"(debug: {type(e).__name__})"
        )

    await adapter.send_message(chat_id, reply)
    await messages_db.append(
        chat_id=chat_id, user_id=0, role="assistant", text=reply
    )
