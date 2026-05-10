"""Entry point for Vlad Assistant (Phase 1 — Claude tool-use)."""

from __future__ import annotations

import asyncio
import sys

from loguru import logger

from src.config import settings
from src.db.session import init_db
from src.telegram.bot_api_adapter import BotApiAdapter
from src.telegram.handlers import handle_message


def _configure_logging() -> None:
    logger.remove()
    logger.add(sys.stdout, level="INFO", enqueue=True)


async def main() -> None:
    _configure_logging()
    logger.info(
        "Vlad Assistant starting (Phase 1 — Claude tool-use). owner_id={}",
        settings.owner_telegram_user_id,
    )

    await init_db()

    adapter = BotApiAdapter()
    adapter.on_message(handle_message)

    try:
        await adapter.start()
    finally:
        await adapter.stop()


if __name__ == "__main__":
    asyncio.run(main())
