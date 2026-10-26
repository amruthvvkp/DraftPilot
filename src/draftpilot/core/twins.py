"""The room's two digital twins: the Story twin (the project) and the Writer twin (the writer).

The Story twin is the project's structured story context: the storyline, characters (with their
motives, objectives and timelines), locations, outline beats and canon. The Twin Keeper derives
characters (from character cues) and locations (from scene headings) from the draft after edits;
rows the writer created or edited are never overwritten. The Writer twin combines the writer's own profile and
memories with what the room has learned from their approve/reject decisions. Both are
summarised into compact briefs that every room agent receives.
"""

import re
import string
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime

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
    Character,
    CharacterTimelineEvent,
    KnowledgeNode,
    Location,
    Project,
    Scene,
    Screenplay,
    StoryBeat,
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
    """Return whether a graph node is owned by the Twin Keeper (not created or edited by the writer)."""
    return node.node_metadata.get("source") == TWIN_KEEPER and not node.node_metadata.get("writer_edited")


def _owned_by_keeper(row: Character | Location) -> bool:
    """Return whether a character/location row is derived and untouched by the writer."""
    return row.source == "twin" and not row.writer_edited


async def refresh_story_twin(session: AsyncSession, project_id: int) -> dict[str, int]:
    """Re-derive characters and locations from the working draft; never overwrite writer edits.

    Derived statistics (cue, dialogue lines, scenes) always refresh. A row's prose fields are
    only written while it is still keeper-owned, and only keeper-owned rows are removed when
    they disappear from the draft.
    """
    screenplay = await working_screenplay(session, project_id)
    if screenplay is None:
        return {"characters": 0, "locations": 0, "removed": 0}
    scenes = await scenes_crud.list_for_screenplay(session, screenplay.id or 0)
    blocks = await blocks_crud.list_for_scenes(session, [scene.id for scene in scenes if scene.id is not None])
    characters, locations = extract_story_twin(scenes, blocks)
    headings = {scene.id: scene.heading for scene in scenes}
    now = datetime.now(UTC)
    existing_characters = list(
        (await session.exec(select(Character).where(Character.project_id == project_id))).all()
    )
    by_cue = {normalize_cue(row.cue or row.name): row for row in existing_characters}
    by_name = {row.name.casefold(): row for row in existing_characters}
    seen_characters: set[int] = set()  # object identities of rows still in the draft
    for rank, stats in enumerate(characters):
        row = by_cue.get(stats.name) or by_name.get(display_name(stats.name).casefold())
        first = stats.first_scene_id
        summary = (
            f"Speaks {stats.dialogue_lines} lines across {len(stats.scene_ids)} scenes; first in "
            f"{headings.get(first) or 'the opening, before the first scene heading'}."
        )
        if row is None:
            row = Character(
                project_id=project_id,
                name=display_name(stats.name),
                cue=stats.name,
                summary=summary,
                role="supporting" if rank else "protagonist",
                source="twin",
                position=len(existing_characters) + rank,
            )
            existing_characters.append(row)
        elif (row.cue, row.dialogue_lines, row.scene_ids) == (stats.name, stats.dialogue_lines, stats.scene_ids) and (
            not _owned_by_keeper(row) or row.summary == summary
        ):
            seen_characters.add(id(row))
            continue
        else:
            row.version += 1
            row.updated_at = now
            if _owned_by_keeper(row):
                row.summary = summary
        row.cue = stats.name
        row.dialogue_lines = stats.dialogue_lines
        row.scene_ids = stats.scene_ids
        session.add(row)
        seen_characters.add(id(row))
    existing_locations = list((await session.exec(select(Location).where(Location.project_id == project_id))).all())
    by_heading = {(row.heading_location or row.name).upper(): row for row in existing_locations}
    seen_locations: set[int] = set()
    for place in locations:
        description = (
            f"{'/'.join(sorted(place.int_ext)) or 'Location'} in {len(place.scene_ids)} scenes"
            + (f" ({', '.join(sorted(place.times))})" if place.times else "")
            + "."
        )
        location = by_heading.get(place.name)
        derived = (sorted(place.int_ext), sorted(place.times), place.scene_ids)
        if location is None:
            location = Location(
                project_id=project_id,
                name=display_name(place.name),
                heading_location=place.name,
                description=description,
                source="twin",
                position=len(existing_locations),
            )
            existing_locations.append(location)
        elif (location.int_ext, location.times, location.scene_ids) == derived and (
            not _owned_by_keeper(location) or location.description == description
        ):
            seen_locations.add(id(location))
            continue
        else:
            location.version += 1
            location.updated_at = now
            if _owned_by_keeper(location):
                location.description = description
        location.heading_location = place.name
        location.int_ext, location.times, location.scene_ids = derived
        session.add(location)
        seen_locations.add(id(location))
    removed = 0
    for character in existing_characters:
        if character.id is not None and id(character) not in seen_characters and _owned_by_keeper(character):
            await session.delete(character)
            removed += 1
    for location in existing_locations:
        if location.id is not None and id(location) not in seen_locations and _owned_by_keeper(location):
            await session.delete(location)
            removed += 1
    await session.commit()
    return {"characters": len(characters), "locations": len(locations), "removed": removed}


