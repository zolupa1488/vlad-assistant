"""Phase I implementation of TelegramAdapter — aiogram + Bot API."""

from __future__ import annotations

from typing import Awaitable, Callable

from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.types import FSInputFile
from loguru import logger

from src.config import settings


class _AiogramMessageView:
    """Adapt aiogram's `types.Message` to our `IncomingMessage` Protocol."""

    def __init__(self, message: types.Message) -> None:
        self._m = message

    @property
    def chat_id(self) -> int:
        return self._m.chat.id

    @property
    def user_id(self) -> int:
        return self._m.from_user.id if self._m.from_user else 0

    @property
    def text(self) -> str | None:
        return self._m.text

    @property
    def voice_file_id(self) -> str | None:
        if self._m.voice:
            return self._m.voice.file_id
        if self._m.audio:
            return self._m.audio.file_id
        return None

    @property
    def raw(self) -> types.Message:
        return self._m


class BotApiAdapter:
    """aiogram-based adapter (Phase I)."""

    def __init__(self) -> None:
        self.bot = Bot(
            token=settings.telegram_bot_token,
            default=DefaultBotProperties(parse_mode="HTML"),
        )
        self.dp = Dispatcher()
        self._handler: Callable[..., Awaitable[None]] | None = None

    def on_message(self, handler: Callable[..., Awaitable[None]]) -> None:
        self._handler = handler

    async def start(self) -> None:
        if self._handler is None:
            raise RuntimeError("on_message handler is not registered")

        @self.dp.message()
        async def _route(message: types.Message) -> None:
            assert self._handler is not None
            await self._handler(self, _AiogramMessageView(message))

        me = await self.bot.get_me()
        logger.info("Started long polling as @{} (id={})", me.username, me.id)
        await self.dp.start_polling(self.bot)

    async def stop(self) -> None:
        await self.dp.stop_polling()
        await self.bot.session.close()

    async def send_message(self, chat_id: int, text: str) -> None:
        await self.bot.send_message(chat_id=chat_id, text=text)

    async def set_typing(self, chat_id: int) -> None:
        await self.bot.send_chat_action(chat_id=chat_id, action="typing")

    async def download_file(self, file_id: str, dest_path: str) -> None:
        file = await self.bot.get_file(file_id)
        await self.bot.download(file, destination=dest_path)

    async def send_document(self, chat_id: int, file_path: str, caption: str | None = None) -> None:
        await self.bot.send_document(
            chat_id=chat_id,
            document=FSInputFile(file_path),
            caption=caption,
        )

    async def send_photo(self, chat_id: int, file_path: str, caption: str | None = None) -> None:
        await self.bot.send_photo(
            chat_id=chat_id,
            photo=FSInputFile(file_path),
            caption=caption,
        )
