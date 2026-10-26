"""Screenplay structure services — acts, scenes and blocks — shared by REST and MCP.

Every write checks project scope and the caller's version, keeps positions contiguous, and runs
the usual side effects (scene RAG refresh, live-sync event, debounced Story-twin refresh).
"""

from typing import Any

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core import events
from draftpilot.core.errors import Conflict, Invalid, NotFound, check_version
from draftpilot.core.scene_sync import request_twin_refresh, scene_changed
from draftpilot.core.screenplay.hydrate import blocks_for_scene
from draftpilot.crud import acts as acts_crud
from draftpilot.crud import blocks as blocks_crud
from draftpilot.crud import projects as projects_crud
from draftpilot.crud import scenes as scenes_crud
from draftpilot.crud import screenplays as screenplays_crud
from draftpilot.models import (
    Act,
    Block,
    BlockCreate,
    BlockType,
    BlockUpdate,
    Project,
    Scene,
    SceneCreate,
    SceneUpdate,
    Screenplay,
)


async def require_project(session: AsyncSession, project_id: int) -> Project:
    """Return the project or raise ``NotFound``."""
    project = await projects_crud.get(session, project_id)
    if project is None:
        raise NotFound("Project not found")
    return project


async def screenplay_in_project(session: AsyncSession, project_id: int, screenplay_id: int | None) -> Screenplay:
    """Return the named draft, or the project's first draft when ``screenplay_id`` is None."""
    if screenplay_id is None:
        drafts = await screenplays_crud.list_for_project(session, project_id)
        if not drafts:
            raise NotFound("Project has no screenplay")
        return drafts[0]
    screenplay = await screenplays_crud.get(session, screenplay_id)
    if screenplay is None or screenplay.project_id != project_id:
        raise NotFound("Screenplay not found")
    return screenplay


async def act_in_project(session: AsyncSession, project_id: int, act_id: int) -> Act:
    """Return an act that belongs to the project or raise ``NotFound``."""
    act = await acts_crud.get(session, act_id)
    screenplay = await screenplays_crud.get(session, act.screenplay_id) if act else None
    if act is None or screenplay is None or screenplay.project_id != project_id:
        raise NotFound("Act not found")
    return act


async def scene_in_project(session: AsyncSession, project_id: int, scene_id: int) -> Scene:
    """Return a scene that belongs to the project or raise ``NotFound``."""
    scene = await scenes_crud.get(session, scene_id)
    if scene is None:
        raise NotFound("Scene not found")
    try:
        await act_in_project(session, project_id, scene.act_id)
    except NotFound:
        raise NotFound("Scene not found") from None
    return scene


async def versioned_scene(
    session: AsyncSession, project_id: int, scene_id: int, expected_version: int | None, *, required: bool = True
) -> Scene:
    """Return a project scene after enforcing the caller's scene version."""
    scene = await scene_in_project(session, project_id, scene_id)
    check_version(expected_version, scene.version, "Scene", required=required)
    return scene


async def _act_changed(project_id: int, screenplay_id: int, reason: str) -> None:
    """Tell open studios that a draft's act structure changed."""
    await events.publish(project_id, "structure.changed", {"screenplay_id": screenplay_id, "reason": reason})


async def _renumber(session: AsyncSession, rows: list[Any]) -> None:
    """Give rows contiguous positions in their current order."""
    for position, row in enumerate(rows):
        if row.position != position:
            row.position = position
            session.add(row)


# --- acts -------------------------------------------------------------------------------------


async def create_act(
    session: AsyncSession, project_id: int, screenplay_id: int | None, title: str, position: int | None = None
) -> Act:
    """Add an act to a draft at ``position`` (default: the end)."""
    screenplay = await screenplay_in_project(session, project_id, screenplay_id)
    assert screenplay.id is not None
    acts = await acts_crud.list_for_screenplay(session, screenplay.id)
    act = Act(screenplay_id=screenplay.id, title=title.strip() or f"Act {len(acts) + 1}", position=len(acts))
    session.add(act)
    await session.flush()
    if position is not None and 0 <= position < len(acts):
        acts.insert(position, act)
        await _renumber(session, acts)
    await session.commit()
    await session.refresh(act)
    await _act_changed(project_id, screenplay.id, "act.created")
    return act


