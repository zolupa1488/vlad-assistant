"""Entry point for Vlad Assistant (Phase 0 — echo)."""

from __future__ import annotations

import asyncio
import sys

from loguru import logger

from src.config import settings
from src.telegram.bot_api_adapter import BotApiAdapter
from src.telegram.handlers import handle_message


def _configure_logging() -> None:
    logger.remove()
    logger.add(sys.stdout, level="INFO", enqueue=True)


async def main() -> None:
    _configure_logging()
    logger.info(
        "Vlad Assistant starting (Phase 0 — echo). owner_id={}",
        settings.owner_telegram_user_id,
    )

    adapter = BotApiAdapter()
    adapter.on_message(handle_message)

    try:
        await adapter.start()
    finally:
        await adapter.stop()


if __name__ == "__main__":
    asyncio.run(main())
