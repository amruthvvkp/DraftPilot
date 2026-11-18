"""Read-only views of the script and the Story twin, and ``analyze_script`` over them in Monty.

Code mode hands sandboxed code two allow-listed host objects instead of many tool calls:
``script`` (scenes in script order, with exact word, dialogue and speaker counts) and ``story``
(characters, relationships, timeline events, locations, beats and canon nodes). Both are plain
precomputed snapshots: nothing in them can reach the database, and no method writes. Changes
still go through ``propose_*`` tools as proposals the writer approves.
"""

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from pydantic_monty import ClassInstance
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.config import settings
from draftpilot.core.monty import (
    MontyExecutionConfig,
    MontyExecutionResult,
    MontySandboxError,
    execute_glue_audited,
    execution_config,
)
from draftpilot.core.screenplay.hydrate import load_screenplay_doc
from draftpilot.core.screenplay.schema import ScreenplayDoc
from draftpilot.core.twins import normalize_cue, parse_heading, working_screenplay
from draftpilot.models import (
    Act,
    BlockType,
    Character,
    CharacterRelationship,
    CharacterTimelineEvent,
    KnowledgeNode,
    Location,
    Project,
    Scene,
    StoryBeat,
)

_YEAR = re.compile(r"\((\d{4})\)")
SCRIPT_METHODS = ("summary", "scene", "dialogue_share", "pacing_curve", "scene_character_matrix", "character_scenes")
STORY_METHODS = ("character", "events_for")


def _words(text: str) -> int:
    """Count whitespace-separated words."""
    return len(text.split())


@dataclass
class ScriptView:
    """The working draft in script order: one dict per scene, plus exact statistics over them."""

    title: str = ""
    scenes: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        """Return scene, act, word and speaker totals, and the interior/exterior and time-of-day splits."""
        words = sum(scene["words"] for scene in self.scenes)
        dialogue = sum(scene["dialogue_words"] for scene in self.scenes)
        speakers = {name for scene in self.scenes for name in scene["speakers"]}
        return {
            "scenes": len(self.scenes),
            "acts": len({scene["act"] for scene in self.scenes}),
            "words": words,
            "dialogue_words": dialogue,
            "dialogue_ratio": round(dialogue / words, 4) if words else 0.0,
            "speaking_characters": len(speakers),
            "locations": len({scene["location"] for scene in self.scenes if scene["location"]}),
            "int_ext": dict(Counter(scene["int_ext"] or "OTHER" for scene in self.scenes)),
            "times": dict(Counter(scene["time"] or "UNSPECIFIED" for scene in self.scenes)),
        }

    def scene(self, scene_id: int) -> dict[str, Any] | None:
        """Return one scene by id, or None."""
        return next((scene for scene in self.scenes if scene["id"] == scene_id), None)

    def dialogue_share(self, by: str = "words") -> dict[str, float]:
        """Return each speaker's share of all dialogue, by ``words`` or ``lines``, largest first."""
        key = "speaker_words" if by == "words" else "speaker_lines"
        totals: Counter[str] = Counter()
        for scene in self.scenes:
            totals.update(scene[key])
        whole = sum(totals.values())
        return {name: round(count / whole, 4) for name, count in totals.most_common()} if whole else {}

    def pacing_curve(self) -> list[dict[str, Any]]:
        """Return per-scene length and dialogue ratio in script order (the pacing curve)."""
        return [
            {
                "number": scene["number"],
                "id": scene["id"],
                "words": scene["words"],
                "dialogue_ratio": round(scene["dialogue_words"] / scene["words"], 4) if scene["words"] else 0.0,
                "speakers": len(scene["speakers"]),
            }
            for scene in self.scenes
        ]

    def scene_character_matrix(self, top: int = 0) -> dict[str, Any]:
        """Return a character × scene presence matrix (1 = speaks there), for the ``top`` speakers or all."""
        lines: Counter[str] = Counter()
        for scene in self.scenes:
            lines.update(scene["speaker_lines"])
        ranked = sorted(lines, key=lambda name: (-lines[name], name))[: top or None]
        return {
            "characters": ranked,
            "scene_ids": [scene["id"] for scene in self.scenes],
            "rows": [[1 if name in scene["speakers"] else 0 for scene in self.scenes] for name in ranked],
        }

    def character_scenes(self, name: str) -> list[int]:
        """Return the ids of the scenes a character speaks in (by cue, case-insensitive)."""
        cue = normalize_cue(name)
        return [scene["id"] for scene in self.scenes if cue in scene["speakers"]]


