"""Scene-level proposals: whole-scene rewrites and appended scenes, each one reviewable and reversible."""

from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.screenplay.adapters.fountain import parse_fountain
from draftpilot.core.screenplay.hydrate import (
    apply_scene_doc,
    block_from_doc,
    scene_to_doc,
)
from draftpilot.core.screenplay.schema import BlockDoc, SceneDoc
from draftpilot.crud import acts as acts_crud
from draftpilot.crud import scenes as scenes_crud
from draftpilot.models import Act, Scene

MAX_REWRITE_BLOCKS = 400


def parse_scene_fountain(text: str) -> SceneDoc:
    """Parse one scene written as Fountain into a heading plus blocks, merging any extra headings away."""
    doc = parse_fountain(text.strip() + "\n")
    scenes = [scene for act in doc.acts for scene in act.scenes]
    if not scenes:
        raise ValueError("The rewrite contains no screenplay content")
    blocks = [block for scene in scenes for block in scene.blocks]
    if not blocks or len(blocks) > MAX_REWRITE_BLOCKS:
        raise ValueError("The rewrite must contain between 1 and 400 blocks")
    heading = next((scene.heading for scene in scenes if scene.heading), "")
    return SceneDoc(heading=heading, blocks=[block.model_copy(update={"id": None}) for block in blocks])


def rewrite_operation(doc: SceneDoc) -> dict[str, Any]:
    """Return the proposal operation that replaces a scene's blocks (and heading, when given)."""
    operation: dict[str, Any] = {
        "blocks": [block.model_dump(mode="json", exclude={"id", "origin"}) for block in doc.blocks]
    }
    if doc.heading:
        operation["heading"] = doc.heading
    return operation


async def rewrite_snapshot(session: AsyncSession, scene: Scene) -> dict[str, Any]:
    """Capture the scene's current heading and id-bearing blocks so a rollback restores them exactly."""
    current = await scene_to_doc(session, scene)
    return {"heading": current.heading, "blocks": [block.model_dump(mode="json") for block in current.blocks]}


async def apply_scene_rewrite(
    session: AsyncSession, scene: Scene, heading: str | None, blocks: list[dict[str, Any]], origin: str | None
) -> None:
    """Replace a scene's blocks from a proposal payload and bump its version."""
    docs = [BlockDoc.model_validate(item) for item in blocks]
    if origin is not None:
        docs = [doc.model_copy(update={"origin": origin}) for doc in docs]
    scene.version += 1
    await apply_scene_doc(
        session, scene, SceneDoc(heading=heading or scene.heading, blocks=docs), update_heading=heading is not None
    )


def append_operation(scenes: list[SceneDoc]) -> dict[str, Any]:
    """Return the proposal operation that appends new scenes to the end of a screenplay."""
    return {
        "append_scenes": [
            {"heading": scene.heading, "blocks": [block.model_dump(mode="json", exclude={"id", "origin"}) for block in scene.blocks]}
            for scene in scenes
        ]
    }


async def append_scenes(
    session: AsyncSession, screenplay_id: int, scenes: list[dict[str, Any]], origin: str
) -> list[int]:
    """Append proposed scenes after the screenplay's last scene and return their ids."""
    acts = await acts_crud.list_for_screenplay(session, screenplay_id)
    act = acts[-1] if acts else Act(screenplay_id=screenplay_id, position=0)
    if act.id is None:
        session.add(act)
        await session.flush()
    existing = await scenes_crud.list_for_act(session, act.id or 0)
    position = max((scene.position for scene in existing), default=-1) + 1
    created: list[Scene] = []
    for offset, item in enumerate(scenes):
        scene = Scene(act_id=act.id or 0, heading=str(item.get("heading") or ""), position=position + offset)
        session.add(scene)
        await session.flush()
        for index, block in enumerate(item.get("blocks") or []):
            session.add(block_from_doc(BlockDoc.model_validate(block), scene.id or 0, index, origin))
        created.append(scene)
    await session.commit()
    return [scene.id or 0 for scene in created]


async def remove_appended_scenes(session: AsyncSession, scene_ids: list[int]) -> list[Scene]:
    """Delete scenes a rolled-back proposal appended, refusing if the writer has edited any of them."""
    scenes = [scene for scene_id in scene_ids if (scene := await session.get(Scene, scene_id)) is not None]
    if any(scene.version != 1 for scene in scenes):
        raise ValueError("An appended scene has been edited since approval")
    for scene in scenes:
        await session.delete(scene)
    await session.commit()
    return scenes
