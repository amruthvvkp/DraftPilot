"""Canonical screenplay export endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse, Response
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.benchmark import (
    BenchmarkManifest,
    BenchmarkTrack,
    manifest_from_document,
    source_digest,
)
from draftpilot.core.db import async_get_db
from draftpilot.core.screenplay.adapters.fdx import parse_fdx, render_fdx
from draftpilot.core.screenplay.adapters.fountain import parse_fountain, render_fountain
from draftpilot.core.screenplay.adapters.pdf import parse_pdf
from draftpilot.core.screenplay.html import render_html
from draftpilot.core.screenplay.hydrate import load_screenplay_doc, save_screenplay_doc
from draftpilot.core.screenplay.pdf import render_pdf
from draftpilot.crud import projects as projects_crud
from draftpilot.crud import screenplays as screenplays_crud
from draftpilot.models import ScreenplayCreate, ScreenplayRead

router = APIRouter(prefix="/projects/{project_id}/screenplays/{screenplay_id}", tags=["exports"])
MAX_IMPORT_BYTES = 10 * 1024 * 1024


@router.get("/benchmark-manifest", response_model=BenchmarkManifest)
async def benchmark_manifest(
    project_id: int,
    screenplay_id: int,
    track: BenchmarkTrack = Query(default="redevelopment"),
    session: AsyncSession = Depends(async_get_db),
) -> BenchmarkManifest:
    """Build an isolated benchmark manifest from a project screenplay."""
    project = await projects_crud.get(session, project_id)
    screenplay = await screenplays_crud.get(session, screenplay_id)
    if project is None or screenplay is None or screenplay.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screenplay not found")
    document = await load_screenplay_doc(session, screenplay_id)
    return manifest_from_document(
        document,
        track=track,
        label=f"{track}-project-{project_id}-screenplay-{screenplay_id}",
        primary_language=project.primary_language,
        translation_languages=project.languages,
        source_sha256=screenplay.source_sha256,
    )


@router.get("/exports/{file_format}", response_class=PlainTextResponse)
async def export_screenplay(
    project_id: int,
    screenplay_id: int,
    file_format: str,
    session: AsyncSession = Depends(async_get_db),
) -> Response:
    """Export canonical screenplay data as Fountain, FDX, HTML, or PDF without mutation."""
    project = await projects_crud.get(session, project_id)
    screenplay = await screenplays_crud.get(session, screenplay_id)
    if project is None or screenplay is None or screenplay.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screenplay not found")
    if file_format not in {"fountain", "fdx", "html", "pdf"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Unsupported export format")
    document = await load_screenplay_doc(session, screenplay_id)
    if file_format == "fountain":
        content = render_fountain(document)
        media_type = "text/plain"
        filename = f"{screenplay.title}.fountain"
    elif file_format == "fdx":
        content = render_fdx(document)
        media_type = "application/xml"
        filename = f"{screenplay.title}.fdx"
    elif file_format == "html":
        content = render_html(document)
        media_type = "text/html"
        filename = f"{screenplay.title}.html"
    else:
        return Response(
            render_pdf(document),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{screenplay.title}.pdf"'},
        )
    return PlainTextResponse(
        content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/imports/{file_format}", response_model=ScreenplayRead, status_code=status.HTTP_201_CREATED
)
async def import_screenplay(
    project_id: int,
    screenplay_id: int,
    file_format: str,
    request: Request,
    session: AsyncSession = Depends(async_get_db),
) -> ScreenplayRead:
    """Import Fountain or FDX into a new screenplay without replacing existing data."""
    if file_format not in {"fountain", "fdx", "pdf"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Unsupported import format")
    project = await projects_crud.get(session, project_id)
    source = await screenplays_crud.get(session, screenplay_id)
    if project is None or source is None or source.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screenplay not found")
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > MAX_IMPORT_BYTES:
                raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Import is too large")
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid content length") from exc
    raw = await request.body()
    if len(raw) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Import is too large")
    try:
        if file_format == "pdf":
            document = parse_pdf(raw)
        else:
            text = raw.decode("utf-8-sig")
            document = parse_fountain(text) if file_format == "fountain" else parse_fdx(text)
    except (UnicodeDecodeError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Malformed screenplay import") from exc
    imported = await screenplays_crud.create(
        session,
        ScreenplayCreate(
            project_id=project_id,
            title=f"{source.title} (Imported)"[:200],
            format=source.format,
            status="draft",
            source_sha256=source_digest(raw),
        ),
    )
    if imported.id is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Import could not be persisted")
    await save_screenplay_doc(session, imported.id, document)
    return ScreenplayRead.model_validate(imported)
