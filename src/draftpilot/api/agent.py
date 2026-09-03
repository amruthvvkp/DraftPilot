"""Typed agent proposal endpoints with approval and rollback controls."""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.db import async_get_db
from draftpilot.crud import agent_proposals as proposals_crud
from draftpilot.crud import acts as acts_crud
from draftpilot.crud import projects as projects_crud
from draftpilot.crud import scenes as scenes_crud
from draftpilot.crud import story_artifacts as artifacts_crud
from draftpilot.crud import screenplays as screenplays_crud
from draftpilot.models import AgentProposal, AgentProposalRead

router = APIRouter(prefix="/projects/{project_id}/agent-proposals", tags=["agent"])


class ProposalCreateRequest(BaseModel):
    """Describe a typed, reviewable operation proposed by an agent."""

    target_kind: str = Field(pattern="^(scene|artifact)$")
    target_id: int
    operation: dict[str, Any] = Field(min_length=1)
    diff: dict[str, Any] = Field(default_factory=dict)
    base_version: int = Field(ge=1)
    run_id: int | None = None


async def _scene_in_project(
    session: AsyncSession, project_id: int, scene_id: int
) -> Any | None:
    """Return a scene in the requested project or ``None``."""
    scene = await scenes_crud.get(session, scene_id)
    act = await acts_crud.get(session, scene.act_id) if scene else None
    screenplay = await screenplays_crud.get(session, act.screenplay_id) if act else None
    if scene is None or screenplay is None or screenplay.project_id != project_id:
        return None
    return scene


@router.get("", response_model=list[AgentProposalRead])
async def list_agent_proposals(
    project_id: int, session: AsyncSession = Depends(async_get_db)
) -> list[AgentProposalRead]:
    """List proposals scoped to one project."""
    if await projects_crud.get(session, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    proposals = await proposals_crud.list_for_project(session, project_id)
    return [AgentProposalRead.model_validate(proposal) for proposal in proposals]


@router.post("", response_model=AgentProposalRead, status_code=status.HTTP_201_CREATED)
async def create_agent_proposal(
    project_id: int,
    data: ProposalCreateRequest,
    session: AsyncSession = Depends(async_get_db),
) -> AgentProposalRead:
    """Persist a proposal after deriving its target version server-side."""
    target: Any | None
    if data.target_kind == "scene":
        target = await _scene_in_project(session, project_id, data.target_id)
    else:
        target = await artifacts_crud.get(session, data.target_id)
        if target is not None and target.project_id != project_id:
            target = None
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal target not found")
    version = getattr(target, "version", None)
    if version != data.base_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Proposal target has changed")
    before = data.operation.keys() & {"title", "content", "depends_on", "artifact_metadata", "heading", "body"}
    snapshot = {key: getattr(target, key) for key in before}
    proposal = await proposals_crud.create(
        session,
        AgentProposal(
            project_id=project_id,
            run_id=data.run_id,
            target_kind=data.target_kind,
            target_id=data.target_id,
            operation=data.operation,
            diff=data.diff,
            before=snapshot,
            base_version=data.base_version,
        ),
    )
    return AgentProposalRead.model_validate(proposal)


@router.post("/{proposal_id}/approve", response_model=AgentProposalRead)
async def approve_agent_proposal(
    project_id: int, proposal_id: int, session: AsyncSession = Depends(async_get_db)
) -> AgentProposalRead:
    """Apply a typed proposal only when its target version is unchanged."""
    proposal = await proposals_crud.get(session, proposal_id)
    if proposal is None or proposal.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
    if proposal.status != "proposed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Proposal is not pending")
    target: Any | None
    if proposal.target_kind == "scene":
        target = await _scene_in_project(session, project_id, proposal.target_id)
    else:
        target = await artifacts_crud.get(session, proposal.target_id)
        if target is not None and target.project_id != project_id:
            target = None
    if target is None or getattr(target, "version", None) != proposal.base_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Proposal target has changed")
    operation = proposal.operation
    allowed = {"title", "content", "depends_on", "artifact_metadata", "heading", "body"}
    if set(operation) - allowed:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported typed operation")
    for key, value in operation.items():
        setattr(target, key, value)
    target.version += 1
    session.add(target)
    if proposal.target_kind == "artifact":
        await artifacts_crud.mark_dependents_stale(session, project_id, [proposal.target_id])
    proposal.status = "approved"
    proposal.updated_at = datetime.now(timezone.utc)
    session.add(proposal)
    await session.commit()
    await session.refresh(proposal)
    return AgentProposalRead.model_validate(proposal)


@router.post("/{proposal_id}/rollback", response_model=AgentProposalRead)
async def rollback_agent_proposal(
    project_id: int, proposal_id: int, session: AsyncSession = Depends(async_get_db)
) -> AgentProposalRead:
    """Rollback an approved proposal as a new versioned target mutation."""
    proposal = await proposals_crud.get(session, proposal_id)
    if proposal is None or proposal.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
    if proposal.status != "approved":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Proposal is not approved")
    target: Any | None
    if proposal.target_kind == "scene":
        target = await _scene_in_project(session, project_id, proposal.target_id)
    else:
        target = await artifacts_crud.get(session, proposal.target_id)
        if target is not None and target.project_id != project_id:
            target = None
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal target not found")
    for key, value in proposal.before.items():
        setattr(target, key, value)
    target.version += 1
    session.add(target)
    proposal.status = "rolled_back"
    proposal.updated_at = datetime.now(timezone.utc)
    session.add(proposal)
    await session.commit()
    await session.refresh(proposal)
    return AgentProposalRead.model_validate(proposal)
