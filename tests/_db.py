"""In-memory SQLite sessions for tests that exercise real persistence logic."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

import draftpilot.models  # noqa: F401  (registers every table)


@asynccontextmanager
async def memory_session(url: str = "sqlite+aiosqlite://") -> AsyncIterator[AsyncSession]:
    """Yield a session on a fresh database (in-memory unless a file URL is given) with every table created."""
    engine = create_async_engine(url)

    @event.listens_for(engine.sync_engine, "connect")
    def _foreign_keys(dbapi_connection: object, _record: object) -> None:
        """Enforce foreign keys like Postgres does."""
        dbapi_connection.execute("PRAGMA foreign_keys=ON")  # type: ignore[attr-defined]

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
    await engine.dispose()
