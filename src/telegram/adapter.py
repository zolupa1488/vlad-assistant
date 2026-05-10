"""Abstract Telegram I/O contract.

Phase I: BotApiAdapter (aiogram) — see `bot_api_adapter.py`.
Phase II: TelethonAdapter (MTProto userbot) — to be added in Phase 9.

Business logic only depends on this interface; the rest of the codebase
must NOT import aiogram or telethon directly.
"""

from __future__ import annotations

from typing import Awaitable, Callable, Protocol


class IncomingMessage(Protocol):
    """Channel-agnostic view of an incoming message."""

    @property
    def chat_id(self) -> int: ...
    @property
    def user_id(self) -> int: ...
    @property
    def text(self) -> str | None: ...
    @property
    def voice_file_id(self) -> str | None: ...


MessageHandler = Callable[["TelegramAdapter", IncomingMessage], Awaitable[None]]


class TelegramAdapter(Protocol):
    """Abstract Telegram client used by handlers and outbound actions."""

    async def start(self) -> None: ...
    async def stop(self) -> None: ...

    async def send_message(self, chat_id: int, text: str) -> None: ...
    async def set_typing(self, chat_id: int) -> None: ...

    async def download_file(self, file_id: str, dest_path: str) -> None:
        """Download an arbitrary Telegram file to disk."""

    async def send_document(self, chat_id: int, file_path: str, caption: str | None = None) -> None:
        """Send a local file as a Telegram document."""

    async def send_photo(self, chat_id: int, file_path: str, caption: str | None = None) -> None:
        """Send a local image file as a Telegram photo."""

    def on_message(self, handler: MessageHandler) -> None: ...
