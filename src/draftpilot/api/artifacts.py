"""Versioned project story-artifact endpoints."""

from datetime import datetime, timezone

import logfire
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.db import async_get_db
from draftpilot.core.queue import get_arq_pool
from draftpilot.crud import projects as projects_crud
from draftpilot.crud import story_artifacts as artifacts_crud
from draftpilot.models import StoryArtifact, StoryArtifactRead

router = APIRouter(prefix="/projects/{project_id}/artifacts", tags=["artifacts"])


async def _enqueue_index(project_id: int, artifact: StoryArtifact) -> None:
    """Queue an artifact refresh without rolling back the committed artifact."""
    try:
        await (await get_arq_pool()).enqueue_job(
            "index_rag_document",
            {
                "project_id": project_id,
                "source_id": f"artifact:{artifact.id}",
                "source_kind": artifact.kind,
                "text": artifact.content,
                "content_version": artifact.version,
            },
        )
    except Exception as exc:  # pragma: no cover - queue availability varies by deployment
        logfire.warning("RAG indexing enqueue skipped: {exc}", exc=str(exc))


class ArtifactCreateRequest(BaseModel):
    """Describe a new editable story-development artifact."""

    kind: str = Field(max_length=40)
    title: str = Field(min_length=1, max_length=200)
    content: str = ""
    depends_on: list[int] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


class ArtifactUpdateRequest(BaseModel):
    """Describe an optimistic artifact edit."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = None
    depends_on: list[int] | None = None
    metadata: dict[str, object] | None = None
    stale: bool | None = None


async def _validate_dependencies(
    session: AsyncSession,
    project_id: int,
    artifact_id: int | None,
    dependencies: list[int],
) -> None:
    """Reject missing, cross-project, self-referential, or cyclic dependencies."""
    if len(dependencies) != len(set(dependencies)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Artifact dependencies must be unique",
        )
    artifacts = await artifacts_crud.list_for_project(session, project_id)
    by_id = {artifact.id: artifact for artifact in artifacts if artifact.id is not None}
    missing = set(dependencies) - set(by_id)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Artifact dependencies must belong to this project",
        )
    if artifact_id is not None and artifact_id in dependencies:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="An artifact cannot depend on itself",
        )
    if artifact_id is None:
        return
    graph = {identifier: list(artifact.depends_on) for identifier, artifact in by_id.items()}
    graph[artifact_id] = dependencies
    pending = list(dependencies)
    visited: set[int] = set()
    while pending:
        dependency_id = pending.pop()
        if dependency_id == artifact_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Artifact dependencies cannot contain cycles",
            )
        if dependency_id in visited:
            continue
        visited.add(dependency_id)
        pending.extend(graph.get(dependency_id, []))


@router.get("", response_model=list[StoryArtifactRead])
async def list_artifacts(
    project_id: int, session: AsyncSession = Depends(async_get_db)
) -> list[StoryArtifactRead]:
    """List editable artifacts within project scope."""
    if await projects_crud.get(session, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    artifacts = await artifacts_crud.list_for_project(session, project_id)
    return [StoryArtifactRead.model_validate(artifact) for artifact in artifacts]


@router.post("", response_model=StoryArtifactRead, status_code=status.HTTP_201_CREATED)
async def create_artifact(
    project_id: int,
    data: ArtifactCreateRequest,
    session: AsyncSession = Depends(async_get_db),
) -> StoryArtifactRead:
    """Create an editable project artifact without overwriting another artifact."""
    if await projects_crud.get(session, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    await _validate_dependencies(session, project_id, None, data.depends_on)
    values = data.model_dump()
    values["artifact_metadata"] = values.pop("metadata")
    artifact = StoryArtifact(project_id=project_id, **values)
    session.add(artifact)
    await session.commit()
    await session.refresh(artifact)
    await _enqueue_index(project_id, artifact)
    return StoryArtifactRead.model_validate(artifact)


@router.patch("/{artifact_id}", response_model=StoryArtifactRead)
async def update_artifact(
    project_id: int,
    artifact_id: int,
    data: ArtifactUpdateRequest,
    session: AsyncSession = Depends(async_get_db),
    if_match: int | None = Header(default=None, alias="If-Match"),
) -> StoryArtifactRead:
    """Edit an artifact and mark its dependent artifacts stale."""
    artifact = await artifacts_crud.get(session, artifact_id)
    if artifact is None or artifact.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    if if_match is None:
        raise HTTPException(status_code=status.HTTP_428_PRECONDITION_REQUIRED, detail="If-Match is required")
    if if_match != artifact.version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Artifact has changed")
    changes = data.model_dump(exclude_unset=True)
    if "depends_on" in changes:
        await _validate_dependencies(session, project_id, artifact_id, changes["depends_on"])
    if "metadata" in changes:
        changes["artifact_metadata"] = changes.pop("metadata")
    for key, value in changes.items():
        setattr(artifact, key, value)
    artifact.version += 1
    artifact.stale = False
    artifact.updated_at = datetime.now(timezone.utc)
    session.add(artifact)
    await artifacts_crud.mark_dependents_stale(session, project_id, [artifact_id])
    await session.commit()
    await session.refresh(artifact)
    await _enqueue_index(project_id, artifact)
    return StoryArtifactRead.model_validate(artifact)
