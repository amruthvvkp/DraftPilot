"""Canonical screenplay export endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.db import async_get_db
from draftpilot.core.screenplay.adapters.fdx import render_fdx
from draftpilot.core.screenplay.adapters.fountain import render_fountain
from draftpilot.core.screenplay.hydrate import load_screenplay_doc
from draftpilot.crud import projects as projects_crud
from draftpilot.crud import screenplays as screenplays_crud

router = APIRouter(prefix="/projects/{project_id}/screenplays/{screenplay_id}/exports", tags=["exports"])


@router.get("/{file_format}", response_class=PlainTextResponse)
async def export_screenplay(
    project_id: int,
    screenplay_id: int,
    file_format: str,
    session: AsyncSession = Depends(async_get_db),
) -> PlainTextResponse:
    """Export canonical screenplay data as Fountain or FDX without mutation."""
    project = await projects_crud.get(session, project_id)
    screenplay = await screenplays_crud.get(session, screenplay_id)
    if project is None or screenplay is None or screenplay.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screenplay not found")
    if file_format not in {"fountain", "fdx"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported export format")
    document = await load_screenplay_doc(session, screenplay_id)
    if file_format == "fountain":
        content = render_fountain(document)
        media_type = "text/plain"
        filename = f"{screenplay.title}.fountain"
    else:
        content = render_fdx(document)
        media_type = "application/xml"
        filename = f"{screenplay.title}.fdx"
    return PlainTextResponse(
        content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
