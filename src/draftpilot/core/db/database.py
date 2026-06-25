"""Async database engine, session factory, and FastAPI dependency.

A single async engine is created from the configured Postgres DSN. Use
``async_get_db`` as a NiceGUI/FastAPI dependency or ``session_scope`` as a
context manager inside background tasks.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.config import settings

async_engine: AsyncEngine = create_async_engine(
    settings.postgres.async_dsn,
    echo=False,
    pool_pre_ping=True,
)

async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def async_get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session (FastAPI ``Depends`` compatible)."""
    async with async_session_factory() as session:
        yield session


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Transactional session context for use outside request handlers."""
    async with async_session_factory() as session:
        yield session


async def create_db_and_tables() -> None:
    """Create all tables for local/dev bootstrap (Alembic owns production)."""
    # Import models so every table is registered on SQLModel.metadata.
    from sqlmodel import SQLModel

    import draftpilot.models  # noqa: F401

    async with async_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def dispose_engine() -> None:
    """Dispose the engine connection pool on shutdown."""
    await async_engine.dispose()
