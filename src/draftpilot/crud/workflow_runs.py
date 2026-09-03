"""CRUD operations for durable workflow runs."""

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.models import WorkflowRun, WorkflowRunCreate
from draftpilot.models.base import _utcnow


async def create(session: AsyncSession, data: WorkflowRunCreate) -> WorkflowRun:
    """Create a queued workflow run."""
    run = WorkflowRun.model_validate(data)
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def get(session: AsyncSession, run_id: int) -> WorkflowRun | None:
    """Return a workflow run by identifier."""
    return await session.get(WorkflowRun, run_id)


async def list_for_project(session: AsyncSession, project_id: int) -> list[WorkflowRun]:
    """Return project runs newest first."""
    result = await session.exec(
        select(WorkflowRun)
        .where(WorkflowRun.project_id == project_id)
        .order_by(col(WorkflowRun.created_at).desc())
    )
    return list(result.all())


async def update_status(
    session: AsyncSession,
    run: WorkflowRun,
    status: str,
    result: dict[str, object] | None = None,
    error: str | None = None,
) -> WorkflowRun:
    """Persist a workflow transition and its result or error."""
    run.status = status
    run.result = result
    run.error = error
    run.updated_at = _utcnow()
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run
