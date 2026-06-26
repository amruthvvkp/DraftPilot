"""CRUD operations for SceneRevision — scene-level snapshot and restore."""

from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.screenplay.hydrate import replace_scene_blocks, scene_to_doc
from draftpilot.core.screenplay.schema import SceneDoc
from draftpilot.models import Scene, SceneRevision


async def _next_rev_number(session: AsyncSession, scene_id: int) -> int:
    """Return the next 1-based revision number for a scene."""
    result = await session.exec(
        select(func.max(col(SceneRevision.rev_number))).where(
            SceneRevision.scene_id == scene_id
        )
    )
    return (result.one() or 0) + 1


async def snapshot(
    session: AsyncSession, scene: Scene, message: str | None = None
) -> SceneRevision:
    """Capture the scene's current heading and blocks as a new revision."""
    assert scene.id is not None
    doc = await scene_to_doc(session, scene)
    revision = SceneRevision(
        scene_id=scene.id,
        rev_number=await _next_rev_number(session, scene.id),
        snapshot=doc.model_dump(mode="json"),
        message=message,
    )
    session.add(revision)
    await session.commit()
    await session.refresh(revision)
    return revision


async def get(session: AsyncSession, revision_id: int) -> SceneRevision | None:
    """Return the scene revision with the given id, or ``None`` if absent."""
    return await session.get(SceneRevision, revision_id)


async def list_for_scene(session: AsyncSession, scene_id: int) -> list[SceneRevision]:
    """Return all revisions for a scene ordered by revision number."""
    result = await session.exec(
        select(SceneRevision)
        .where(SceneRevision.scene_id == scene_id)
        .order_by(col(SceneRevision.rev_number))
    )
    return list(result.all())


async def restore(
    session: AsyncSession, scene: Scene, revision: SceneRevision
) -> None:
    """Restore a scene's heading and blocks from a stored revision snapshot."""
    doc = SceneDoc.model_validate(revision.snapshot)
    await replace_scene_blocks(session, scene, doc)
