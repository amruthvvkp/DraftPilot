"""Project resource endpoints for the DraftPilot API."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.db import async_get_db
from draftpilot.crud import acts as acts_crud
from draftpilot.crud import blocks as blocks_crud
from draftpilot.crud import project_references as references_crud
from draftpilot.crud import projects as projects_crud
from draftpilot.crud import scenes as scenes_crud
from draftpilot.crud import screenplays as screenplays_crud
from draftpilot.models import (
    ActRead,
    BlockRead,
    ProjectCreate,
    ProjectRead,
    ProjectReferenceBase,
    ProjectReferenceRead,
    SceneRead,
    ScreenplayRead,
)

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectWorkspaceRead(BaseModel):
    """Aggregate project context needed to render the screenplay workspace."""

    project: ProjectRead
    screenplay: ScreenplayRead | None
    acts: list[ActRead]
    scenes: list[SceneRead]
    blocks: dict[int, list[BlockRead]] = Field(default_factory=dict)


class ProjectReferenceInput(BaseModel):
    """Capture a typed reference before the server assigns its project."""

    kind: str = "other"
    label: str = Field(min_length=1, max_length=300)
    url: str | None = Field(default=None, max_length=1000)
    note: str | None = Field(default=None, max_length=1000)


class ProjectCreateRequest(ProjectCreate):
    """Accept a project brief together with typed creative references."""

    references: list[ProjectReferenceInput] = Field(default_factory=list)


class ProjectReadWithReferences(ProjectRead):
    """Return project metadata and its persisted creative references."""

    references: list[ProjectReferenceRead] = Field(default_factory=list)


@router.get("", response_model=list[ProjectRead])
async def list_projects(session: AsyncSession = Depends(async_get_db)) -> list[ProjectRead]:
    """Return all projects ordered by title."""
    projects = await projects_crud.list_all(session)
    return [ProjectRead.model_validate(project) for project in projects]


@router.post("", response_model=ProjectReadWithReferences, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: ProjectCreateRequest, session: AsyncSession = Depends(async_get_db)
) -> ProjectReadWithReferences:
    """Create and return a project from the submitted creative brief."""
    project = await projects_crud.create_with_references(
        session,
        ProjectCreate.model_validate(data),
        [ProjectReferenceBase.model_validate(reference) for reference in data.references],
    )
    references = await references_crud.list_for_project(session, project.id or 0)
    return ProjectReadWithReferences(
        **ProjectRead.model_validate(project).model_dump(),
        references=[ProjectReferenceRead.model_validate(reference) for reference in references],
    )


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
    blocks: dict[int, list[BlockRead]] = {}
    if screenplay is not None and screenplay.id is not None:
        acts = await acts_crud.list_for_screenplay(session, screenplay.id)
        scenes = await scenes_crud.list_for_screenplay(session, screenplay.id)
        for scene in scenes:
            if scene.id is not None:
                scene_blocks = await blocks_crud.list_for_scene(session, scene.id)
                blocks[scene.id] = [BlockRead.model_validate(block) for block in scene_blocks]
    return ProjectWorkspaceRead(
        project=ProjectRead.model_validate(project),
        screenplay=ScreenplayRead.model_validate(screenplay) if screenplay else None,
        acts=[ActRead.model_validate(act) for act in acts],
        scenes=[SceneRead.model_validate(scene) for scene in scenes],
        blocks=blocks,
    )