async def update_act(session: AsyncSession, project_id: int, act_id: int, title: str | None = None, position: int | None = None) -> Act:
    """Rename or move an act within its draft."""
    act = await act_in_project(session, project_id, act_id)
    if title is not None:
        if not title.strip():
            raise Invalid("Act title cannot be empty")
        act.title = title.strip()
        session.add(act)
    if position is not None:
        acts = [item for item in await acts_crud.list_for_screenplay(session, act.screenplay_id) if item.id != act.id]
        acts.insert(max(0, min(position, len(acts))), act)
        await _renumber(session, acts)
    await session.commit()
    await session.refresh(act)
    await _act_changed(project_id, act.screenplay_id, "act.updated")
    return act


async def delete_act(session: AsyncSession, project_id: int, act_id: int, move_scenes_to: int | None = None) -> None:
    """Delete an act; its scenes move to ``move_scenes_to`` (required when the act has scenes)."""
    act = await act_in_project(session, project_id, act_id)
    scenes = await scenes_crud.list_for_act(session, act_id)
    siblings = await acts_crud.list_for_screenplay(session, act.screenplay_id)
    if len(siblings) == 1:
        raise Conflict("A screenplay needs at least one act")
    if scenes:
        if move_scenes_to is None:
            raise Conflict("Act has scenes; choose an act to move them to")
        target = await act_in_project(session, project_id, move_scenes_to)
        if target.id == act.id or target.screenplay_id != act.screenplay_id:
            raise Invalid("Scenes can only move to another act of the same draft")
        offset = len(await scenes_crud.list_for_act(session, move_scenes_to))
        for index, scene in enumerate(scenes):
            scene.act_id = move_scenes_to
            scene.position = offset + index
            session.add(scene)
        await session.flush()
    await session.delete(act)
    await session.flush()
    await _renumber(session, [item for item in siblings if item.id != act_id])
    await session.commit()
    await _act_changed(project_id, act.screenplay_id, "act.deleted")


# --- scenes -----------------------------------------------------------------------------------


async def create_scene(
    session: AsyncSession,
    project_id: int,
    heading: str,
    *,
    act_id: int | None = None,
    screenplay_id: int | None = None,
    position: int | None = None,
    scene_instruction: str = "",
    blocks: list[dict[str, Any]] | None = None,
    origin: str = "human",
) -> Scene:
    """Create a scene (default: appended to the draft's last act), optionally with initial blocks."""
    if not heading.strip():
        raise Invalid("Scene heading cannot be empty")
    if act_id is None:
        screenplay = await screenplay_in_project(session, project_id, screenplay_id)
        acts = await acts_crud.list_for_screenplay(session, screenplay.id or 0)
        if not acts:
            act = Act(screenplay_id=screenplay.id or 0, title="Act One", position=0)
            session.add(act)
            await session.flush()
            acts = [act]
        act_id = acts[-1].id
    act = await act_in_project(session, project_id, act_id or 0)
    siblings = await scenes_crud.list_for_act(session, act.id or 0)
    scene = Scene.model_validate(
        SceneCreate(act_id=act.id or 0, heading=heading.strip(), position=len(siblings), scene_instruction=scene_instruction)
    )
    session.add(scene)
    await session.flush()
    if position is not None and 0 <= position < len(siblings):
        siblings.insert(position, scene)
        await _renumber(session, siblings)
    for index, block in enumerate(blocks or []):
        session.add(_block_row(scene.id or 0, index, block, origin))
    await session.commit()
    await session.refresh(scene)
    await scene_changed(session, project_id, scene, reason="scene.created")
    return scene


