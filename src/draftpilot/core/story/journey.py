"""The Journey map for agents: a compact summary of the lanes, the shared moments and the arc check.

``journey_summary`` is what ``read_journey`` returns and what the arc-check workflow reads. The
findings are deterministic, so the check is the same every time the map is the same:

- a **flat arc**: a lane whose intensity barely moves (a range of one step or less);
- **never turns**: a lane whose intensity only rises or only falls;
- **never crosses the protagonist**: a character who shares no moment and no scene with the lead;
- **too few cards**: a lane with a single card, too thin to read an arc from.

Characters with no cards at all get no findings: they are not on the map yet.
"""

from itertools import pairwise
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.errors import Invalid, check_version
from draftpilot.core.story import entities
from draftpilot.core.story.proposals import propose_story_change
from draftpilot.core.story.structure import require_project
from draftpilot.models import AgentProposal

# The Journey map's own fields on a timeline event: what an agent may propose for one card.
JOURNEY_EVENT_FIELDS = (
    "motivation",
    "history",
    "intensity",
    "chrono_index",
    "moment_id",
)
FindingKind = Literal[
    "flat_arc", "never_turns", "never_crosses_protagonist", "too_few_cards"
]
MOTIVATION_CHARS = 160


class JourneyEvent(BaseModel):
    """One card on a lane, in story order."""

    id: int
    title: str
    story_time: str
    chrono_index: float | None
    intensity: int
    motivation: str
    scene_id: int | None
    beat_id: int | None
    moment_id: int | None


class JourneyLane(BaseModel):
    """One character's lane: their cards in story order and the shape of their intensity."""

    character_id: int
    name: str
    role: str
    events: list[JourneyEvent]
    intensity_low: int | None
    intensity_high: int | None
    turns: int
    crosses_protagonist: bool


class JourneyMoment(BaseModel):
    """A shared moment and the characters who take part in it."""

    id: int
    title: str
    story_time: str
    chrono_index: float | None
    scene_id: int | None
    beat_id: int | None
    character_ids: list[int]


class JourneyFinding(BaseModel):
    """One thing the arc check noticed about one lane."""

    kind: FindingKind
    character_id: int
    character: str
    detail: str


class JourneySummary(BaseModel):
    """The map in brief: lanes, shared moments, the protagonist and the arc check's findings."""

    protagonist_id: int | None
    lanes: list[JourneyLane]
    moments: list[JourneyMoment]
    findings: list[JourneyFinding]


def count_turns(values: list[int]) -> int:
    """Count how often a sequence changes direction (rising to falling or back), ignoring plateaus."""
    turns, direction = 0, 0
    for before, after in pairwise(values):
        step = (after > before) - (after < before)
        if step == 0:
            continue
        if direction and step != direction:
            turns += 1
        direction = step
    return turns


def _story_order(event: object) -> tuple[bool, float, int, int]:
    """Sort cards by story-world position (unplaced last), then lane position, then id."""
    chrono = getattr(event, "chrono_index", None)
    return (
        chrono is None,
        chrono or 0.0,
        getattr(event, "position", 0),
        getattr(event, "id", 0) or 0,
    )


def _findings(
    lane: JourneyLane, protagonist: tuple[int, str] | None
) -> list[JourneyFinding]:
    """Return what the arc check notices about one lane."""
    found: list[JourneyFinding] = []

    def add(kind: FindingKind, detail: str) -> None:
        """Record one finding for this lane."""
        found.append(
            JourneyFinding(
                kind=kind,
                character_id=lane.character_id,
                character=lane.name,
                detail=detail,
            )
        )

    values = [event.intensity for event in lane.events]
    if not values:
        return found  # a character with no cards isn't on the map yet (the Story twin lists every speaker)
    if len(values) < 2:
        add(
            "too_few_cards",
            f"{lane.name} has {len(values)} card{'s' if len(values) != 1 else ''} on the map, too few to read an arc.",
        )
    elif (
        lane.intensity_high is not None
        and lane.intensity_low is not None
        and lane.intensity_high - lane.intensity_low <= 1
    ):
        add(
            "flat_arc",
            f"{lane.name}'s intensity stays between {lane.intensity_low:+d} and {lane.intensity_high:+d} across {len(values)} cards.",
        )
    elif len(values) >= 3 and lane.turns == 0:
        rising = values[-1] > values[0]
        add(
            "never_turns",
            f"{lane.name}'s intensity only {'rises' if rising else 'falls'} ({values[0]:+d} to {values[-1]:+d}); it never turns.",
        )
    if (
        protagonist
        and lane.character_id != protagonist[0]
        and not lane.crosses_protagonist
    ):
        add(
            "never_crosses_protagonist",
            f"{lane.name} shares no moment and no scene with {protagonist[1]}.",
        )
    return found


