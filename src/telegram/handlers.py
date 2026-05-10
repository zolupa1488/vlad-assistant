"""Phase 0 echo handler.

In later phases this becomes the router that dispatches to brain/RAG/actions.
"""

from __future__ import annotations

from loguru import logger

from src.config import settings
from src.telegram.adapter import IncomingMessage, TelegramAdapter

OWNER_GREETING = "Привет, Владимир, я тебя слышу."
STRANGER_GREETING = "Привет! Это автоответчик Vlad Assistant."


async def handle_message(adapter: TelegramAdapter, message: IncomingMessage) -> None:
    user_id = message.user_id
    chat_id = message.chat_id
    text = message.text or "<non-text>"

    is_owner = user_id == settings.owner_telegram_user_id
    logger.info(
        "incoming user_id={} chat_id={} owner={} text={!r}",
        user_id,
        chat_id,
        is_owner,
        text,
    )

    reply = OWNER_GREETING if is_owner else STRANGER_GREETING

    await adapter.set_typing(chat_id)
    await adapter.send_message(chat_id=chat_id, text=reply)