def _clip(text: str, limit: int = 240) -> str:
    """Shorten prose for the compact brief."""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


async def story_twin_brief(session: AsyncSession, project_id: int, limit: int = 12) -> str:
    """Summarise the Story twin for agent instructions: storyline, cast, places, outline, canon."""
    project = await session.get(Project, project_id)
    characters = list(
        (
            await session.exec(
                select(Character).where(Character.project_id == project_id).order_by(col(Character.position), col(Character.id))
            )
        ).all()
    )
    # Writer-developed characters first, then by how much they speak.
    characters.sort(key=lambda row: (row.source == "twin" and not row.writer_edited, -row.dialogue_lines, row.position))
    locations = sorted(
        (await session.exec(select(Location).where(Location.project_id == project_id))).all(),
        key=lambda row: (row.source == "twin" and not row.writer_edited, -len(row.scene_ids)),
    )
    beats = list(
        (
            await session.exec(
                select(StoryBeat).where(StoryBeat.project_id == project_id).order_by(col(StoryBeat.position), col(StoryBeat.id))
            )
        ).all()
    )
    events_by_character: dict[int, list[CharacterTimelineEvent]] = {}
    for event in (
        await session.exec(
            select(CharacterTimelineEvent)
            .where(CharacterTimelineEvent.project_id == project_id)
            .order_by(col(CharacterTimelineEvent.position))
        )
    ).all():
        events_by_character.setdefault(event.character_id, []).append(event)
    lines: list[str] = []
    if project is not None:
        for label, value in (
            ("Logline", project.logline),
            ("Premise", project.premise),
            ("Theme", project.theme),
            ("Tone", project.tone),
            ("Synopsis", project.synopsis),
        ):
            if value:
                lines.append(f"{label}: {_clip(value, 600 if label == 'Synopsis' else 300)}")
    if characters:
        lines.append("Characters:")
        for row in characters[:limit]:
            facts = [
                f"{label} {_clip(value, 160)}"
                for label, value in (
                    ("want:", row.want),
                    ("need:", row.need),
                    ("motive:", row.motive),
                    ("objective:", row.objective),
                    ("flaw:", row.flaw),
                    ("arc:", row.arc_summary),
                )
                if value
            ]
            stats = f"{row.dialogue_lines} lines" if row.dialogue_lines else "not yet in the script"
            head = f"- {row.name} ({row.role}; {stats})"
            body = "; ".join(facts) or (_clip(row.summary, 160) if row.summary and not _owned_by_keeper(row) else "")
            timeline = events_by_character.get(row.id or 0, [])
            if timeline:
                body += ("; " if body else "") + "timeline: " + " → ".join(_clip(event.title, 60) for event in timeline[:6])
            lines.append(head + (f": {body}" if body else ""))
    if locations:
        lines.append("Key locations: " + ", ".join(row.name for row in locations[:limit]))
    if beats:
        lines.append("Outline beats: " + " | ".join(f"{index + 1}. {_clip(beat.title, 80)}" for index, beat in enumerate(beats[: limit * 2])))
    canon = [node for node in await graph_crud.list_nodes(session, project_id) if node.kind not in {"character", "location"}]
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


UI_PREFERENCES = frozenset({"appearance"})  # studio presentation, not something agents should act on


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
        if value and key not in UI_PREFERENCES:
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
