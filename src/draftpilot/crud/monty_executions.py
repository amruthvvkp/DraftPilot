"""CRUD operations for redacted Monty execution records."""

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.models import MontyExecution, MontyExecutionCreate


async def create(session: AsyncSession, data: MontyExecutionCreate) -> MontyExecution:
    """Create a redacted Monty execution audit record."""
    record = MontyExecution.model_validate(data)
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


async def list_for_project(session: AsyncSession, project_id: int) -> list[MontyExecution]:
    """Return project Monty records newest first."""
    result = await session.exec(
        select(MontyExecution)
        .where(MontyExecution.project_id == project_id)
        .order_by(col(MontyExecution.created_at).desc())
    )
    return list(result.all())
