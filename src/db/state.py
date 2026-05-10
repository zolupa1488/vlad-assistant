"""Per-chat session state — small key/value store."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.db.models import SessionState
from src.db.session import SessionLocal


async def get_all(chat_id: int) -> dict[str, str]:
    async with SessionLocal() as s:
        rows = (
            await s.execute(
                select(SessionState).where(SessionState.chat_id == chat_id)
            )
        ).scalars().all()
    return {r.key: r.value for r in rows}


async def set_value(chat_id: int, key: str, value: str) -> None:
    """Upsert (chat_id, key) → value."""
    async with SessionLocal() as s:
        # Upsert pattern — works on SQLite via INSERT OR REPLACE; for Postgres
        # we'd switch to ON CONFLICT DO UPDATE.
        stmt = sqlite_insert(SessionState).values(
            chat_id=chat_id, key=key, value=value
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["chat_id", "key"],
            set_={"value": stmt.excluded.value},
        )
        await s.execute(stmt)
        await s.commit()


async def clear(chat_id: int, key: str) -> None:
    async with SessionLocal() as s:
        await s.execute(
            delete(SessionState).where(
                SessionState.chat_id == chat_id, SessionState.key == key
            )
        )
        await s.commit()


async def clear_all(chat_id: int) -> None:
    async with SessionLocal() as s:
        await s.execute(delete(SessionState).where(SessionState.chat_id == chat_id))
        await s.commit()
