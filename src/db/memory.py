"""Long-term pinned facts — full-text search via SQL LIKE for now.

Phase 3 will swap LIKE for vector search via Qdrant + sentence-transformers,
but the same tools (`remember` / `recall` / `forget`) keep their interface.
"""

from __future__ import annotations

from sqlalchemy import delete, desc, or_, select

from src.db.models import Memory
from src.db.session import SessionLocal


async def add(chat_id: int, fact: str) -> int:
    fact = fact.strip()
    if not fact:
        return 0
    async with SessionLocal() as s:
        m = Memory(chat_id=chat_id, fact=fact)
        s.add(m)
        await s.commit()
        await s.refresh(m)
        return m.id


async def list_recent(chat_id: int, limit: int = 5) -> list[str]:
    async with SessionLocal() as s:
        rows = (
            await s.execute(
                select(Memory)
                .where(Memory.chat_id == chat_id)
                .order_by(desc(Memory.created_at))
                .limit(limit)
            )
        ).scalars().all()
    return [r.fact for r in rows]


async def search(chat_id: int, query: str, limit: int = 10) -> list[str]:
    """Naive substring search across all words of the query (OR-joined)."""
    words = [w.lower().strip() for w in query.split() if len(w.strip()) > 2]
    if not words:
        return await list_recent(chat_id, limit)
    async with SessionLocal() as s:
        conditions = [Memory.fact.ilike(f"%{w}%") for w in words]
        rows = (
            await s.execute(
                select(Memory)
                .where(Memory.chat_id == chat_id)
                .where(or_(*conditions))
                .order_by(desc(Memory.created_at))
                .limit(limit)
            )
        ).scalars().all()
    return [r.fact for r in rows]


async def delete_matching(chat_id: int, query: str) -> int:
    """Delete memories that match the query (substring across query words)."""
    matches = await search(chat_id, query, limit=100)
    if not matches:
        return 0
    async with SessionLocal() as s:
        # delete by exact fact text — there may be duplicates, that's ok
        result = await s.execute(
            delete(Memory)
            .where(Memory.chat_id == chat_id)
            .where(Memory.fact.in_(matches))
        )
        await s.commit()
        return result.rowcount or 0
