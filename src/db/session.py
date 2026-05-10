"""Async SQLAlchemy engine + session factory."""

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from src.config import settings
from src.db.models import Base

engine: AsyncEngine = create_async_engine(settings.database_url, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    """Create tables if they don't exist (Phase 1: no Alembic yet)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
