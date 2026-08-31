"""Project resource endpoints for the DraftPilot API."""

from fastapi import APIRouter, Depends, status
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.db import async_get_db
from draftpilot.crud import projects as projects_crud
from draftpilot.models import ProjectCreate, ProjectRead

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectRead])
async def list_projects(session: AsyncSession = Depends(async_get_db)) -> list[ProjectRead]:
    """Return all projects ordered by title."""
    projects = await projects_crud.list_all(session)
    return [ProjectRead.model_validate(project) for project in projects]


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: ProjectCreate, session: AsyncSession = Depends(async_get_db)
) -> ProjectRead:
    """Create and return a project from the submitted creative brief."""
    project = await projects_crud.create(session, data)
    return ProjectRead.model_validate(project)