async def journey_summary(session: AsyncSession, project_id: int) -> JourneySummary:
    """Summarise the Journey map: each lane in story order, the shared moments, and the arc check."""
    await require_project(session, project_id)
    characters = await entities.list_entities(session, project_id, "character")
    events = sorted(
        await entities.list_entities(session, project_id, "timeline_event"),
        key=_story_order,
    )
    moments = await entities.list_entities(session, project_id, "moment")
    moment_scene = {moment.id: moment.scene_id for moment in moments}

    members: dict[int, set[int]] = {}
    scenes_of: dict[int, set[int]] = {
        character.id: set(character.scene_ids or []) for character in characters
    }
    for event in events:
        if event.moment_id is not None:
            members.setdefault(event.moment_id, set()).add(event.character_id)
        scene_id = event.scene_id or moment_scene.get(event.moment_id)
        if scene_id is not None:
            scenes_of.setdefault(event.character_id, set()).add(scene_id)

    ordered = sorted(
        characters, key=lambda row: (row.role != "protagonist", row.position, row.id)
    )
    lead = next((row for row in ordered if row.role == "protagonist"), None)
    lead_moments = {
        moment_id for moment_id, ids in members.items() if lead and lead.id in ids
    }

    def crosses(character_id: int) -> bool:
        """Whether this character shares a moment or a scene with the protagonist."""
        if lead is None or character_id == lead.id:
            return True
        shared_moment = any(
            character_id in members.get(moment_id, set()) for moment_id in lead_moments
        )
        return shared_moment or bool(
            scenes_of.get(character_id, set()) & scenes_of.get(lead.id or 0, set())
        )

    lanes: list[JourneyLane] = []
    for character in ordered:
        cards = [event for event in events if event.character_id == character.id]
        values = [event.intensity for event in cards]
        lanes.append(
            JourneyLane(
                character_id=character.id,
                name=character.name,
                role=character.role,
                events=[
                    JourneyEvent(
                        id=event.id,
                        title=event.title,
                        story_time=event.story_time,
                        chrono_index=event.chrono_index,
                        intensity=event.intensity,
                        motivation=event.motivation[:MOTIVATION_CHARS],
                        scene_id=event.scene_id,
                        beat_id=event.beat_id,
                        moment_id=event.moment_id,
                    )
                    for event in cards
                ],
                intensity_low=min(values) if values else None,
                intensity_high=max(values) if values else None,
                turns=count_turns(values),
                crosses_protagonist=crosses(character.id),
            )
        )
    protagonist = (
        (lead.id, lead.name) if lead is not None and lead.id is not None else None
    )
    return JourneySummary(
        protagonist_id=protagonist[0] if protagonist else None,
        lanes=lanes,
        moments=[
            JourneyMoment(
                id=moment.id,
                title=moment.title,
                story_time=moment.story_time,
                chrono_index=moment.chrono_index,
                scene_id=moment.scene_id,
                beat_id=moment.beat_id,
                character_ids=sorted(members.get(moment.id, set())),
            )
            for moment in moments
        ],
        findings=[
            finding for lane in lanes for finding in _findings(lane, protagonist)
        ],
    )


def journey_text(summary: JourneySummary) -> str:
    """Render the summary as compact text for a prompt: one line per card, then moments and findings."""
    lines: list[str] = []
    for lane in summary.lanes:
        lead = " (protagonist)" if lane.character_id == summary.protagonist_id else ""
        lines.append(
            f"## {lane.name}{lead}, {lane.role or 'character'} — {len(lane.events)} cards, {lane.turns} turns"
        )
        for event in lane.events:
            when = f"[{event.story_time}] " if event.story_time else ""
            why = f" — because {event.motivation}" if event.motivation else ""
            lines.append(
                f"- #{event.id} {when}{event.title} (intensity {event.intensity:+d}){why}"
            )
    if summary.moments:
        names = {lane.character_id: lane.name for lane in summary.lanes}
        lines.append("## Shared moments")
        lines.extend(
            f"- {moment.title}: {', '.join(names.get(item, '?') for item in moment.character_ids) or 'nobody yet'}"
            for moment in summary.moments
        )
    if summary.findings:
        lines.append("## Findings")
        lines.extend(
            f"- {finding.kind}: {finding.detail}" for finding in summary.findings
        )
    return "\n".join(lines)


