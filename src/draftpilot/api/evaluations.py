"""Project-scoped evaluation result endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.db import async_get_db
from draftpilot.core.queue import get_arq_pool
from draftpilot.crud import evaluations as evaluations_crud
from draftpilot.crud import projects as projects_crud
from draftpilot.crud import screenplays as screenplays_crud
from draftpilot.crud import workflow_runs as runs_crud
from draftpilot.models import (
    EvaluationResult,
    EvaluationResultCreate,
    EvaluationResultRead,
    WorkflowRunCreate,
    WorkflowRunRead,
)

router = APIRouter(prefix="/projects/{project_id}/evaluations", tags=["evaluations"])


class EvaluationRunRequest(BaseModel):
    """Describe a deterministic evaluation run for one project screenplay."""

    screenplay_id: int = Field(ge=1)
    evaluator: str = Field(default="deterministic_review", min_length=1, max_length=100)
    max_attempts: int = Field(default=3, ge=1, le=10)


@router.post("/runs", response_model=WorkflowRunRead, status_code=status.HTTP_202_ACCEPTED)
async def start_evaluation(
    project_id: int,
    data: EvaluationRunRequest,
    session: AsyncSession = Depends(async_get_db),
) -> WorkflowRunRead:
    """Persist and enqueue a project-scoped screenplay evaluation."""
    project = await projects_crud.get(session, project_id)
    screenplay = await screenplays_crud.get(session, data.screenplay_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if screenplay is None or screenplay.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screenplay not found")
    run = await runs_crud.create(
        session,
        WorkflowRunCreate(
            project_id=project_id,
            kind="evaluation",
            input={"screenplay_id": data.screenplay_id, "evaluator": data.evaluator},
            agent_role="audience_evaluator",
            max_attempts=data.max_attempts,
        ),
    )
    await (await get_arq_pool()).enqueue_job("execute_workflow", run.id)
    return WorkflowRunRead.model_validate(run)


@router.get("", response_model=list[EvaluationResultRead])
async def list_evaluations(
    project_id: int, session: AsyncSession = Depends(async_get_db)
) -> list[EvaluationResultRead]:
    """Return persisted evaluation results for one project."""
    if await projects_crud.get(session, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    results = await evaluations_crud.list_for_project(session, project_id)
    return [EvaluationResultRead.model_validate(result) for result in results]


@router.post("", response_model=EvaluationResultRead, status_code=status.HTTP_201_CREATED)
async def create_evaluation(
    project_id: int,
    data: EvaluationResultCreate,
    session: AsyncSession = Depends(async_get_db),
) -> EvaluationResultRead:
    """Persist a typed evaluation result for an existing project."""
    if await projects_crud.get(session, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    result = await evaluations_crud.create(
        session, EvaluationResult(project_id=project_id, **data.model_dump())
    )
    return EvaluationResultRead.model_validate(result)
