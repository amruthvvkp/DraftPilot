"""CRUD operations for Act."""

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.models import Act, ActCreate, ActUpdate


async def create(session: AsyncSession, data: ActCreate) -> Act:
    """Create and persist a new act."""
    act = Act.model_validate(data)
    session.add(act)
    await session.commit()
    await session.refresh(act)
    return act


async def get(session: AsyncSession, act_id: int) -> Act | None:
    """Return the act with the given id, or ``None`` if absent."""
    return await session.get(Act, act_id)


async def list_for_screenplay(session: AsyncSession, screenplay_id: int) -> list[Act]:
    """Return all acts for a screenplay ordered by position."""
    result = await session.exec(
        select(Act).where(Act.screenplay_id == screenplay_id).order_by(col(Act.position))
    )
    return list(result.all())


async def update(session: AsyncSession, act: Act, data: ActUpdate) -> Act:
    """Apply the given changes to an act and persist them."""
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(act, key, value)
    session.add(act)
    await session.commit()
    await session.refresh(act)
    return act


async def delete(session: AsyncSession, act: Act) -> None:
    """Delete the given act."""
    await session.delete(act)
    await session.commit()