@dataclass
class StoryView:
    """The Story twin as typed records: cast, relationships, timelines, places, beats and canon."""

    title: str = ""
    logline: str = ""
    characters: list[dict[str, Any]] = field(default_factory=list)
    relationships: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    locations: list[dict[str, Any]] = field(default_factory=list)
    beats: list[dict[str, Any]] = field(default_factory=list)
    facts: list[dict[str, Any]] = field(default_factory=list)

    def character(self, name: str) -> dict[str, Any] | None:
        """Return the character matching a name, cue or alias (case-insensitive), or None."""
        wanted = normalize_cue(name)
        for character in self.characters:
            names = [character["name"], character["cue"] or "", *character["aliases"]]
            if wanted in {normalize_cue(item) for item in names if item}:
                return character
        return None

    def events_for(self, name: str) -> list[dict[str, Any]]:
        """Return one character's timeline events in their timeline order."""
        character = self.character(name)
        if character is None:
            return []
        return sorted((event for event in self.events if event["character_id"] == character["id"]), key=lambda event: event["position"])


def script_view(doc: ScreenplayDoc, scene_ids: list[int] | None = None) -> ScriptView:
    """Build the script view from a ``ScreenplayDoc``; ``scene_ids`` (in doc order) default to 1..n."""
    scenes: list[dict[str, Any]] = []
    number = 0
    for act_index, act in enumerate(doc.acts, start=1):
        for scene in act.scenes:
            number += 1
            heading = parse_heading(scene.heading)
            year = _YEAR.search(scene.heading)
            speaker: str | None = None
            speakers: list[str] = []
            speaker_words: Counter[str] = Counter()
            speaker_lines: Counter[str] = Counter()
            action: list[str] = []
            dialogue_words = 0
            for block in scene.blocks:
                if block.element_type == BlockType.CHARACTER:
                    speaker = normalize_cue(block.text) or None
                elif block.element_type == BlockType.DIALOGUE and speaker:
                    count = _words(block.text)
                    dialogue_words += count
                    speaker_words[speaker] += count
                    speaker_lines[speaker] += 1
                    if speaker not in speakers:
                        speakers.append(speaker)
                elif block.element_type != BlockType.PARENTHETICAL:
                    speaker = None
                    if block.element_type in {BlockType.ACTION, BlockType.TRANSITION, BlockType.SHOT}:
                        action.append(block.text)
            action_text = "\n".join(action)
            scenes.append(
                {
                    "id": scene_ids[number - 1] if scene_ids else number,
                    "number": number,
                    "act": act_index,
                    "heading": scene.heading,
                    "int_ext": heading.int_ext,
                    "location": heading.location,
                    "time": heading.time,
                    "year": int(year.group(1)) if year else None,
                    "words": _words(action_text) + dialogue_words,
                    "action_words": _words(action_text),
                    "dialogue_words": dialogue_words,
                    "speakers": speakers,
                    "speaker_words": dict(speaker_words),
                    "speaker_lines": dict(speaker_lines),
                    "action": action_text,
                }
            )
    return ScriptView(title=doc.title_page.get("title", ""), scenes=scenes)


async def load_script_view(session: AsyncSession, project_id: int) -> ScriptView:
    """Load the project's working draft as a script view (empty when there is no draft)."""
    screenplay = await working_screenplay(session, project_id)
    if screenplay is None or screenplay.id is None:
        return ScriptView()
    doc = await load_screenplay_doc(session, screenplay.id)
    ids = list(
        (
            await session.exec(
                select(Scene.id)
                .join(Act, col(Act.id) == col(Scene.act_id))
                .where(Act.screenplay_id == screenplay.id)
                .order_by(col(Act.position), col(Scene.position))
            )
        ).all()
    )
    view = script_view(doc, [scene_id for scene_id in ids if scene_id is not None])
    view.title = view.title or screenplay.title
    return view


