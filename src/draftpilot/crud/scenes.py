"""CRUD operations for Scene."""

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.models import Act, Scene, SceneCreate, SceneUpdate


async def create(session: AsyncSession, data: SceneCreate) -> Scene:
    """Create and persist a new scene."""
    scene = Scene.model_validate(data)
    session.add(scene)
    await session.commit()
    await session.refresh(scene)
    return scene


async def get(session: AsyncSession, scene_id: int) -> Scene | None:
    """Return the scene with the given id, or ``None`` if absent."""
    return await session.get(Scene, scene_id)


async def list_for_act(session: AsyncSession, act_id: int) -> list[Scene]:
    """Return all scenes for an act ordered by position."""
    result = await session.exec(
        select(Scene).where(Scene.act_id == act_id).order_by(col(Scene.position))
    )
    return list(result.all())


async def list_for_screenplay(session: AsyncSession, screenplay_id: int) -> list[Scene]:
    """Return all scenes for a screenplay (across its acts) in act/scene order."""
    result = await session.exec(
        select(Scene)
        .join(Act, onclause=col(Scene.act_id) == col(Act.id))
        .where(Act.screenplay_id == screenplay_id)
        .order_by(col(Act.position), col(Scene.position))
    )
    return list(result.all())


async def update(session: AsyncSession, scene: Scene, data: SceneUpdate) -> Scene:
    """Apply the given changes to a scene and persist them."""
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(scene, key, value)
    session.add(scene)
    await session.commit()
    await session.refresh(scene)
    return scene


async def delete(session: AsyncSession, scene: Scene) -> None:
    """Delete the given scene."""
    await session.delete(scene)
    await session.commit()
