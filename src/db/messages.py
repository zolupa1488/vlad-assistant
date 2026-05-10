"""CRUD for chat history (sliding-window context)."""

from sqlalchemy import desc, select

from src.config import settings
from src.db.models import Message
from src.db.session import SessionLocal


async def append(*, chat_id: int, user_id: int, role: str, text: str) -> None:
    async with SessionLocal() as s:
        s.add(Message(chat_id=chat_id, user_id=user_id, role=role, text=text))
        await s.commit()


async def recent(chat_id: int, limit: int | None = None) -> list[dict]:
    """Return last N messages for the chat in chronological order, formatted as
    OpenAI-API-style dicts: {"role": ..., "content": ...}."""
    n = limit or settings.max_history_messages
    async with SessionLocal() as s:
        rows = (
            await s.execute(
                select(Message)
                .where(Message.chat_id == chat_id)
                .order_by(desc(Message.created_at))
                .limit(n)
            )
        ).scalars().all()
    rows.reverse()
    return [{"role": m.role, "content": m.text} for m in rows]
