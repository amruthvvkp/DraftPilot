"""Versioned timeline proposal and approval endpoints."""

from fastapi import APIRouter, Depends, status
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core import timeline_proposals
from draftpilot.core.db import async_get_db
from draftpilot.core.timeline_proposals import TimelineProposalRequest
from draftpilot.models import TimelineProposalRead

router = APIRouter(
    prefix="/projects/{project_id}/screenplays/{screenplay_id}/timeline/proposals",
    tags=["timeline"],
)


@router.post("", response_model=TimelineProposalRead, status_code=status.HTTP_201_CREATED)
async def create_timeline_proposal(
    project_id: int, screenplay_id: int, data: TimelineProposalRequest, session: AsyncSession = Depends(async_get_db)
) -> TimelineProposalRead:
    """Persist a validated reorder proposal without changing scene order."""
    return await timeline_proposals.create(session, project_id, screenplay_id, data)


@router.get("", response_model=list[TimelineProposalRead])
async def list_timeline_proposals(
    project_id: int, screenplay_id: int, session: AsyncSession = Depends(async_get_db)
) -> list[TimelineProposalRead]:
    """List timeline proposals within project and screenplay scope."""
    return await timeline_proposals.list_for_screenplay(session, project_id, screenplay_id)


@router.post("/{proposal_id}/approve", response_model=TimelineProposalRead)
async def approve_timeline_proposal(
    project_id: int, screenplay_id: int, proposal_id: int, session: AsyncSession = Depends(async_get_db)
) -> TimelineProposalRead:
    """Apply a proposal only when its original scene order is still current."""
    return await timeline_proposals.approve(session, project_id, screenplay_id, proposal_id)


@router.post("/{proposal_id}/reject", response_model=TimelineProposalRead)
async def reject_timeline_proposal(
    project_id: int, screenplay_id: int, proposal_id: int, session: AsyncSession = Depends(async_get_db)
) -> TimelineProposalRead:
    """Reject a pending proposal without changing screenplay scenes."""
    return await timeline_proposals.reject(session, project_id, screenplay_id, proposal_id)


@router.post("/{proposal_id}/rollback", response_model=TimelineProposalRead)
async def rollback_timeline_proposal(
    project_id: int, screenplay_id: int, proposal_id: int, session: AsyncSession = Depends(async_get_db)
) -> TimelineProposalRead:
    """Restore the original scene order from an approved reorder proposal."""
    return await timeline_proposals.rollback(session, project_id, screenplay_id, proposal_id)
