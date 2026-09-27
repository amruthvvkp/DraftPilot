"""Async database engine, session factory, and FastAPI dependency.

A single async engine is created from the configured Postgres DSN. Use
``async_get_db`` as a FastAPI dependency or ``session_scope`` as a
context manager inside background tasks.
"""

from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager, contextmanager

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


async def async_get_db() -> AsyncGenerator[AsyncSession]:
    """Yield a database session (FastAPI ``Depends`` compatible)."""
    async with async_session_factory() as session:
        yield session


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession]:
    """Transactional session context for use outside request handlers."""
    async with async_session_factory() as session:
        yield session


@contextmanager
def bound_to(engine: AsyncEngine) -> Iterator[None]:
    """Point every ``session_scope``/``async_get_db`` session at another engine (evals use an isolated database)."""
    global async_session_factory
    previous = async_session_factory
    async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)
    try:
        yield
    finally:
        async_session_factory = previous


async def dispose_engine() -> None:
    """Dispose the engine connection pool on shutdown."""
    await async_engine.dispose()
