"""CRUD operations for Screenplay."""

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.models import Screenplay, ScreenplayCreate, ScreenplayUpdate


async def create(session: AsyncSession, data: ScreenplayCreate) -> Screenplay:
    """Create and persist a new screenplay."""
    screenplay = Screenplay.model_validate(data)
    session.add(screenplay)
    await session.commit()
    await session.refresh(screenplay)
    return screenplay


async def get(session: AsyncSession, screenplay_id: int) -> Screenplay | None:
    """Return the screenplay with the given id, or ``None`` if absent."""
    return await session.get(Screenplay, screenplay_id)


async def list_for_project(session: AsyncSession, project_id: int) -> list[Screenplay]:
    """Return all screenplays for a project ordered by title."""
    result = await session.exec(
        select(Screenplay)
        .where(Screenplay.project_id == project_id)
        .order_by(col(Screenplay.title))
    )
    return list(result.all())


async def update(
    session: AsyncSession, screenplay: Screenplay, data: ScreenplayUpdate
) -> Screenplay:
    """Apply the given changes to a screenplay and persist them."""
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(screenplay, key, value)
    session.add(screenplay)
    await session.commit()
    await session.refresh(screenplay)
    return screenplay


async def delete(session: AsyncSession, screenplay: Screenplay) -> None:
    """Delete the given screenplay."""
    await session.delete(screenplay)
    await session.commit()