async def update_scene(
    session: AsyncSession, project_id: int, scene_id: int, data: SceneUpdate, expected_version: int | None
) -> Scene:
    """Update a scene's heading, instruction or cached body under optimistic concurrency."""
    scene = await versioned_scene(session, project_id, scene_id, expected_version)
    updated = await scenes_crud.update(session, scene, data)
    await scene_changed(session, project_id, updated, reason="scene.updated")
    return updated


async def move_scene(
    session: AsyncSession, project_id: int, scene_id: int, position: int, expected_version: int | None, act_id: int | None = None
) -> Scene:
    """Move a scene to ``position`` within ``act_id`` (default: its current act)."""
    scene = await versioned_scene(session, project_id, scene_id, expected_version)
    source_act = await act_in_project(session, project_id, scene.act_id)
    target_act = await act_in_project(session, project_id, act_id) if act_id is not None else source_act
    if target_act.screenplay_id != source_act.screenplay_id:
        raise Invalid("Scenes can only move within the same draft")
    if target_act.id != source_act.id:
        remaining = [item for item in await scenes_crud.list_for_act(session, source_act.id or 0) if item.id != scene.id]
        await _renumber(session, remaining)
        scene.act_id = target_act.id or 0
    siblings = [item for item in await scenes_crud.list_for_act(session, target_act.id or 0) if item.id != scene.id]
    siblings.insert(max(0, min(position, len(siblings))), scene)
    for index, item in enumerate(siblings):
        item.position = index
        session.add(item)
    scene.version += 1
    session.add(scene)
    await session.commit()
    await session.refresh(scene)
    await events.publish(project_id, "structure.changed", {"screenplay_id": source_act.screenplay_id, "reason": "scene.moved"})
    await scene_changed(session, project_id, scene, reason="scene.moved")
    return scene


async def delete_scene(session: AsyncSession, project_id: int, scene_id: int, expected_version: int | None) -> dict[str, Any]:
    """Delete a scene with its blocks and revisions, unlinking beats and timeline events."""
    from draftpilot.core.indexing import delete_document
    from draftpilot.models import Character, CharacterTimelineEvent, Location, StoryBeat

    scene = await versioned_scene(session, project_id, scene_id, expected_version)
    act = await act_in_project(session, project_id, scene.act_id)
    snapshot = {"id": scene.id, "heading": scene.heading, "act_id": scene.act_id, "position": scene.position}
    for model in (StoryBeat, Character, Location):
        rows: Any = (await session.exec(select(model).where(model.project_id == project_id))).all()
        for row in rows:
            if scene_id in (row.scene_ids or []):
                row.scene_ids = [item for item in row.scene_ids if item != scene_id]
                session.add(row)
    events_query = select(CharacterTimelineEvent).where(CharacterTimelineEvent.scene_id == scene_id)
    for event in (await session.exec(events_query)).all():
        event.scene_id = None
        session.add(event)
    await session.delete(scene)
    await session.flush()
    await _renumber(session, await scenes_crud.list_for_act(session, act.id or 0))
    await session.commit()
    await delete_document(project_id, f"scene:{scene_id}")
    await events.publish(project_id, "structure.changed", {"screenplay_id": act.screenplay_id, "reason": "scene.deleted", "scene_id": scene_id})
    await request_twin_refresh(project_id)
    return snapshot


# --- blocks -----------------------------------------------------------------------------------


def _block_row(scene_id: int, position: int, data: dict[str, Any], origin: str) -> Block:
    """Build a validated block row from loose input."""
    try:
        element_type = BlockType(str(data.get("element_type", "action")))
    except ValueError as exc:
        raise Invalid(f"Unknown block type {data.get('element_type')!r}") from exc
    return Block(
        scene_id=scene_id,
        position=position,
        element_type=element_type,
        text=str(data.get("text", "")),
        character_extension=data.get("character_extension") or None,
        is_dual=bool(data.get("is_dual", False)),
        dual_group=data.get("dual_group"),
        origin=origin,
    )


