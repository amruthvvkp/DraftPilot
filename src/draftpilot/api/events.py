"""Server-Sent Events stream of one project's committed changes."""

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core import events
from draftpilot.core.db import async_get_db
from draftpilot.crud import projects as projects_crud

router = APIRouter(prefix="/projects/{project_id}/events", tags=["events"])


async def _stream(request: Request, project_id: int) -> AsyncIterator[str]:
    """Encode project events as SSE frames with heartbeat comments while idle."""
    yield "retry: 3000\n\n"
    async for event in events.subscribe(project_id):
        if await request.is_disconnected():
            break
        if event is None:
            yield ": keep-alive\n\n"
            continue
        yield f"event: {event['kind']}\ndata: {json.dumps(event, default=str)}\n\n"


@router.get("")
async def stream_project_events(
    project_id: int, request: Request, session: AsyncSession = Depends(async_get_db)
) -> StreamingResponse:
    """Stream committed changes so the studio updates when agents or MCP clients edit."""
    if await projects_crud.get(session, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    await session.close()
    return StreamingResponse(
        _stream(request, project_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
