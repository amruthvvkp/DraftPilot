"""Project-scoped backup and non-destructive restore endpoints."""

from pathlib import Path
from typing import Any

import logfire
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.backup import BackupError, BackupManifest, read_backup, write_backup
from draftpilot.core.config import settings
from draftpilot.core.db import async_get_db
from draftpilot.core.queue import get_arq_pool
from draftpilot.core.screenplay.hydrate import load_screenplay_doc, save_screenplay_doc
from draftpilot.core.screenplay.schema import ScreenplayDoc
from draftpilot.crud import project_references as references_crud
from draftpilot.crud import projects as projects_crud
from draftpilot.crud import screenplays as screenplays_crud
from draftpilot.crud import story_artifacts as artifacts_crud
from draftpilot.models import Project, ProjectCreate, ProjectReference, Screenplay, StoryArtifact

router = APIRouter(prefix="/projects/{project_id}/backups", tags=["backups"])


class BackupRead(BaseModel):
    """Return a backup filename and its integrity manifest."""

    filename: str
    manifest: BackupManifest


async def _enqueue_restored_artifacts(session: AsyncSession, project_id: int) -> None:
    """Queue restored artifacts for incremental project-scoped indexing."""
    try:
        pool = await get_arq_pool()
        for artifact in await artifacts_crud.list_for_project(session, project_id):
            if artifact.id is None:
                continue
            await pool.enqueue_job(
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
        logfire.warning("Restored artifact indexing enqueue skipped: {exc}", exc=str(exc))


async def _project_payload(session: AsyncSession, project_id: int) -> dict[str, Any]:
    """Serialize supported project content without database identifiers."""
    project = await projects_crud.get(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    references = await references_crud.list_for_project(session, project_id)
    artifacts = await artifacts_crud.list_for_project(session, project_id)
    screenplays = await screenplays_crud.list_for_project(session, project_id)
    screenplay_payload: list[dict[str, Any]] = []
    for screenplay in screenplays:
        if screenplay.id is not None:
            screenplay_payload.append(
                {
                    "title": screenplay.title,
                    "format": screenplay.format,
                    "status": screenplay.status,
                    "document": (await load_screenplay_doc(session, screenplay.id)).model_dump(mode="json"),
                }
            )
    return {
        "project": ProjectCreate.model_validate(project).model_dump(mode="json"),
        "references": [ProjectReference.model_validate(reference).model_dump(mode="json") for reference in references],
        "artifacts": [
            {
                "backup_id": artifact.id,
                "kind": artifact.kind,
                "title": artifact.title,
                "content": artifact.content,
                "version": artifact.version,
                "stale": artifact.stale,
                "depends_on": artifact.depends_on,
                "artifact_metadata": artifact.artifact_metadata,
            }
            for artifact in artifacts
        ],
        "screenplays": screenplay_payload,
    }


async def restore_backup_payload(session: AsyncSession, payload: dict[str, Any]) -> Project:
    """Restore validated backup content into a new project without overwriting existing data."""
    project = Project.model_validate(ProjectCreate.model_validate(payload["project"]))
    session.add(project)
    await session.flush()
    assert project.id is not None
    for reference in payload.get("references", []):
        session.add(ProjectReference(project_id=project.id, **reference))
    artifact_ids: dict[int, int] = {}
    pending_dependencies: list[tuple[StoryArtifact, list[int]]] = []
    for artifact in payload.get("artifacts", []):
        values = dict(artifact)
        backup_id = values.pop("backup_id", None)
        dependencies = values.pop("depends_on", [])
        restored = StoryArtifact(
            project_id=project.id,
            depends_on=[],
            **values,
        )
        session.add(restored)
        await session.flush()
        if isinstance(backup_id, int) and restored.id is not None:
            artifact_ids[backup_id] = restored.id
        if isinstance(dependencies, list):
            pending_dependencies.append((restored, [item for item in dependencies if isinstance(item, int)]))
    for restored, dependencies in pending_dependencies:
        restored.depends_on = [artifact_ids[item] for item in dependencies if item in artifact_ids]
        session.add(restored)
    await session.commit()
    for screenplay_data in payload.get("screenplays", []):
        screenplay = Screenplay(
            project_id=project.id,
            title=screenplay_data["title"],
            format=screenplay_data["format"],
            status=screenplay_data["status"],
        )
        session.add(screenplay)
        await session.flush()
        assert screenplay.id is not None
        await save_screenplay_doc(
            session,
            screenplay.id,
            ScreenplayDoc.model_validate(screenplay_data["document"]),
            commit=False,
        )
    await session.commit()
    return project


@router.post("", response_model=BackupRead, status_code=status.HTTP_201_CREATED)
async def create_backup(project_id: int, session: AsyncSession = Depends(async_get_db)) -> BackupRead:
    """Create an atomic backup of supported project content."""
    project = await projects_crud.get(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    filename, manifest = write_backup(
        settings.backup.root,
        project_id,
        await _project_payload(session, project_id),
        settings.metadata.version,
        project.title,
    )
    return BackupRead(filename=filename, manifest=manifest)


@router.get("", response_model=list[BackupRead])
async def list_backups(project_id: int) -> list[BackupRead]:
    """List valid backups for the requested project only."""
    results: list[BackupRead] = []
    if not settings.backup.root.exists():
        return results
    for path in sorted(settings.backup.root.glob("*.json.gz")):
        try:
            envelope = read_backup(settings.backup.root, path.name)
        except BackupError:
            continue
        if envelope.manifest.project_id == project_id:
            results.append(BackupRead(filename=path.name, manifest=envelope.manifest))
    return results


@router.get("/{filename}")
async def download_backup(project_id: int, filename: str) -> FileResponse:
    """Download a validated backup belonging to the requested project."""
    try:
        envelope = read_backup(settings.backup.root, filename)
    except BackupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup not found") from exc
    if envelope.manifest.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup not found")
    return FileResponse(Path(settings.backup.root) / filename, media_type="application/gzip", filename=filename)


@router.post("/{filename}/restore", response_model=dict[str, int], status_code=status.HTTP_201_CREATED)
async def restore_backup(
    project_id: int, filename: str, session: AsyncSession = Depends(async_get_db)
) -> dict[str, int]:
    """Restore a backup into a new project without overwriting existing data."""
    try:
        envelope = read_backup(settings.backup.root, filename)
    except BackupError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid backup") from exc
    if envelope.manifest.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup not found")
    payload = envelope.payload
    try:
        project = await restore_backup_payload(session, payload)
    except (KeyError, TypeError, ValueError) as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid backup payload") from exc
    if project.id is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Restored project has no identifier")
    await _enqueue_restored_artifacts(session, project.id)
    return {"project_id": project.id}