class JourneyEventChange(BaseModel):
    """A proposed change to one card's journey fields (only the fields given are changed)."""

    motivation: str | None = Field(default=None, max_length=2000)
    history: str | None = Field(default=None, max_length=4000)
    intensity: int | None = Field(default=None, ge=-5, le=5)
    chrono_index: float | None = None
    moment_id: int | None = None
    summary: str = Field(default="", max_length=500)


class SharedMomentProposal(BaseModel):
    """A proposed shared moment and the cards (from two or more characters) that would join it."""

    title: str = Field(min_length=1, max_length=300)
    event_ids: list[int] = Field(min_length=2, max_length=20)
    description: str = Field(default="", max_length=4000)
    story_time: str = Field(default="", max_length=100)
    chrono_index: float | None = None
    scene_id: int | None = None
    summary: str = Field(default="", max_length=500)


class MomentParticipants(BaseModel):
    """The cards that make up a shared moment (any card left out leaves it)."""

    event_ids: list[int] = Field(max_length=40)
    expected_version: int = Field(ge=1)


async def propose_event_change(
    session: AsyncSession,
    project_id: int,
    event_id: int,
    change: JourneyEventChange,
    *,
    run_id: int | None = None,
) -> AgentProposal:
    """Propose a card's motivation, history, intensity, story time or shared moment for the writer to approve."""
    fields = change.model_dump(include=set(JOURNEY_EVENT_FIELDS), exclude_unset=True)
    if not fields:
        raise Invalid(f"Propose at least one of: {', '.join(JOURNEY_EVENT_FIELDS)}")
    event = await entities.get_entity(session, project_id, "timeline_event", event_id)
    summary = change.summary or f"{event.title}: " + ", ".join(
        f"{name} → {value}" for name, value in fields.items()
    )
    return await propose_story_change(
        session,
        project_id,
        "timeline_event",
        "update",
        fields,
        entity_id=event_id,
        run_id=run_id,
        summary=summary[:500],
    )


async def propose_shared_moment(
    session: AsyncSession,
    project_id: int,
    proposal: SharedMomentProposal,
    *,
    run_id: int | None = None,
) -> AgentProposal:
    """Propose a shared moment; approving it creates the moment and links its participants' cards."""
    fields: dict[str, Any] = {
        "title": proposal.title,
        "summary": proposal.description,
        "story_time": proposal.story_time,
    }
    if proposal.chrono_index is not None:
        fields["chrono_index"] = proposal.chrono_index
    if proposal.scene_id is not None:
        fields["scene_id"] = proposal.scene_id
    return await propose_story_change(
        session,
        project_id,
        "moment",
        "create",
        fields,
        run_id=run_id,
        summary=proposal.summary or f"Shared moment: {proposal.title}",
        event_ids=proposal.event_ids,
    )


async def set_moment_participants(
    session: AsyncSession,
    project_id: int,
    moment_id: int,
    participants: MomentParticipants,
) -> list[Any]:
    """Make exactly these cards a shared moment's participants (the writer's direct edit); return them."""
    moment = await entities.get_entity(session, project_id, "moment", moment_id)
    check_version(participants.expected_version, moment.version, "Moment")
    wanted = set(participants.event_ids)
    rows = [
        await entities.get_entity(session, project_id, "timeline_event", event_id)
        for event_id in wanted
    ]
    current = await entities.list_entities(
        session, project_id, "timeline_event", moment_id=moment_id
    )
    for row in current:
        if row.id not in wanted:
            await entities.update_entity(
                session,
                project_id,
                "timeline_event",
                row.id,
                {"moment_id": None},
                expected_version=None,
                require_version=False,
            )
    for row in rows:
        if row.moment_id != moment_id:
            await entities.update_entity(
                session,
                project_id,
                "timeline_event",
                row.id,
                {"moment_id": moment_id},
                expected_version=None,
                require_version=False,
            )
    return await entities.list_entities(
        session, project_id, "timeline_event", moment_id=moment_id
    )
