"""Typed agent proposal endpoints with approval and rollback controls."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core import proposals
from draftpilot.core.db import async_get_db
from draftpilot.core.proposals import ProposalCreateRequest
from draftpilot.crud import agent_proposals as proposals_crud
from draftpilot.crud import projects as projects_crud
from draftpilot.models import AgentProposalRead

router = APIRouter(prefix="/projects/{project_id}/agent-proposals", tags=["agent"])


@router.get("", response_model=list[AgentProposalRead])
async def list_agent_proposals(
    project_id: int, session: AsyncSession = Depends(async_get_db)
) -> list[AgentProposalRead]:
    """List proposals scoped to one project."""
    if await projects_crud.get(session, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return [AgentProposalRead.model_validate(proposal) for proposal in await proposals_crud.list_for_project(session, project_id)]


@router.post("", response_model=AgentProposalRead, status_code=status.HTTP_201_CREATED)
async def create_agent_proposal(
    project_id: int, data: ProposalCreateRequest, session: AsyncSession = Depends(async_get_db)
) -> AgentProposalRead:
    """Persist a proposal after deriving its target version server-side."""
    return await proposals.create_proposal(session, project_id, data)


@router.post("/{proposal_id}/approve", response_model=AgentProposalRead)
async def approve_agent_proposal(
    project_id: int, proposal_id: int, session: AsyncSession = Depends(async_get_db)
) -> AgentProposalRead:
    """Apply a typed proposal only when its target version is unchanged."""
    return await proposals.approve(session, project_id, proposal_id)


@router.post("/{proposal_id}/reject", response_model=AgentProposalRead)
async def reject_agent_proposal(
    project_id: int, proposal_id: int, session: AsyncSession = Depends(async_get_db)
) -> AgentProposalRead:
    """Reject a pending proposal without touching its target."""
    return await proposals.reject(session, project_id, proposal_id)


@router.post("/{proposal_id}/rollback", response_model=AgentProposalRead)
async def rollback_agent_proposal(
    project_id: int, proposal_id: int, session: AsyncSession = Depends(async_get_db)
) -> AgentProposalRead:
    """Rollback an approved proposal as a new versioned target mutation."""
    return await proposals.rollback(session, project_id, proposal_id)
