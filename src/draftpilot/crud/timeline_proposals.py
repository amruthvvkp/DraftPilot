"""CRUD operations for reviewable timeline proposals."""

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.models import TimelineProposalRecord


async def create(session: AsyncSession, proposal: TimelineProposalRecord) -> TimelineProposalRecord:
    """Persist a proposed timeline reorder."""
    session.add(proposal)
    await session.commit()
    await session.refresh(proposal)
    return proposal


async def get(session: AsyncSession, proposal_id: int) -> TimelineProposalRecord | None:
    """Return a timeline proposal by identifier."""
    return await session.get(TimelineProposalRecord, proposal_id)


async def list_for_screenplay(
    session: AsyncSession, screenplay_id: int
) -> list[TimelineProposalRecord]:
    """Return screenplay proposals newest first."""
    result = await session.exec(
        select(TimelineProposalRecord)
        .where(TimelineProposalRecord.screenplay_id == screenplay_id)
        .order_by(col(TimelineProposalRecord.created_at).desc())
    )
    return list(result.all())
