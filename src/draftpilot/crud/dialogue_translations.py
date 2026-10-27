"""CRUD operations for linked dialogue translations."""

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.models import DialogueTranslation, DialogueTranslationCreate


async def list_for_block(session: AsyncSession, block_id: int) -> list[DialogueTranslation]:
    """Return translations for one source block in language order."""
    result = await session.exec(
        select(DialogueTranslation)
        .where(DialogueTranslation.block_id == block_id)
        .order_by(col(DialogueTranslation.language))
    )
    return list(result.all())


async def upsert(session: AsyncSession, data: DialogueTranslationCreate) -> DialogueTranslation:
    """Create or replace one language variant for a source dialogue block."""
    existing = (
        await session.exec(
            select(DialogueTranslation).where(
                DialogueTranslation.block_id == data.block_id,
                DialogueTranslation.language == data.language,
            )
        )
    ).first()
    if existing is None:
        existing = DialogueTranslation.model_validate(data)
    else:
        existing.text = data.text
        existing.source_version = data.source_version
        existing.status = data.status
    session.add(existing)
    await session.commit()
    await session.refresh(existing)
    return existing