async def load_story_view(session: AsyncSession, project_id: int) -> StoryView:
    """Load the project's Story twin records as a story view."""

    async def rows[RowT](model: type[RowT], *order: Any) -> list[RowT]:
        """Return one table's rows for the project."""
        return list((await session.exec(select(model).where(model.project_id == project_id).order_by(*order))).all())  # type: ignore[attr-defined]

    project = await session.get(Project, project_id)
    characters = await rows(Character, col(Character.position), col(Character.id))
    return StoryView(
        title=project.title if project else "",
        logline=(project.logline or "") if project else "",
        characters=[
            {
                "id": item.id,
                "name": item.name,
                "cue": item.cue,
                "aliases": list(item.aliases),
                "role": item.role,
                "want": item.want,
                "need": item.need,
                "arc_summary": item.arc_summary,
                "dialogue_lines": item.dialogue_lines,
                "scene_ids": list(item.scene_ids),
            }
            for item in characters
        ],
        relationships=[
            {"source_id": item.source_character_id, "target_id": item.target_character_id, "relation": item.relation}
            for item in await rows(CharacterRelationship, col(CharacterRelationship.id))
        ],
        events=[
            {
                "id": item.id,
                "character_id": item.character_id,
                "position": item.position,
                "title": item.title,
                "description": item.description,
                "story_time": item.story_time,
                "chrono_index": item.chrono_index,
                "intensity": item.intensity,
                "scene_id": item.scene_id,
                "beat_id": item.beat_id,
                "moment_id": item.moment_id,
            }
            for item in await rows(CharacterTimelineEvent, col(CharacterTimelineEvent.character_id), col(CharacterTimelineEvent.position))
        ],
        locations=[
            {"id": item.id, "name": item.name, "heading_location": item.heading_location, "scene_ids": list(item.scene_ids)}
            for item in await rows(Location, col(Location.position), col(Location.id))
        ],
        beats=[
            {"id": item.id, "act_id": item.act_id, "position": item.position, "title": item.title, "beat_type": item.beat_type, "scene_ids": list(item.scene_ids)}
            for item in await rows(StoryBeat, col(StoryBeat.act_id), col(StoryBeat.position))
        ],
        facts=[
            {"id": item.id, "kind": item.kind, "label": item.label, "description": item.description or ""}
            for item in await rows(KnowledgeNode, col(KnowledgeNode.id))
        ],
    )


def host_objects(script: ScriptView, story: StoryView) -> dict[str, ClassInstance]:
    """Wrap both views for the sandbox, exposing only their data and their read-only methods."""
    return {
        "script": ClassInstance(script, eager_attrs=("title", "scenes"), allowed_methods=SCRIPT_METHODS),
        "story": ClassInstance(
            story,
            eager_attrs=("title", "logline", "characters", "relationships", "events", "locations", "beats", "facts"),
            allowed_methods=STORY_METHODS,
        ),
    }


def plain(value: Any) -> Any:
    """Return a sandbox result as JSON-safe values (tuples and sets become lists; the rest strings)."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, dict):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [plain(item) for item in value]
    if isinstance(value, ScriptView | StoryView):
        return f"<{type(value).__name__}>"
    return str(value)


@dataclass(frozen=True)
class AnalysisResult:
    """What one analysis returned: its JSON-safe value, printed output and duration."""

    value: Any
    stdout: str
    duration_ms: int


def code_config() -> MontyExecutionConfig:
    """Return the installation's Monty limits."""
    return execution_config(settings.monty)


async def run_analysis(
    session: AsyncSession,
    project_id: int,
    code: str,
    *,
    run_id: int | None = None,
    config: MontyExecutionConfig | None = None,
    purpose: str = "analyze_script",
) -> AnalysisResult:
    """Run code over the project's ``script`` and ``story`` views in Monty, audited, and return its value."""
    effective = config or code_config()
    script = await load_script_view(session, project_id)
    story = await load_story_view(session, project_id)
    result: MontyExecutionResult = await execute_glue_audited(
        session, project_id, code, host_objects(script, story), effective, run_id=run_id, purpose=purpose
    )
    value = plain(result.value)
    if len(json.dumps(value, default=str)) > effective.max_output_chars:
        raise MontySandboxError("Analysis result exceeds the configured output limit", "return a smaller result")
    return AnalysisResult(value=value, stdout=result.stdout, duration_ms=result.duration_ms)


async def analyze_script(
    session: AsyncSession, project_id: int, code: str, *, run_id: int | None = None, config: MontyExecutionConfig | None = None
) -> AnalysisResult:
    """Run read-only analysis code over the script and Story twin; its last expression is the result."""
    return await run_analysis(session, project_id, code, run_id=run_id, config=config)
