"""Async SQLModel engine and session helpers for the local SQLite app DB."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from pauth.config import settings

engine = create_async_engine(
    f"sqlite+aiosqlite:///{settings.app_db_path}",
    echo=False,
)
# expire_on_commit=False keeps attributes usable after the request session closes.
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    """Create the data directories and all SQLModel tables if missing."""
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields one async session per request."""
    async with SessionLocal() as session:
        yield session
