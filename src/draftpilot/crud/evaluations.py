"""CRUD operations for project evaluation results."""

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.models import EvaluationResult


async def create(session: AsyncSession, result: EvaluationResult) -> EvaluationResult:
    """Persist one evaluation result."""
    session.add(result)
    await session.commit()
    await session.refresh(result)
    return result


async def list_for_project(session: AsyncSession, project_id: int) -> list[EvaluationResult]:
    """Return project evaluations newest first."""
    query = select(EvaluationResult).where(EvaluationResult.project_id == project_id).order_by(
        col(EvaluationResult.created_at).desc()
    )
    result = await session.exec(query)
    return list(result.all())
