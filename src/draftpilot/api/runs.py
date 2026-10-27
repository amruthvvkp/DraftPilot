"""Versioned workflow-run endpoints for durable execution and reconnection."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core import temporal
from draftpilot.core.agent_roles import AgentRoleKey, PermissionMode
from draftpilot.core.db import async_get_db
from draftpilot.crud import projects as projects_crud
from draftpilot.crud import screenplays as screenplays_crud
from draftpilot.crud import workflow_runs as runs_crud
from draftpilot.models import WorkflowRunCreate, WorkflowRunRead

router = APIRouter(prefix="/projects/{project_id}/runs", tags=["runs"])


class RunCreateRequest(BaseModel):
    """Accept a typed workflow request from the UI or an approved client."""

    kind: str = Field(default="screenplay_analysis", max_length=80)
    screenplay_id: int
    agent_role: AgentRoleKey = "story_architect"
    permission_mode: PermissionMode = "chat_only"
    max_attempts: int = Field(default=3, ge=1, le=10)


@router.post("", response_model=WorkflowRunRead, status_code=status.HTTP_202_ACCEPTED)
async def start_run(
    project_id: int,
    data: RunCreateRequest,
    session: AsyncSession = Depends(async_get_db),
) -> WorkflowRunRead:
    """Persist and enqueue a project-scoped workflow run."""
    project = await projects_crud.get(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    screenplay = await screenplays_crud.get(session, data.screenplay_id)
    if screenplay is None or screenplay.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screenplay not found")
    run = await runs_crud.create(
        session,
        WorkflowRunCreate(
            project_id=project_id,
            kind=data.kind,
            input={"screenplay_id": data.screenplay_id},
            agent_role=data.agent_role,
            permission_mode=data.permission_mode,
            max_attempts=data.max_attempts,
        ),
    )
    await temporal.start_run(run.id)
    return WorkflowRunRead.model_validate(run)


@router.get("", response_model=list[WorkflowRunRead])
async def list_runs(
    project_id: int, session: AsyncSession = Depends(async_get_db)
) -> list[WorkflowRunRead]:
    """List durable runs for a project."""
    project = await projects_crud.get(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    runs = await runs_crud.list_for_project(session, project_id)
    return [WorkflowRunRead.model_validate(run) for run in runs]


@router.get("/{run_id}", response_model=WorkflowRunRead)
async def get_run(
    project_id: int, run_id: int, session: AsyncSession = Depends(async_get_db)
) -> WorkflowRunRead:
    """Return a run only within its project scope."""
    run = await runs_crud.get(session, run_id)
    if run is None or run.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return WorkflowRunRead.model_validate(run)


@router.post("/{run_id}/resume", response_model=WorkflowRunRead, status_code=status.HTTP_202_ACCEPTED)
async def resume_run(
    project_id: int, run_id: int, session: AsyncSession = Depends(async_get_db)
) -> WorkflowRunRead:
    """Requeue a non-terminal or failed run for worker resumption."""
    run = await runs_crud.get(session, run_id)
    if run is None or run.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    if run.status in {"succeeded", "cancelled"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Run is terminal")
    run.status = "queued"
    run.attempt_count = 0
    run.error = None
    session.add(run)
    await session.commit()
    await session.refresh(run)
    await temporal.start_run(run.id)
    return WorkflowRunRead.model_validate(run)


@router.post("/{run_id}/cancel", response_model=WorkflowRunRead)
async def cancel_run(
    project_id: int, run_id: int, session: AsyncSession = Depends(async_get_db)
) -> WorkflowRunRead:
    """Cancel a queued or running project workflow without deleting its history."""
    run = await runs_crud.get(session, run_id)
    if run is None or run.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    if run.status in {"succeeded", "failed", "cancelled"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Run is already terminal")
    await runs_crud.update_status(session, run, "cancelled")
    await temporal.cancel_run(run_id)
    return WorkflowRunRead.model_validate(run)
