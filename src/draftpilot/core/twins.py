"""The room's two digital twins: the Story twin (the project) and the Writer twin (the writer).

The Story twin is a live, structured mirror of the screenplay kept in the knowledge graph:
characters (from character cues) and locations (from scene headings), each linked to the
scenes they appear in. The Twin Keeper re-derives them after edits; nodes the writer created
or edited are never overwritten. The Writer twin combines the writer's own profile and
memories with what the room has learned from their approve/reject decisions. Both are
summarised into compact briefs that every room agent receives.
"""

import re
import string
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.crud import blocks as blocks_crud
from draftpilot.crud import knowledge_graph as graph_crud
from draftpilot.crud import scenes as scenes_crud
from draftpilot.crud import screenplays as screenplays_crud
from draftpilot.models import (
    AgentProposal,
    Block,
    BlockType,
    KnowledgeNode,
    Scene,
    Screenplay,
    WriterMemory,
    WriterProfile,
)

TWIN_KEEPER = "twin_keeper"
_HEADING = re.compile(
    r"^\s*(?P<int_ext>INT\.?/EXT\.?|EXT\.?/INT\.?|I/E\.?|INT\.?|EXT\.?|EST\.?)\s+(?P<rest>.+)$", re.IGNORECASE
)
_TIMES = ("NIGHT", "DAY", "MORNING", "EVENING", "DAWN", "DUSK", "SUNSET", "SUNRISE", "LATER", "CONTINUOUS", "MOMENTS LATER")


@dataclass(frozen=True)
class ParsedHeading:
    """A scene heading split into interior/exterior, location, and time of day."""

    int_ext: str | None
    location: str | None
    time: str | None


def parse_heading(heading: str) -> ParsedHeading:
    """Split ``INT. BLOOM HOUSE - NIGHT (1973)`` into its parts; non-standard headings keep None."""
    match = _HEADING.match(heading.strip())
    if match is None:
        return ParsedHeading(None, None, None)
    int_ext = match["int_ext"].upper().rstrip(".").replace("I/E", "INT/EXT")
    # Drop annotations such as "(1973)", "(PRESENT)", or "[CONTINUOUS]" before splitting.
    rest = re.sub(r"\s*[\[(][^\])]*[\])]\s*", " ", match["rest"]).strip()
    location, time = rest, None
    parts = [part.strip() for part in re.split(r"\s+[-–—]\s+", rest) if part.strip()]
    if len(parts) > 1 and parts[-1].upper() in _TIMES:
        location, time = " - ".join(parts[:-1]), parts[-1].upper()
    return ParsedHeading(int_ext, re.sub(r"\s+", " ", location).upper() or None, time)


def normalize_cue(text: str) -> str:
    """Normalise a character cue: uppercase, without extensions like (V.O.) or (CONT'D)."""
    return re.sub(r"\s+", " ", re.sub(r"\(.*?\)", "", text)).strip().upper()


def display_name(name: str) -> str:
    """Title-case a cue or location without capitalising after apostrophes (EDWARD'S -> Edward's)."""
    return string.capwords(name.lower())


@dataclass
class CharacterStats:
    """What the script says about one character."""

    name: str
    dialogue_lines: int = 0
    scene_ids: list[int] = field(default_factory=list)

    @property
    def first_scene_id(self) -> int | None:
        """Return the scene the character first speaks in."""
        return self.scene_ids[0] if self.scene_ids else None


@dataclass
class LocationStats:
    """What the script says about one location."""

    name: str
    int_ext: set[str] = field(default_factory=set)
    times: set[str] = field(default_factory=set)
    scene_ids: list[int] = field(default_factory=list)


