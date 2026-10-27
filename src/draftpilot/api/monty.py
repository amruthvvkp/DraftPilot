"""Versioned endpoints for project-scoped Monty audit records."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.db import async_get_db
from draftpilot.crud import monty_executions as executions_crud
from draftpilot.crud import projects as projects_crud
from draftpilot.models import MontyExecutionRead

router = APIRouter(prefix="/projects/{project_id}/monty-executions", tags=["monty"])


@router.get("", response_model=list[MontyExecutionRead])
async def list_monty_executions(
    project_id: int, session: AsyncSession = Depends(async_get_db)
) -> list[MontyExecutionRead]:
    """Return redacted Monty audit records for one project."""
    if await projects_crud.get(session, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    records = await executions_crud.list_for_project(session, project_id)
    return [MontyExecutionRead.model_validate(record) for record in records]
