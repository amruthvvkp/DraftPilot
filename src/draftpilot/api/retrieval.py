"""Project retrieval endpoints: hybrid search, index health, and full re-index."""

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.config import settings
from draftpilot.core.copilot import retrieve_context
from draftpilot.core.db import async_get_db
from draftpilot.core.queue import enqueue_best_effort
from draftpilot.crud import projects as projects_crud

router = APIRouter(prefix="/projects/{project_id}/rag", tags=["retrieval"])


class ReindexResponse(BaseModel):
    """Report whether a full re-index was queued."""

    queued: bool


async def _require_project(session: AsyncSession, project_id: int) -> None:
    """Raise 404 when the project does not exist."""
    if await projects_crud.get(session, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@router.get("/search")
async def search(
    project_id: int, q: str, session: AsyncSession = Depends(async_get_db)
) -> list[dict[str, object]]:
    """Hybrid-search the project (scenes, story artifacts, canon, references)."""
    await _require_project(session, project_id)
    return await retrieve_context(project_id, q)


@router.get("/stats")
async def stats(project_id: int, session: AsyncSession = Depends(async_get_db)) -> dict[str, int]:
    """Report how many of the project's documents and chunks are indexed and embedded."""
    await _require_project(session, project_id)
    url = f"{settings.rag.service_url.rstrip('/')}/projects/{project_id}/stats"
    headers = {"Authorization": f"Bearer {settings.rag.auth_token.get_secret_value()}"}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return dict(response.json())
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Retrieval service unavailable") from exc


@router.post("/reindex", response_model=ReindexResponse, status_code=status.HTTP_202_ACCEPTED)
async def reindex(project_id: int, session: AsyncSession = Depends(async_get_db)) -> ReindexResponse:
    """Queue a full re-index of the project's scenes, artifacts, canon, and references."""
    await _require_project(session, project_id)
    queued = await enqueue_best_effort("reindex_project", project_id, description="Project reindex enqueue")
    return ReindexResponse(queued=queued)
