"""Side effects of a committed scene change: full-scene RAG refresh plus a live-sync event."""

from typing import Protocol

from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core import events
from draftpilot.core.queue import enqueue_best_effort
from draftpilot.core.screenplay.hydrate import blocks_for_scene, scene_text


class SceneLike(Protocol):
    """Describe the scene fields a change notification needs."""

    id: int | None
    heading: str
    version: int


async def scene_changed(session: AsyncSession, project_id: int, scene: SceneLike, *, reason: str) -> None:
    """Re-index the whole scene and tell open studios that it changed."""
    assert scene.id is not None
    blocks = await blocks_for_scene(session, scene.id)
    await enqueue_best_effort(
        "index_rag_document",
        {
            "project_id": project_id,
            "source_id": f"scene:{scene.id}",
            "source_kind": "scene",
            "text": scene_text(scene.heading, blocks),
            "content_version": scene.version,
        },
        description="RAG scene indexing enqueue",
    )
    await events.publish(
        project_id, "scene.changed", {"scene_id": scene.id, "version": scene.version, "reason": reason}
    )
    await request_twin_refresh(project_id)


async def request_twin_refresh(project_id: int) -> None:
    """Ask the Twin Keeper to re-derive the Story twin; bursts of edits collapse into one run."""
    await enqueue_best_effort(
        "refresh_story_twin",
        project_id,
        description="Story twin refresh enqueue",
        _job_id=f"story-twin:{project_id}",
        _defer_by=5,
    )