def extract_story_twin(
    scenes: list[Scene], blocks: list[Block]
) -> tuple[list[CharacterStats], list[LocationStats]]:
    """Derive characters (by dialogue) and locations (by heading) from ordered scenes and blocks."""
    by_scene: dict[int, list[Block]] = {}
    for block in blocks:
        by_scene.setdefault(block.scene_id, []).append(block)
    characters: dict[str, CharacterStats] = {}
    locations: dict[str, LocationStats] = {}
    for scene in scenes:
        scene_id = scene.id or 0
        heading = parse_heading(scene.heading)
        if heading.location:
            location = locations.setdefault(heading.location, LocationStats(heading.location))
            location.scene_ids.append(scene_id)
            if heading.int_ext:
                location.int_ext.add(heading.int_ext)
            if heading.time:
                location.times.add(heading.time)
        speaker: str | None = None
        for block in sorted(by_scene.get(scene_id, []), key=lambda item: item.position):
            if block.element_type == BlockType.CHARACTER:
                speaker = normalize_cue(block.text) or None
            elif block.element_type == BlockType.DIALOGUE and speaker:
                stats = characters.setdefault(speaker, CharacterStats(speaker))
                stats.dialogue_lines += 1
                if scene_id not in stats.scene_ids:
                    stats.scene_ids.append(scene_id)
            elif block.element_type not in {BlockType.PARENTHETICAL, BlockType.DIALOGUE}:
                speaker = None
    ranked_characters = sorted(characters.values(), key=lambda item: (-item.dialogue_lines, item.name))
    ranked_locations = sorted(locations.values(), key=lambda item: (-len(item.scene_ids), item.name))
    return ranked_characters, ranked_locations


async def working_screenplay(session: AsyncSession, project_id: int) -> Screenplay | None:
    """Return the draft the twin mirrors: the most recently updated screenplay that has scenes."""
    drafts = sorted(
        await screenplays_crud.list_for_project(session, project_id), key=lambda item: item.updated_at, reverse=True
    )
    for draft in drafts:
        if await scenes_crud.list_for_screenplay(session, draft.id or 0):
            return draft
    return drafts[0] if drafts else None


def _derived(node: KnowledgeNode) -> bool:
    """Return whether a node is owned by the Twin Keeper (not created or edited by the writer)."""
    return node.node_metadata.get("source") == TWIN_KEEPER and not node.node_metadata.get("writer_edited")


async def refresh_story_twin(session: AsyncSession, project_id: int) -> dict[str, int]:
    """Re-derive character and location nodes from the working draft; keep writer-owned nodes."""
    screenplay = await working_screenplay(session, project_id)
    if screenplay is None:
        return {"characters": 0, "locations": 0, "removed": 0}
    scenes = await scenes_crud.list_for_screenplay(session, screenplay.id or 0)
    blocks = await blocks_crud.list_for_scenes(session, [scene.id for scene in scenes if scene.id is not None])
    characters, locations = extract_story_twin(scenes, blocks)
    headings = {scene.id: scene.heading for scene in scenes}
    nodes = await graph_crud.list_nodes(session, project_id)
    existing = {(node.kind, node.label.casefold()): node for node in nodes}
    now = datetime.now(UTC)
    seen: set[int] = set()

    def upsert(kind: str, label: str, metadata: dict[str, Any], description: str) -> None:
        """Create a twin node, or refresh the derived facts of an existing one."""
        node = existing.get((kind, label.casefold()))
        if node is None:
            session.add(
                KnowledgeNode(
                    project_id=project_id,
                    kind=kind,
                    label=label,
                    description=description,
                    node_metadata={"source": TWIN_KEEPER, **metadata},
                )
            )
            return
        seen.add(node.id or 0)
        merged = {**node.node_metadata, **metadata}
        if merged != node.node_metadata:
            node.node_metadata = merged
            node.version += 1
            node.updated_at = now
            if _derived(node):
                node.description = description
            session.add(node)

    for character in characters:
        first = character.first_scene_id
        upsert(
            "character",
            display_name(character.name),
            {
                "cue": character.name,
                "dialogue_lines": character.dialogue_lines,
                "scene_ids": character.scene_ids,
                "first_scene_id": first,
                "screenplay_id": screenplay.id,
            },
            f"Speaks {character.dialogue_lines} lines across {len(character.scene_ids)} scenes; first in "
            f"{headings.get(first) or 'the opening, before the first scene heading'}.",
        )
    for location in locations:
        upsert(
            "location",
            display_name(location.name),
            {
                "heading_location": location.name,
                "int_ext": sorted(location.int_ext),
                "times": sorted(location.times),
                "scene_ids": location.scene_ids,
                "screenplay_id": screenplay.id,
            },
            f"{'/'.join(sorted(location.int_ext)) or 'Location'} in {len(location.scene_ids)} scenes"
            + (f" ({', '.join(sorted(location.times))})" if location.times else "")
            + ".",
        )
    removed = 0
    current = {("character", display_name(item.name).casefold()) for item in characters} | {
        ("location", display_name(item.name).casefold()) for item in locations
    }
    for node in nodes:
        if node.kind in {"character", "location"} and _derived(node) and (node.kind, node.label.casefold()) not in current:
            await session.delete(node)
            removed += 1
    await session.commit()
    return {"characters": len(characters), "locations": len(locations), "removed": removed}


