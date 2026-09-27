"""CRUD operations for encrypted provider profiles."""

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.models import ProviderProfile


async def get(session: AsyncSession, profile_id: int) -> ProviderProfile | None:
    """Return one provider profile by id."""
    return await session.get(ProviderProfile, profile_id)


async def get_by_name(session: AsyncSession, name: str) -> ProviderProfile | None:
    """Return one provider profile by unique display name."""
    result = await session.exec(select(ProviderProfile).where(ProviderProfile.name == name))
    return result.first()


async def list_all(session: AsyncSession) -> list[ProviderProfile]:
    """Return provider profiles in stable name order."""
    result = await session.exec(select(ProviderProfile).order_by(col(ProviderProfile.name)))
    return list(result.all())