async def create_block(
    session: AsyncSession,
    project_id: int,
    scene_id: int,
    data: dict[str, Any],
    expected_version: int | None,
    *,
    position: int | None = None,
    origin: str = "human",
) -> Block:
    """Insert one block at ``position`` (default: the end) of a versioned scene."""
    scene = await versioned_scene(session, project_id, scene_id, expected_version)
    existing = await blocks_for_scene(session, scene_id)
    block = _block_row(scene_id, len(existing), data, origin)
    session.add(block)
    await session.flush()
    if position is not None and 0 <= position < len(existing):
        existing.insert(position, block)
        await _renumber(session, existing)
    scene.version += 1
    session.add(scene)
    await session.commit()
    await session.refresh(block)
    await scene_changed(session, project_id, scene, reason="block.created")
    return block


async def create_block_from_schema(
    session: AsyncSession, project_id: int, scene_id: int, data: BlockCreate, expected_version: int | None
) -> Block:
    """Create a block from the REST schema, honouring its requested position."""
    scene = await versioned_scene(session, project_id, scene_id, expected_version)
    block = await blocks_crud.create(session, BlockCreate(**{**data.model_dump(), "scene_id": scene_id}))
    scene.version += 1
    session.add(scene)
    await session.commit()
    await scene_changed(session, project_id, scene, reason="block.created")
    return block


async def update_block(
    session: AsyncSession, project_id: int, scene_id: int, block_id: int, data: BlockUpdate, expected_version: int | None
) -> Block:
    """Edit one block; a text change moves authorship to the writer."""
    scene = await versioned_scene(session, project_id, scene_id, expected_version)
    block = await blocks_crud.get(session, block_id)
    if block is None or block.scene_id != scene_id:
        raise NotFound("Block not found")
    text_changed = data.text is not None and data.text != block.text
    updated = await blocks_crud.update(session, block, data)
    if text_changed:
        updated.origin = "human"
        session.add(updated)
    scene.version += 1
    session.add(scene)
    await session.commit()
    await scene_changed(session, project_id, scene, reason="block.updated")
    return updated


async def delete_block(session: AsyncSession, project_id: int, scene_id: int, block_id: int, expected_version: int | None) -> None:
    """Delete one block (and its translations) and close the gap in positions."""
    scene = await versioned_scene(session, project_id, scene_id, expected_version)
    block = await blocks_crud.get(session, block_id)
    if block is None or block.scene_id != scene_id:
        raise NotFound("Block not found")
    await session.delete(block)
    await session.flush()
    await _renumber(session, await blocks_for_scene(session, scene_id))
    scene.version += 1
    session.add(scene)
    await session.commit()
    await scene_changed(session, project_id, scene, reason="block.deleted")


async def reorder_blocks(
    session: AsyncSession, project_id: int, scene_id: int, block_ids: list[int], expected_version: int | None
) -> list[Block]:
    """Reorder a scene's blocks; the order must list exactly the scene's current blocks."""
    scene = await versioned_scene(session, project_id, scene_id, expected_version)
    blocks = {block.id: block for block in await blocks_for_scene(session, scene_id)}
    if sorted(block_ids) != sorted(block_id for block_id in blocks if block_id is not None):
        raise Invalid("Order must list every block in the scene exactly once")
    for position, block_id in enumerate(block_ids):
        blocks[block_id].position = position
        session.add(blocks[block_id])
    scene.version += 1
    session.add(scene)
    await session.commit()
    await scene_changed(session, project_id, scene, reason="blocks.reordered")
    return [blocks[block_id] for block_id in block_ids]


async def scenes_for_project(session: AsyncSession, project_id: int, screenplay_id: int | None = None) -> list[Scene]:
    """Return a draft's scenes in act/scene order."""
    screenplay = await screenplay_in_project(session, project_id, screenplay_id)
    return await scenes_crud.list_for_screenplay(session, screenplay.id or 0)


async def acts_for_project(session: AsyncSession, project_id: int, screenplay_id: int | None = None) -> list[Act]:
    """Return a draft's acts in order."""
    screenplay = await screenplay_in_project(session, project_id, screenplay_id)
    query = select(Act).where(Act.screenplay_id == screenplay.id).order_by(col(Act.position))
    return list((await session.exec(query)).all())
