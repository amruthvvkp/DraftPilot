"""Versioned timeline proposal and approval endpoints."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.db import async_get_db
from draftpilot.core.screenplay.timeline import propose_reorder
from draftpilot.crud import projects as projects_crud
from draftpilot.crud import scenes as scenes_crud
from draftpilot.crud import screenplays as screenplays_crud
from draftpilot.crud import story_artifacts as artifacts_crud
from draftpilot.crud import timeline_proposals as proposals_crud
from draftpilot.models import TimelineProposalRead, TimelineProposalRecord

router = APIRouter(
    prefix="/projects/{project_id}/screenplays/{screenplay_id}/timeline/proposals",
    tags=["timeline"],
)


class TimelineProposalRequest(BaseModel):
    """Describe a proposed scene order and its estimated durations."""

    scene_ids: list[int] = Field(min_length=1)
    durations: dict[int, int]


async def _scoped_screenplay(
    session: AsyncSession, project_id: int, screenplay_id: int
) -> bool:
    """Return whether a screenplay belongs to the requested project."""
    project = await projects_crud.get(session, project_id)
    screenplay = await screenplays_crud.get(session, screenplay_id)
    return project is not None and screenplay is not None and screenplay.project_id == project_id


@router.post("", response_model=TimelineProposalRead, status_code=status.HTTP_201_CREATED)
async def create_timeline_proposal(
    project_id: int,
    screenplay_id: int,
    data: TimelineProposalRequest,
    session: AsyncSession = Depends(async_get_db),
) -> TimelineProposalRead:
    """Persist a validated reorder proposal without changing scene order."""
    if not await _scoped_screenplay(session, project_id, screenplay_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screenplay not found")
    scenes = await scenes_crud.list_for_screenplay(session, screenplay_id)
    current_ids = [scene.id for scene in scenes if scene.id is not None]
    try:
        proposal = propose_reorder(current_ids, data.scene_ids, data.durations)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    record = await proposals_crud.create(
        session,
        TimelineProposalRecord(
            project_id=project_id,
            screenplay_id=screenplay_id,
            original_scene_ids=current_ids,
            proposed_scene_ids=proposal.scene_ids,
            timings=[timing.model_dump() for timing in proposal.timings],
            total_runtime_seconds=proposal.total_runtime_seconds,
        ),
    )
    return TimelineProposalRead.model_validate(record)


@router.get("", response_model=list[TimelineProposalRead])
async def list_timeline_proposals(
    project_id: int,
    screenplay_id: int,
    session: AsyncSession = Depends(async_get_db),
) -> list[TimelineProposalRead]:
    """List timeline proposals within project and screenplay scope."""
    if not await _scoped_screenplay(session, project_id, screenplay_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screenplay not found")
    proposals = await proposals_crud.list_for_screenplay(session, screenplay_id)
    return [TimelineProposalRead.model_validate(proposal) for proposal in proposals]


@router.post("/{proposal_id}/approve", response_model=TimelineProposalRead)
async def approve_timeline_proposal(
    project_id: int,
    screenplay_id: int,
    proposal_id: int,
    session: AsyncSession = Depends(async_get_db),
) -> TimelineProposalRead:
    """Apply a proposal only when its original scene order is still current."""
    proposal = await proposals_crud.get(session, proposal_id)
    if (
        proposal is None
        or proposal.project_id != project_id
        or proposal.screenplay_id != screenplay_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
    if proposal.status != "proposed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Proposal is not pending")
    scenes = await scenes_crud.list_for_screenplay(session, screenplay_id)
    current_ids = [scene.id for scene in scenes if scene.id is not None]
    if current_ids != proposal.original_scene_ids:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Screenplay order has changed")
    by_id = {scene.id: scene for scene in scenes}
    for position, scene_id in enumerate(proposal.proposed_scene_ids):
        scene = by_id[scene_id]
        scene.position = position
        scene.version += 1
        session.add(scene)
    timeline_artifacts = await artifacts_crud.list_for_project(session, project_id)
    timeline_ids = [
        artifact.id
        for artifact in timeline_artifacts
        if artifact.id is not None and artifact.kind == "timeline"
    ]
    if timeline_ids:
        await artifacts_crud.mark_dependents_stale(session, project_id, timeline_ids)
    proposal.status = "approved"
    proposal.updated_at = datetime.now(UTC)
    session.add(proposal)
    await session.commit()
    await session.refresh(proposal)
    return TimelineProposalRead.model_validate(proposal)


@router.post("/{proposal_id}/reject", response_model=TimelineProposalRead)
async def reject_timeline_proposal(
    project_id: int,
    screenplay_id: int,
    proposal_id: int,
    session: AsyncSession = Depends(async_get_db),
) -> TimelineProposalRead:
    """Reject a pending proposal without changing screenplay scenes."""
    proposal = await proposals_crud.get(session, proposal_id)
    if (
        proposal is None
        or proposal.project_id != project_id
        or proposal.screenplay_id != screenplay_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
    if proposal.status != "proposed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Proposal is not pending")
    proposal.status = "rejected"
    proposal.updated_at = datetime.now(UTC)
    session.add(proposal)
    await session.commit()
    await session.refresh(proposal)
    return TimelineProposalRead.model_validate(proposal)


@router.post("/{proposal_id}/rollback", response_model=TimelineProposalRead)
async def rollback_timeline_proposal(
    project_id: int,
    screenplay_id: int,
    proposal_id: int,
    session: AsyncSession = Depends(async_get_db),
) -> TimelineProposalRead:
    """Restore the original scene order from an approved reorder proposal."""
    proposal = await proposals_crud.get(session, proposal_id)
    if (
        proposal is None
        or proposal.project_id != project_id
        or proposal.screenplay_id != screenplay_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
    if proposal.status != "approved":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Proposal is not approved")
    scenes = await scenes_crud.list_for_screenplay(session, screenplay_id)
    current_ids = [scene.id for scene in scenes if scene.id is not None]
    if current_ids != proposal.proposed_scene_ids:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Screenplay order has changed")
    by_id = {scene.id: scene for scene in scenes}
    for position, scene_id in enumerate(proposal.original_scene_ids):
        scene = by_id[scene_id]
        scene.position = position
        scene.version += 1
        session.add(scene)
    timeline_artifacts = await artifacts_crud.list_for_project(session, project_id)
    timeline_ids = [
        artifact.id
        for artifact in timeline_artifacts
        if artifact.id is not None and artifact.kind == "timeline"
    ]
    if timeline_ids:
        await artifacts_crud.mark_dependents_stale(session, project_id, timeline_ids)
    proposal.status = "rolled_back"
    proposal.updated_at = datetime.now(UTC)
    session.add(proposal)
    await session.commit()
    await session.refresh(proposal)
    return TimelineProposalRead.model_validate(proposal)
