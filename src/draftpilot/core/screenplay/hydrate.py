"""Translate a ``ScreenplayDoc`` to and from the persisted Act/Scene/Block rows."""

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.screenplay.schema import ActDoc, BlockDoc, SceneDoc, ScreenplayDoc
from draftpilot.models import Act, Block, Scene


def block_to_doc(block: Block) -> BlockDoc:
    """Convert a persisted ``Block`` into a ``BlockDoc``."""
    return BlockDoc(
        element_type=block.element_type,
        text=block.text,
        character_extension=block.character_extension,
        is_dual=block.is_dual,
        dual_group=block.dual_group,
        translation=block.translation,
        translation_lang=block.translation_lang,
        marks=block.marks,
    )


def block_from_doc(doc: BlockDoc, scene_id: int, position: int) -> Block:
    """Build an unpersisted ``Block`` for a scene from a ``BlockDoc``."""
    return Block(
        scene_id=scene_id,
        position=position,
        element_type=doc.element_type,
        text=doc.text,
        character_extension=doc.character_extension,
        is_dual=doc.is_dual,
        dual_group=doc.dual_group,
        translation=doc.translation,
        translation_lang=doc.translation_lang,
        marks=doc.marks,
    )


async def _blocks_for_scene(session: AsyncSession, scene_id: int) -> list[Block]:
    """Return a scene's blocks ordered by position."""
    result = await session.exec(
        select(Block).where(Block.scene_id == scene_id).order_by(col(Block.position))
    )
    return list(result.all())


async def scene_to_doc(session: AsyncSession, scene: Scene) -> SceneDoc:
    """Build a ``SceneDoc`` (heading + ordered blocks) for a persisted scene."""
    assert scene.id is not None
    blocks = await _blocks_for_scene(session, scene.id)
    return SceneDoc(heading=scene.heading, blocks=[block_to_doc(b) for b in blocks])


async def replace_scene_blocks(session: AsyncSession, scene: Scene, doc: SceneDoc) -> None:
    """Replace a scene's heading and blocks with the contents of a ``SceneDoc``."""
    assert scene.id is not None
    for existing in await _blocks_for_scene(session, scene.id):
        await session.delete(existing)
    scene.heading = doc.heading
    session.add(scene)
    for position, block_doc in enumerate(doc.blocks):
        session.add(block_from_doc(block_doc, scene.id, position))
    await session.commit()


async def load_screenplay_doc(session: AsyncSession, screenplay_id: int) -> ScreenplayDoc:
    """Assemble the full ``ScreenplayDoc`` for a screenplay from the database."""
    acts_result = await session.exec(
        select(Act).where(Act.screenplay_id == screenplay_id).order_by(col(Act.position))
    )
    act_docs: list[ActDoc] = []
    for act in acts_result.all():
        assert act.id is not None
        scenes_result = await session.exec(
            select(Scene).where(Scene.act_id == act.id).order_by(col(Scene.position))
        )
        scene_docs = [await scene_to_doc(session, scene) for scene in scenes_result.all()]
        act_docs.append(ActDoc(title=act.title, scenes=scene_docs))
    return ScreenplayDoc(acts=act_docs)


async def save_screenplay_doc(
    session: AsyncSession, screenplay_id: int, doc: ScreenplayDoc
) -> None:
    """Replace all acts/scenes/blocks of a screenplay with the contents of a doc."""
    existing = await session.exec(select(Act).where(Act.screenplay_id == screenplay_id))
    for act in existing.all():
        await session.delete(act)
    await session.flush()
    for act_position, act_doc in enumerate(doc.acts):
        act = Act(
            screenplay_id=screenplay_id,
            position=act_position,
            title=act_doc.title or f"Act {act_position + 1}",
        )
        session.add(act)
        await session.flush()
        assert act.id is not None
        for scene_position, scene_doc in enumerate(act_doc.scenes):
            scene = Scene(act_id=act.id, position=scene_position, heading=scene_doc.heading)
            session.add(scene)
            await session.flush()
            assert scene.id is not None
            for block_position, block_doc in enumerate(scene_doc.blocks):
                session.add(block_from_doc(block_doc, scene.id, block_position))
    await session.commit()
