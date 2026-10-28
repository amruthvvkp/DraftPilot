"""Read-only aggregates behind the visual story tools: tension, pacing, milestones and the cast graph."""

from itertools import combinations

from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.screenplay.timeline import calculate_scene_timings
from draftpilot.core.story import entities
from draftpilot.core.story.structure import (
    acts_for_project,
    require_project,
    scenes_for_project,
)
from draftpilot.crud import blocks as blocks_crud
from draftpilot.models import BlockRead


class VisualAct(BaseModel):
    """One act of the draft, in order."""

    id: int
    title: str
    position: int


class VisualScene(BaseModel):
    """One scene in narrative order with its runtime estimate and the cast's average intensity."""

    id: int
    act_id: int
    index: int
    heading: str
    runtime_seconds: int
    start_seconds: int
    intensity: float | None
    event_count: int
    character_ids: list[int]


class VisualMilestone(BaseModel):
    """A beat with a structural type, anchored to the first of its scenes in narrative order."""

    beat_id: int
    title: str
    beat_type: str
    act_id: int | None
    scene_id: int | None
    scene_index: int | None


class VisualCharacter(BaseModel):
    """A node of the cast graph."""

    id: int
    name: str
    role: str
    moment_count: int


class VisualEdge(BaseModel):
    """A pair of characters, how many moments and scenes they share, and their named relations."""

    source: int
    target: int
    shared_moments: int
    shared_scenes: int
    relations: list[str]


class StoryVisuals(BaseModel):
    """Everything the visual tools draw, computed from one draft and the project's story data."""

    screenplay_id: int
    total_runtime_seconds: int
    acts: list[VisualAct]
    scenes: list[VisualScene]
    milestones: list[VisualMilestone]
    characters: list[VisualCharacter]
    edges: list[VisualEdge]


def _pair(a: int, b: int) -> tuple[int, int]:
    """Return an unordered character pair as a sorted tuple."""
    return (a, b) if a < b else (b, a)


async def story_visuals(session: AsyncSession, project_id: int, screenplay_id: int | None = None) -> StoryVisuals:
    """Aggregate a draft's scenes, intensities, beat milestones and cast graph for the visual tools."""
    await require_project(session, project_id)
    acts = await acts_for_project(session, project_id, screenplay_id)
    scenes = await scenes_for_project(session, project_id, screenplay_id)
    screenplay = acts[0].screenplay_id if acts else screenplay_id
    scene_ids = [scene.id or 0 for scene in scenes]
    blocks: dict[int, list[BlockRead]] = {scene_id: [] for scene_id in scene_ids}
    for block in await blocks_crud.list_for_scenes(session, scene_ids):
        blocks[block.scene_id].append(BlockRead.model_validate(block))
    timings, total = calculate_scene_timings(scenes, blocks)
    index_of = {scene_id: index for index, scene_id in enumerate(scene_ids)}

    events = await entities.list_entities(session, project_id, "timeline_event")
    moments = await entities.list_entities(session, project_id, "moment")
    beats = await entities.list_entities(session, project_id, "beat")
    characters = await entities.list_entities(session, project_id, "character")
    relationships = await entities.list_entities(session, project_id, "relationship")
    moment_scene = {moment.id: moment.scene_id for moment in moments}

    # An event sits in its own scene, else in its shared moment's scene.
    intensities: dict[int, list[int]] = {scene_id: [] for scene_id in scene_ids}
    cast: dict[int, set[int]] = {scene_id: set() for scene_id in scene_ids}
    for event in events:
        scene_id = event.scene_id or moment_scene.get(event.moment_id)
        if scene_id in intensities:
            intensities[scene_id].append(event.intensity)
            cast[scene_id].add(event.character_id)
    character_ids = {character.id for character in characters}
    for character in characters:
        for scene_id in character.scene_ids:
            if scene_id in cast:
                cast[scene_id].add(character.id)

    milestones: list[VisualMilestone] = []
    for beat in beats:
        if beat.beat_type == "beat":
            continue
        placed = sorted((index_of[scene_id], scene_id) for scene_id in beat.scene_ids if scene_id in index_of)
        milestones.append(
            VisualMilestone(
                beat_id=beat.id,
                title=beat.title,
                beat_type=beat.beat_type,
                act_id=beat.act_id,
                scene_id=placed[0][1] if placed else None,
                scene_index=placed[0][0] if placed else None,
            )
        )

    # Edge strength: moments two characters both take part in, plus scenes they share.
    in_moment: dict[int, set[int]] = {}
    for event in events:
        if event.moment_id is not None and event.character_id in character_ids:
            in_moment.setdefault(event.moment_id, set()).add(event.character_id)
    shared_moments: dict[tuple[int, int], int] = {}
    moment_count: dict[int, int] = {}
    for members in in_moment.values():
        for member in members:
            moment_count[member] = moment_count.get(member, 0) + 1
        for a, b in combinations(sorted(members), 2):
            shared_moments[(a, b)] = shared_moments.get((a, b), 0) + 1
    shared_scenes: dict[tuple[int, int], int] = {}
    for members in cast.values():
        for a, b in combinations(sorted(members & character_ids), 2):
            shared_scenes[(a, b)] = shared_scenes.get((a, b), 0) + 1
    relations: dict[tuple[int, int], list[str]] = {}
    for relationship in relationships:
        if relationship.source_character_id == relationship.target_character_id:
            continue
        relations.setdefault(_pair(relationship.source_character_id, relationship.target_character_id), []).append(relationship.relation)
    pairs = sorted(set(shared_moments) | set(shared_scenes) | set(relations))

    return StoryVisuals(
        screenplay_id=screenplay or 0,
        total_runtime_seconds=total,
        acts=[VisualAct(id=act.id or 0, title=act.title or f"Act {act.position + 1}", position=act.position) for act in acts],
        scenes=[
            VisualScene(
                id=scene.id or 0,
                act_id=scene.act_id,
                index=index,
                heading=scene.heading,
                runtime_seconds=timing.estimated_duration_seconds,
                start_seconds=timing.start_seconds,
                intensity=round(sum(values) / len(values), 2) if (values := intensities[scene.id or 0]) else None,
                event_count=len(values),
                character_ids=sorted(cast[scene.id or 0] & character_ids),
            )
            for index, (scene, timing) in enumerate(zip(scenes, timings, strict=True))
        ],
        milestones=milestones,
        characters=[
            VisualCharacter(id=character.id, name=character.name, role=character.role, moment_count=moment_count.get(character.id, 0))
            for character in characters
        ],
        edges=[
            VisualEdge(
                source=a,
                target=b,
                shared_moments=shared_moments.get((a, b), 0),
                shared_scenes=shared_scenes.get((a, b), 0),
                relations=relations.get((a, b), []),
            )
            for a, b in pairs
        ],
    )