async def story_twin_brief(session: AsyncSession, project_id: int, limit: int = 12) -> str:
    """Summarise the Story twin for agent instructions: main characters, key locations, canon."""
    nodes = await graph_crud.list_nodes(session, project_id)
    characters = sorted(
        (node for node in nodes if node.kind == "character"),
        key=lambda node: -int(node.node_metadata.get("dialogue_lines", 0)),
    )
    locations = sorted(
        (node for node in nodes if node.kind == "location"), key=lambda node: -len(node.node_metadata.get("scene_ids", []))
    )
    canon = [node for node in nodes if node.kind not in {"character", "location"}]
    lines: list[str] = []
    if characters:
        lines.append(
            "Main characters: "
            + "; ".join(
                f"{node.label} ({node.node_metadata.get('dialogue_lines', '?')} lines)"
                + (f" — {node.description}" if node.description and not _derived(node) else "")
                for node in characters[:limit]
            )
        )
    if locations:
        lines.append("Key locations: " + ", ".join(node.label for node in locations[:limit]))
    if canon:
        lines.append("Canon notes: " + "; ".join(f"{node.kind}: {node.label}" for node in canon[:limit]))
    return "\n".join(lines)


async def get_writer_profile(session: AsyncSession) -> WriterProfile:
    """Return the single writer profile, creating an empty one on first use."""
    profile = (await session.exec(select(WriterProfile).order_by(col(WriterProfile.id)))).first()
    if profile is None:
        profile = WriterProfile()
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
    return profile


async def learned_decisions(session: AsyncSession, project_id: int | None = None) -> dict[str, dict[str, int]]:
    """Count the writer's proposal decisions by target kind (what the room has learned so far)."""
    query = select(AgentProposal.target_kind, AgentProposal.status, func.count()).group_by(
        col(AgentProposal.target_kind), col(AgentProposal.status)
    )
    if project_id is not None:
        query = query.where(AgentProposal.project_id == project_id)
    counts: dict[str, dict[str, int]] = {}
    for target_kind, status, count in (await session.exec(query)).all():
        counts.setdefault(target_kind, {})[status] = count
    return counts


async def writer_twin_brief(session: AsyncSession, project_id: int | None = None, memory_limit: int = 12) -> str:
    """Summarise the Writer twin for agent instructions: identity, style, preferences, memories, learned."""
    profile = await get_writer_profile(session)
    query = select(WriterMemory).order_by(col(WriterMemory.pinned).desc(), col(WriterMemory.id).desc())
    memories = [
        memory
        for memory in (await session.exec(query)).all()
        if memory.project_id is None or memory.project_id == project_id
    ][:memory_limit]
    lines: list[str] = []
    who = profile.pen_name or profile.name
    if who:
        lines.append(f"Writer: {who}.")
    if profile.style_notes:
        lines.append(f"Their style: {profile.style_notes}")
    for key, value in profile.preferences.items():
        if value:
            lines.append(f"{key.replace('_', ' ').capitalize()}: {', '.join(value) if isinstance(value, list) else value}")
    if memories:
        lines.append("Remember: " + " | ".join(f"[{memory.kind}] {memory.text}" for memory in memories))
    decisions = await learned_decisions(session, project_id)
    tallies = Counter[str]()
    for statuses in decisions.values():
        tallies.update(statuses)
    decided = tallies["approved"] + tallies["rejected"] + tallies["rolled_back"]
    if decided:
        lines.append(
            f"Past proposals: {tallies['approved']} approved, {tallies['rejected']} rejected, "
            f"{tallies['rolled_back']} rolled back — respect what the writer has turned down."
        )
    return "\n".join(lines)
