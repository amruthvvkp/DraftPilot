"""CRUD and dependency invalidation for story artifacts."""

from collections.abc import Sequence

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.models import StoryArtifact


async def get(session: AsyncSession, artifact_id: int) -> StoryArtifact | None:
    """Return an artifact by identifier."""
    return await session.get(StoryArtifact, artifact_id)


async def list_for_project(session: AsyncSession, project_id: int) -> list[StoryArtifact]:
    """Return project artifacts ordered by kind and title."""
    result = await session.exec(
        select(StoryArtifact)
        .where(StoryArtifact.project_id == project_id)
        .order_by(col(StoryArtifact.kind), col(StoryArtifact.title))
    )
    return list(result.all())


async def mark_dependents_stale(
    session: AsyncSession, project_id: int, changed_ids: Sequence[int]
) -> list[int]:
    """Mark artifacts depending on changed artifacts as stale."""
    changed = set(changed_ids)
    artifacts = await list_for_project(session, project_id)
    stale_ids: list[int] = []
    for artifact in artifacts:
        if artifact.id not in changed and changed.intersection(artifact.depends_on):
            artifact.stale = True
            stale_ids.append(artifact.id or 0)
            session.add(artifact)
    return stale_ids
