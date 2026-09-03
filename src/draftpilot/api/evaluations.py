"""Project-scoped evaluation result endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.db import async_get_db
from draftpilot.crud import evaluations as evaluations_crud
from draftpilot.crud import projects as projects_crud
from draftpilot.models import EvaluationResult, EvaluationResultCreate, EvaluationResultRead

router = APIRouter(prefix="/projects/{project_id}/evaluations", tags=["evaluations"])


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
