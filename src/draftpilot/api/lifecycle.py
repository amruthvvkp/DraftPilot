"""Project lifecycle endpoints: delete (backed up first), duplicate, and recover deleted projects."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.api.backups import (
    _enqueue_restored_artifacts,
    _project_payload,
    restore_backup_payload,
)
from draftpilot.core import events
from draftpilot.core.db import async_get_db
from draftpilot.core.project_lifecycle import (
    delete_project,
    deleted_project_backups,
    dismiss_deleted_project,
)
from draftpilot.core.queue import enqueue_best_effort
from draftpilot.crud import projects as projects_crud
from draftpilot.models import ProjectRead

router = APIRouter(prefix="/projects", tags=["projects"])


class DuplicateRequest(BaseModel):
    """Name the copy (defaults to "<title> (copy)")."""

    title: str | None = Field(default=None, min_length=1, max_length=200)


@router.get("/deleted")
async def list_deleted_projects(session: AsyncSession = Depends(async_get_db)) -> list[dict[str, Any]]:
    """List deleted projects that can still be restored from their last backup."""
    return [
        {"project_id": item["manifest"].project_id, "title": item["title"], "filename": item["filename"],
         "deleted_at": item["manifest"].created_at.isoformat()}
        for item in await deleted_project_backups(session)
    ]


@router.post("/deleted/{project_id}/dismiss")
async def dismiss_deleted(project_id: int, session: AsyncSession = Depends(async_get_db)) -> dict[str, int]:
    """Hide a deleted project from "Recently deleted" (its backups remain on disk)."""
    if await projects_crud.get(session, project_id) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project still exists")
    return {"hidden": dismiss_deleted_project(project_id)}


@router.delete("/{project_id}")
async def delete_project_route(project_id: int, session: AsyncSession = Depends(async_get_db)) -> dict[str, Any]:
    """Back up and delete a project with everything in it; restore it later from the backup."""
    payload = await _project_payload(session, project_id)
    try:
        result = await delete_project(session, project_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found") from exc
    await enqueue_best_effort("purge_rag_project", project_id, description="RAG project purge enqueue")
    await events.publish(project_id, "project.deleted", {"backup": result["backup"]})
    return result


@router.post("/{project_id}/duplicate", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def duplicate_project(
    project_id: int, data: DuplicateRequest | None = None, session: AsyncSession = Depends(async_get_db)
) -> ProjectRead:
    """Copy a project's brief, references, artifacts and every draft into a new project."""
    payload = await _project_payload(session, project_id)
    payload["project"]["title"] = (data.title if data and data.title else f"{payload['project']['title']} (copy)")[:200]
    project = await restore_backup_payload(session, payload)
    await _enqueue_restored_artifacts(session, project.id or 0)
    await enqueue_best_effort("reindex_project", project.id, description="RAG reindex enqueue")
    await enqueue_best_effort("refresh_story_twin", project.id, description="Story twin refresh enqueue")
    return ProjectRead.model_validate(project)
