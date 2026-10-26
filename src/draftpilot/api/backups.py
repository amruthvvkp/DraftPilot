"""Project-scoped backup and non-destructive restore endpoints."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.backup import (
    BackupError,
    BackupManifest,
    read_backup,
    write_backup,
)
from draftpilot.core.config import settings
from draftpilot.core.db import async_get_db
from draftpilot.core.project_backup import (
    enqueue_restored_documents,
    project_payload,
    restore_payload,
)
from draftpilot.crud import projects as projects_crud

router = APIRouter(prefix="/projects/{project_id}/backups", tags=["backups"])


class BackupRead(BaseModel):
    """Return a backup filename and its integrity manifest."""

    filename: str
    manifest: BackupManifest


@router.post("", response_model=BackupRead, status_code=status.HTTP_201_CREATED)
async def create_backup(project_id: int, session: AsyncSession = Depends(async_get_db)) -> BackupRead:
    """Create an atomic backup of supported project content."""
    project = await projects_crud.get(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    filename, manifest = write_backup(
        settings.backup.root,
        project_id,
        await project_payload(session, project_id),
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
        project = await restore_payload(session, payload)
    except (KeyError, TypeError, ValueError) as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid backup payload") from exc
    if project.id is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Restored project has no identifier")
    await enqueue_restored_documents(session, project.id)
    if await projects_crud.get(session, project_id) is None:
        # A deleted project was recovered: stop offering it under "recently deleted".
        (Path(settings.backup.root) / f"{filename}.restored").write_text(str(project.id))
    return {"project_id": project.id}
