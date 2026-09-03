"""CRUD operations for typed agent proposals."""

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.models import AgentProposal


async def create(session: AsyncSession, proposal: AgentProposal) -> AgentProposal:
    """Persist a proposed agent operation."""
    session.add(proposal)
    await session.commit()
    await session.refresh(proposal)
    return proposal


async def get(session: AsyncSession, proposal_id: int) -> AgentProposal | None:
    """Return a proposal by identifier."""
    return await session.get(AgentProposal, proposal_id)


async def list_for_project(session: AsyncSession, project_id: int) -> list[AgentProposal]:
    """Return project proposals newest first."""
    result = await session.exec(
        select(AgentProposal)
        .where(AgentProposal.project_id == project_id)
        .order_by(col(AgentProposal.created_at).desc())
    )
    return list(result.all())
