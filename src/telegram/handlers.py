"""Phase 1 handler: Claude tool-use loop with sliding-window context."""

from __future__ import annotations

from loguru import logger

from src.brain.tool_use_loop import respond
from src.config import settings
from src.db import messages as messages_db
from src.telegram.adapter import IncomingMessage, TelegramAdapter


async def handle_message(adapter: TelegramAdapter, message: IncomingMessage) -> None:
    user_id = message.user_id
    chat_id = message.chat_id
    text = (message.text or "").strip()

    if not text:
        await adapter.send_message(
            chat_id, "Пока могу только текст. Голосовые научусь чуть позже."
        )
        return

    is_owner = user_id == settings.owner_telegram_user_id
    logger.info(
        "incoming user_id={} chat_id={} owner={} text={!r}",
        user_id,
        chat_id,
        is_owner,
        text[:200],
    )

    history = await messages_db.recent(chat_id)
    await messages_db.append(
        chat_id=chat_id, user_id=user_id, role="user", text=text
    )

    await adapter.set_typing(chat_id)
    try:
        reply = await respond(user_text=text, is_owner=is_owner, history=history)
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
