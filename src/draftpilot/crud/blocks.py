"""CRUD operations for Block."""

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.models import Block, BlockCreate, BlockUpdate


async def create(session: AsyncSession, data: BlockCreate) -> Block:
    """Create and persist a new block."""
    block = Block.model_validate(data)
    session.add(block)
    await session.commit()
    await session.refresh(block)
    return block


async def get(session: AsyncSession, block_id: int) -> Block | None:
    """Return the block with the given id, or ``None`` if absent."""
    return await session.get(Block, block_id)


async def list_for_scene(session: AsyncSession, scene_id: int) -> list[Block]:
    """Return all blocks for a scene ordered by position."""
    result = await session.exec(
        select(Block).where(Block.scene_id == scene_id).order_by(col(Block.position))
    )
    return list(result.all())


async def update(session: AsyncSession, block: Block, data: BlockUpdate) -> Block:
    """Apply the given changes to a block and persist them."""
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(block, key, value)
    session.add(block)
    await session.commit()
    await session.refresh(block)
    return block


async def delete(session: AsyncSession, block: Block) -> None:
    """Delete the given block."""
    await session.delete(block)
    await session.commit()
