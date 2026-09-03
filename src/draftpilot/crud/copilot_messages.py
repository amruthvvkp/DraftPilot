"""CRUD operations for project-scoped Copilot messages."""

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.models import CopilotMessage, CopilotMessageCreate


async def list_for_project(session: AsyncSession, project_id: int, limit: int = 100) -> list[CopilotMessage]:
    """Return the most recent Copilot messages in chronological order."""
    result = await session.exec(
        select(CopilotMessage)
        .where(CopilotMessage.project_id == project_id)
        .order_by(col(CopilotMessage.created_at).desc())
        .limit(limit)
    )
    return list(reversed(result.all()))


async def create(session: AsyncSession, data: CopilotMessageCreate) -> CopilotMessage:
    """Persist and return one Copilot message."""
    message = CopilotMessage.model_validate(data)
    session.add(message)
    await session.commit()
    await session.refresh(message)
    return message
