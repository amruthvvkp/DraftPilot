"""Project resource endpoints for the DraftPilot API."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.db import async_get_db
from draftpilot.crud import acts as acts_crud
from draftpilot.crud import projects as projects_crud
from draftpilot.crud import scenes as scenes_crud
from draftpilot.crud import screenplays as screenplays_crud
from draftpilot.models import ActRead, ProjectCreate, ProjectRead, SceneRead, ScreenplayRead

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectWorkspaceRead(BaseModel):
    """Aggregate project context needed to render the screenplay workspace."""

    project: ProjectRead
    screenplay: ScreenplayRead | None
    acts: list[ActRead]
    scenes: list[SceneRead]


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


@router.get("/{project_id}/workspace", response_model=ProjectWorkspaceRead)
async def get_project_workspace(
    project_id: int, session: AsyncSession = Depends(async_get_db)
) -> ProjectWorkspaceRead:
    """Return the project and its ordered screenplay context for the editor."""
    project = await projects_crud.get(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    screenplays = await screenplays_crud.list_for_project(session, project_id)
    screenplay = screenplays[0] if screenplays else None
    acts = []
    scenes = []
    if screenplay is not None and screenplay.id is not None:
        acts = await acts_crud.list_for_screenplay(session, screenplay.id)
        scenes = await scenes_crud.list_for_screenplay(session, screenplay.id)
    return ProjectWorkspaceRead(
        project=ProjectRead.model_validate(project),
        screenplay=ScreenplayRead.model_validate(screenplay) if screenplay else None,
        acts=[ActRead.model_validate(act) for act in acts],
        scenes=[SceneRead.model_validate(scene) for scene in scenes],
    )
