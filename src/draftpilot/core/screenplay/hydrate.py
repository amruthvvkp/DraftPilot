"""Translate a ``ScreenplayDoc`` to and from the persisted Act/Scene/Block rows."""

from collections import defaultdict

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.screenplay.schema import ActDoc, BlockDoc, SceneDoc, ScreenplayDoc
from draftpilot.models import Act, Block, Scene, Screenplay

_CONTENT_FIELDS = (
    "element_type",
    "text",
    "character_extension",
    "is_dual",
    "dual_group",
    "translation",
    "translation_lang",
    "marks",
)


def block_to_doc(block: Block) -> BlockDoc:
    """Convert a persisted ``Block`` into a ``BlockDoc`` that remembers its id."""
    return BlockDoc(
        id=block.id,
        element_type=block.element_type,
        text=block.text,
        character_extension=block.character_extension,
        is_dual=block.is_dual,
        dual_group=block.dual_group,
        translation=block.translation,
        translation_lang=block.translation_lang,
        marks=block.marks,
        origin=block.origin,
    )


def block_from_doc(doc: BlockDoc, scene_id: int, position: int, origin: str = "human") -> Block:
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
        origin=doc.origin or origin,
    )


def scene_text(heading: str, blocks: list[Block]) -> str:
    """Return the plain text of a whole scene: heading plus every block in order."""
    return "\n".join([heading, *(block.text for block in blocks if block.text)])


async def blocks_for_scene(session: AsyncSession, scene_id: int) -> list[Block]:
    """Return a scene's blocks ordered by position."""
    result = await session.exec(
        select(Block).where(Block.scene_id == scene_id).order_by(col(Block.position))
    )
    return list(result.all())


async def scene_to_doc(session: AsyncSession, scene: Scene) -> SceneDoc:
    """Build a ``SceneDoc`` (heading + ordered blocks) for a persisted scene."""
    assert scene.id is not None
    blocks = await blocks_for_scene(session, scene.id)
    return SceneDoc(heading=scene.heading, blocks=[block_to_doc(b) for b in blocks])


async def apply_scene_doc(
    session: AsyncSession, scene: Scene, doc: SceneDoc, *, update_heading: bool = True
) -> None:
    """Make a scene's blocks match a ``SceneDoc`` while keeping block ids stable.

    Blocks are matched by id; snapshots taken before ids were recorded match by
    position instead. Matched blocks are updated in place (so linked dialogue
    translations survive), unmatched document blocks are inserted, and blocks
    absent from the document are deleted.
    """
    assert scene.id is not None
    existing = await blocks_for_scene(session, scene.id)
    by_id = {block.id: block for block in existing}
    legacy = all(block_doc.id is None for block_doc in doc.blocks)
    kept: set[int | None] = set()
    for position, block_doc in enumerate(doc.blocks):
        target = (
            (existing[position] if position < len(existing) else None)
            if legacy
            else by_id.get(block_doc.id)
        )
        if target is None or target.id in kept:
            session.add(block_from_doc(block_doc, scene.id, position))
            continue
        kept.add(target.id)
        for field in _CONTENT_FIELDS:
            setattr(target, field, getattr(block_doc, field))
        target.position = position
        if block_doc.origin:
            target.origin = block_doc.origin
        session.add(target)
    for block in existing:
        if block.id not in kept:
            await session.delete(block)
    if update_heading:
        scene.heading = doc.heading
    session.add(scene)
    await session.commit()


async def load_screenplay_doc(session: AsyncSession, screenplay_id: int) -> ScreenplayDoc:
    """Assemble the full ``ScreenplayDoc`` for a screenplay in three queries."""
    screenplay = await session.get(Screenplay, screenplay_id)
    acts = list(
        (
            await session.exec(
                select(Act).where(Act.screenplay_id == screenplay_id).order_by(col(Act.position))
            )
        ).all()
    )
    act_ids = [act.id for act in acts]
    scenes = list(
        (
            await session.exec(
                select(Scene).where(col(Scene.act_id).in_(act_ids)).order_by(col(Scene.position))
            )
        ).all()
    ) if act_ids else []
    scene_ids = [scene.id for scene in scenes]
    blocks = list(
        (
            await session.exec(
                select(Block).where(col(Block.scene_id).in_(scene_ids)).order_by(col(Block.position))
            )
        ).all()
    ) if scene_ids else []
    blocks_by_scene: dict[int, list[Block]] = defaultdict(list)
    for block in blocks:
        blocks_by_scene[block.scene_id].append(block)
    scenes_by_act: dict[int, list[Scene]] = defaultdict(list)
    for scene in scenes:
        scenes_by_act[scene.act_id].append(scene)
    return ScreenplayDoc(
        title_page=dict(screenplay.title_page) if screenplay is not None else {},
        acts=[
            ActDoc(
                title=act.title,
                scenes=[
                    SceneDoc(
                        heading=scene.heading,
                        blocks=[block_to_doc(block) for block in blocks_by_scene[scene.id or 0]],
                    )
                    for scene in scenes_by_act[act.id or 0]
                ],
            )
            for act in acts
        ],
    )


async def save_screenplay_doc(
    session: AsyncSession,
    screenplay_id: int,
    doc: ScreenplayDoc,
    *,
    commit: bool = True,
    origin: str = "import",
) -> None:
    """Replace all acts/scenes/blocks and the title page of a screenplay with a document.

    Used to populate a new screenplay (import, backup restore), so every block is
    new; ``origin`` records where the text came from.
    """
    screenplay = await session.get(Screenplay, screenplay_id)
    if screenplay is not None:
        screenplay.title_page = dict(doc.title_page)
        session.add(screenplay)
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
                imported = block_doc.model_copy(update={"id": None})
                session.add(block_from_doc(imported, scene.id, block_position, origin))
    if commit:
        await session.commit()
