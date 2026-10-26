"""Room workflows: the writers' room as repeatable, durable multi-agent workflows with a human gate at the end.

The workflows themselves are Temporal workflows in ``agents/room_workflows.py``. Each step
consults one room role for a typed output. This module holds what they share: the typed
outputs and parameters, the pure text helpers, the catalogue, and the activities that touch the
database (loading scenes, finding leads, and the gates that create proposals). Generative
workflows (outline, character arcs, scene rewrite, scene drafting) end in reviewable proposals the
writer approves, and analytic ones (brainstorm, audience panel, coverage, continuity) return a
report. Nothing is ever written to the script or story silently.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import timedelta
from statistics import mean
from typing import Any, Literal

import logfire
from pydantic import BaseModel, Field, field_validator
from sqlmodel.ext.asyncio.session import AsyncSession
from temporalio import activity
from temporalio.common import RetryPolicy

from draftpilot.agents.deps import RoomDeps
from draftpilot.core import events
from draftpilot.core.db import session_scope
from draftpilot.core.errors import NotFound
from draftpilot.core.scene_proposals import (
    append_operation,
    parse_scene_fountain,
    rewrite_operation,
    rewrite_snapshot,
)
from draftpilot.core.screenplay.adapters.fountain import render_fountain
from draftpilot.core.screenplay.hydrate import scene_to_doc
from draftpilot.core.screenplay.schema import ActDoc, BlockType, ScreenplayDoc
from draftpilot.core.story import entities as story_entities
from draftpilot.core.story.proposals import propose_outline as propose_outline_beats
from draftpilot.core.story.proposals import propose_story_change
from draftpilot.core.twins import normalize_cue, story_twin_brief, working_screenplay
from draftpilot.crud import agent_proposals as proposals_crud
from draftpilot.crud import scenes as scenes_crud
from draftpilot.crud import story_artifacts as artifacts_crud
from draftpilot.crud import workflow_runs as runs_crud
from draftpilot.models import AgentProposal, AgentRun, Scene, StoryArtifact

# ---------------------------------------------------------------------------------------------------------------------
# Typed outputs the room hands back to the graph
# ---------------------------------------------------------------------------------------------------------------------


class Beat(BaseModel):
    """One causally ordered story beat."""

    act: int = Field(ge=1, le=5, description="Act number (1-3 for a three-act feature).")
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=2000, description="What happens and why it matters.")


class Outline(BaseModel):
    """A logline plus an ordered beat outline."""

    logline: str = Field(min_length=1, max_length=500)
    beats: list[Beat] = Field(min_length=3, max_length=60)


class Critique(BaseModel):
    """A graded, actionable critique of a draft."""

    score: int = Field(ge=1, le=10, description="Overall quality from 1 (unusable) to 10 (ship it).")
    strengths: list[str] = Field(default_factory=list, max_length=8)
    problems: list[str] = Field(default_factory=list, max_length=8)
    fixes: list[str] = Field(default_factory=list, max_length=8, description="Specific changes, most important first.")


class Idea(BaseModel):
    """One pitched idea."""

    title: str = Field(min_length=1, max_length=200)
    pitch: str = Field(min_length=1, max_length=1500)
    why_it_works: str = Field(default="", max_length=800)


class IdeaSet(BaseModel):
    """The ideas one brainstorm lens produced."""

    ideas: list[Idea] = Field(min_length=1, max_length=10)


class Pick(BaseModel):
    """One shortlisted idea and why."""

    title: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=800)


class Shortlist(BaseModel):
    """The room's ranked shortlist and a one-paragraph synthesis."""

    picks: list[Pick] = Field(min_length=1, max_length=5)
    synthesis: str = Field(min_length=1, max_length=2000)


class CharacterArc(BaseModel):
    """One character's arc."""

    character: str = Field(min_length=1, max_length=200)
    want: str = Field(min_length=1, max_length=1000, description="The conscious, external goal.")
    need: str = Field(min_length=1, max_length=1000, description="The inner truth they must accept.")
    flaw: str = Field(default="", max_length=1000)
    turning_points: list[str] = Field(default_factory=list, max_length=10)
    arc_summary: str = Field(min_length=1, max_length=2000)


class SceneDraft(BaseModel):
    """One scene written in Fountain plus the writer-facing rationale."""

    fountain: str = Field(min_length=1, max_length=40_000, description="The full scene in Fountain, heading first.")
    rationale: str = Field(default="", max_length=2000)

    @field_validator("fountain")
    @classmethod
    def _parses_as_a_scene(cls, value: str) -> str:
        """Reject drafts that are not valid screenplay text, so the model retries."""
        parse_scene_fountain(value)
        return value


class Reaction(BaseModel):
    """One audience persona's reaction."""

    persona: str = Field(min_length=1, max_length=200)
    engagement: int = Field(ge=1, le=10)
    moved_by: list[str] = Field(default_factory=list, max_length=6)
    lost_at: list[str] = Field(default_factory=list, max_length=6)
    would_recommend: bool
    quote: str = Field(default="", max_length=500, description="What this viewer would say walking out.")


class Coverage(BaseModel):
    """Studio-style coverage."""

    logline: str = Field(min_length=1, max_length=500)
    synopsis: str = Field(min_length=1, max_length=4000)
    premise: int = Field(ge=1, le=10)
    structure: int = Field(ge=1, le=10)
    character: int = Field(ge=1, le=10)
    dialogue: int = Field(ge=1, le=10)
    pacing: int = Field(ge=1, le=10)
    strengths: list[str] = Field(default_factory=list, max_length=8)
    weaknesses: list[str] = Field(default_factory=list, max_length=8)
    verdict: Literal["pass", "consider", "recommend"]


class ContinuityIssue(BaseModel):
    """One continuity problem."""

    scene_ids: list[int] = Field(default_factory=list, max_length=10)
    kind: Literal["timeline", "character", "prop", "location", "fact", "other"]
    description: str = Field(min_length=1, max_length=1000)
    suggestion: str = Field(default="", max_length=1000)


class ContinuityReport(BaseModel):
    """Every continuity problem found (possibly none)."""

    issues: list[ContinuityIssue] = Field(default_factory=list, max_length=40)


# ---------------------------------------------------------------------------------------------------------------------
# Parameters each workflow accepts
# ---------------------------------------------------------------------------------------------------------------------


class OutlineParams(BaseModel):
    """Turn the writer's notes into a critiqued beat outline."""

    notes: str = Field(min_length=1, max_length=20_000)
    max_rounds: int = Field(default=2, ge=0, le=4)
    target_score: int = Field(default=8, ge=1, le=10)


class BrainstormParams(BaseModel):
    """Brainstorm a question through several lenses and shortlist the best."""

    topic: str = Field(min_length=1, max_length=4000)
    lenses: list[str] = Field(
        default_factory=lambda: ["character-driven", "genre twist", "visual set piece"], min_length=1, max_length=6
    )


class ArcParams(BaseModel):
    """Develop arcs for named characters, or the leads of the Story twin."""

    characters: list[str] = Field(default_factory=list, max_length=8)
    top: int = Field(default=3, ge=1, le=8)


class RewriteParams(BaseModel):
    """Rewrite one scene to a brief through a draft-critique loop."""

    scene_id: int
    brief: str = Field(min_length=1, max_length=4000)
    max_rounds: int = Field(default=2, ge=0, le=4)
    target_score: int = Field(default=8, ge=1, le=10)


class DraftBeat(BaseModel):
    """A beat to dramatise as a new scene."""

    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=2000)


class DraftScenesParams(BaseModel):
    """Draft new scenes from beats (given, or the outline artifact's beats)."""

    beats: list[DraftBeat] = Field(default_factory=list, max_length=12)
    outline_artifact_id: int | None = None
    limit: int = Field(default=4, ge=1, le=12)


class PanelParams(BaseModel):
    """Test the script (or some scenes) on a panel of audience personas."""

    focus: str = Field(default="", max_length=2000)
    scene_ids: list[int] = Field(default_factory=list, max_length=40)
    personas: list[str] = Field(
        default_factory=lambda: [
            "Genre fan who loves big emotional swings",
            "Arthouse critic who punishes cliché",
            "Casual streamer watching on a phone",
            "Studio executive thinking about the market",
        ],
        min_length=1,
        max_length=8,
    )


class CoverageParams(BaseModel):
    """Write studio coverage of the working draft."""

    focus: str = Field(default="", max_length=2000)


class StorylineDraft(BaseModel):
    """A developed storyline: what the film is about, in a few precise fields."""

    title: str = Field(min_length=1, max_length=200)
    logline: str = Field(min_length=1, max_length=500)
    premise: str = Field(min_length=1, max_length=2000, description="The dramatic question and why it matters.")
    synopsis: str = Field(min_length=1, max_length=6000, description="A one-page synopsis, beginning to end.")
    theme: str = Field(min_length=1, max_length=1000)
    tone: str = Field(min_length=1, max_length=500)


class CastMember(BaseModel):
    """One character as the room proposes them."""

    name: str = Field(min_length=1, max_length=200)
    role: str = Field(default="supporting", description="protagonist, antagonist, supporting or minor")
    summary: str = Field(min_length=1, max_length=1000)
    want: str = Field(min_length=1, max_length=1000, description="The conscious, external goal.")
    need: str = Field(min_length=1, max_length=1000, description="The inner truth they must accept.")
    motive: str = Field(default="", max_length=1000)
    objective: str = Field(default="", max_length=1000, description="What they concretely pursue in the story.")
    flaw: str = Field(default="", max_length=1000)
    arc_summary: str = Field(default="", max_length=2000)
    voice: str = Field(default="", max_length=1000)


class Cast(BaseModel):
    """The principal cast."""

    characters: list[CastMember] = Field(min_length=1, max_length=8)


class TimelineMoment(BaseModel):
    """One moment of a character's personal timeline."""

    story_time: str = Field(default="", max_length=100)
    title: str = Field(min_length=1, max_length=300)
    objective: str = Field(default="", max_length=1000)
    emotional_state: str = Field(default="", max_length=300)


class CharacterTimeline(BaseModel):
    """A character's arc as moments in story order."""

    moments: list[TimelineMoment] = Field(min_length=2, max_length=10)


PipelineStage = Literal["storyline", "characters", "timelines", "outline", "scenes", "coverage"]
PIPELINE_STAGES: tuple[PipelineStage, ...] = ("storyline", "characters", "timelines", "outline", "scenes", "coverage")


class DevelopStoryParams(BaseModel):
    """Develop a story from an idea through storyline, cast, timelines, outline and first scenes."""

    idea: str = Field(min_length=1, max_length=20_000, description="The premise, notes or pitch to develop.")
    stages: list[PipelineStage] = Field(default_factory=lambda: list(PIPELINE_STAGES))
    cast_size: int = Field(default=4, ge=1, le=8)
    outline_rounds: int = Field(default=1, ge=0, le=3)
    draft_beats: int = Field(default=3, ge=0, le=12, description="How many outline beats to draft as scenes.")
    wait_hours: int = Field(default=72, ge=1, le=24 * 30, description="How long to wait for the writer at each checkpoint.")


class ContinuityParams(BaseModel):
    """Check continuity across the draft (or some scenes)."""

    focus: str = Field(default="", max_length=2000)
    scene_ids: list[int] = Field(default_factory=list, max_length=60)


# ---------------------------------------------------------------------------------------------------------------------
# What a run carries, and the prompts every step shares
# ---------------------------------------------------------------------------------------------------------------------


@dataclass
class RoomRunInput:
    """Start a room workflow: which one, its validated parameters, and the room's context and model."""

    workflow: str
    params: dict[str, Any]
    room: RoomDeps


@dataclass
class ProgressUpdate:
    """The trail so far, for the run's Postgres copy and the live trail in the studio."""

    run_id: int | None
    project_id: int
    workflow: str
    trail: list[dict[str, Any]]


STEP_GUIDANCE = (
    "You are one step of a writers' room workflow. Work from the material above; use DraftPilot tools only "
    "to check something it does not contain, and read as little as you need. Submit your result with the output tool."
)


SELF_CONTAINED = (
    "You are one step of a writers' room workflow. Everything you need is above. "
    "Submit your result with the output tool."
)

# Database steps are quick; a ValueError is the workflow's own "cannot do this" and never retried.
STEP_ACTIVITY: dict[str, Any] = {
    "start_to_close_timeout": timedelta(minutes=2),
    "retry_policy": RetryPolicy(maximum_attempts=3, non_retryable_error_types=["ValueError", "KeyError", "LookupError"]),
}


def critique_text(critique: Critique) -> str:
    """Render a critique for the next revision prompt."""
    return (
        f"Score {critique.score}/10.\nProblems:\n- " + "\n- ".join(critique.problems or ["(none)"])
        + "\nFixes, most important first:\n- " + "\n- ".join(critique.fixes or ["(none)"])
    )


def outline_text(outline: Outline) -> str:
    """Render an outline as numbered beats."""
    beats = "\n".join(f"{index}. [Act {beat.act}] {beat.title}: {beat.summary}" for index, beat in enumerate(outline.beats, 1))
    return f"Logline: {outline.logline}\n{beats}"


def markdown_outline(outline: Outline) -> str:
    """Render an outline as the markdown an outline artifact holds."""
    lines = [f"**Logline:** {outline.logline}", ""]
    for act in sorted({beat.act for beat in outline.beats}):
        lines.append(f"## Act {act}")
        lines.extend(f"- **{beat.title}** — {beat.summary}" for beat in outline.beats if beat.act == act)
        lines.append("")
    return "\n".join(lines).strip()


REWRITE_RULES = (
    "Keep the same speaking characters unless the brief asks for new ones. Honour every length instruction "
    "in the brief: 'shorter' means fewer words than the current scene."
)


def _speakers(fountain: str) -> set[str]:
    """Return the normalised character cues of a Fountain scene."""
    doc = parse_scene_fountain(fountain)
    return {normalize_cue(block.text) for block in doc.blocks if block.element_type == BlockType.CHARACTER}


def rewrite_facts(original: str, rewrite: str) -> str:
    """Measure what a grader should not have to guess: relative length and any added speakers."""
    ratio = round(100 * len(rewrite.split()) / max(1, len(original.split())))
    added = sorted(_speakers(rewrite) - _speakers(original))
    return f"the rewrite is {ratio}% of the original's length in words; " + (
        f"new speaking characters: {', '.join(added)}." if added else "no new speaking characters."
    )


def scope_text(scene_ids: list[int], focus: str) -> str:
    """Describe which part of the script a read covers."""
    scope = f"Read scenes {scene_ids} (use read_screenplay_scenes with scene_ids)." if scene_ids else "Read the script economically."
    return scope + (f" Focus: {focus}" if focus else "")


def summarize_panel(reactions: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate persona reactions into engagement, recommendation rate, and shared sticking points."""
    lost: dict[str, int] = {}
    for reaction in reactions:
        for item in reaction.get("lost_at", []):
            lost[item] = lost.get(item, 0) + 1
    return {
        "mean_engagement": round(mean(item["engagement"] for item in reactions), 2) if reactions else 0,
        "recommend_rate": round(sum(1 for item in reactions if item["would_recommend"]) / len(reactions), 2) if reactions else 0,
        "shared_sticking_points": [item for item, count in sorted(lost.items(), key=lambda pair: -pair[1]) if count > 1],
    }


# ---------------------------------------------------------------------------------------------------------------------
# Activities: every database read and write a workflow makes
# ---------------------------------------------------------------------------------------------------------------------


async def _artifact(session: AsyncSession, project_id: int, kind: str, title: str) -> StoryArtifact:
    """Return the project's artifact of a kind, creating an empty one to propose into."""
    for artifact in await artifacts_crud.list_for_project(session, project_id):
        if artifact.kind == kind:
            return artifact
    artifact = StoryArtifact(project_id=project_id, kind=kind, title=title)
    session.add(artifact)
    await session.commit()
    await session.refresh(artifact)
    return artifact


async def _propose_artifact(
    session: AsyncSession, project_id: int, run_id: int | None, artifact: StoryArtifact, operation: dict[str, Any], summary: str
) -> int:
    """Create a reviewable artifact proposal and return its id."""
    proposal = await proposals_crud.create(
        session,
        AgentProposal(
            project_id=project_id,
            run_id=run_id,
            target_kind="artifact",
            target_id=artifact.id or 0,
            operation=operation,
            diff={"summary": summary},
            before={key: getattr(artifact, key) for key in operation},
            base_version=artifact.version,
        ),
    )
    return proposal.id or 0


async def lead_characters(session: AsyncSession, project_id: int, top: int) -> list[str]:
    """Return the leads: protagonists first, then the characters with the most dialogue."""
    rows = await story_entities.list_entities(session, project_id, "character")
    rows.sort(key=lambda row: (row.role != "protagonist", -row.dialogue_lines, row.position))
    return [row.name for row in rows[:top]]


async def _project_scene(session: AsyncSession, project_id: int, scene_id: int) -> Scene:
    """Return a scene of the project's working draft or raise."""
    screenplay = await working_screenplay(session, project_id)
    scenes = await scenes_crud.list_for_screenplay(session, screenplay.id or 0) if screenplay else []
    scene = next((item for item in scenes if item.id == scene_id), None)
    if scene is None:
        raise ValueError("Scene is not in the project's working draft")
    return scene


async def scene_fountain(session: AsyncSession, scene: Scene) -> str:
    """Render one persisted scene as Fountain."""
    doc = await scene_to_doc(session, scene)
    return render_fountain(ScreenplayDoc(acts=[ActDoc(scenes=[doc])])).strip()


@activity.defn(name="room_record_progress")
async def record_progress(update: ProgressUpdate) -> bool:
    """Persist the trail so far on the run and publish it; return whether the writer cancelled the run."""
    if update.run_id is None:
        return False
    async with session_scope() as session:
        current = await runs_crud.get(session, update.run_id)
        if current is None or current.status == "cancelled":
            return True
        current.result = {"workflow": update.workflow, "stage": "running", "trail": update.trail}
        session.add(current)
        await session.commit()
    await events.publish(
        update.project_id, "workflow.progress", {"run_id": update.run_id, "steps": len(update.trail), "last": update.trail[-1]["step"]}
    )
    return False


@activity.defn(name="room_record_agent_run")
async def record_agent_run(fields: dict[str, Any]) -> int:
    """Persist one step's AgentRun and return its id."""
    from draftpilot.agents.runtime import save_agent_run

    record = await save_agent_run(AgentRun.model_validate(fields))
    return record.id or 0


@activity.defn(name="room_lead_characters")
async def find_leads(project_id: int, top: int) -> list[str]:
    """Return the Story twin's leads, failing when there are none to develop."""
    async with session_scope() as session:
        leads = await lead_characters(session, project_id, top)
    if not leads:
        raise ValueError("No characters named and the Story twin has none yet")
    return leads


@activity.defn(name="room_load_scene")
async def load_scene(project_id: int, scene_id: int) -> str:
    """Return one working-draft scene as Fountain."""
    async with session_scope() as session:
        scene = await _project_scene(session, project_id, scene_id)
        return await scene_fountain(session, scene)


@activity.defn(name="room_outline_beats")
async def outline_beats(project_id: int, outline_artifact_id: int | None) -> list[dict[str, Any]]:
    """Return the outline's beats: the typed beats (with their ids), else those on the outline artifact."""
    async with session_scope() as session:
        if outline_artifact_id is None:
            beats = await story_entities.list_entities(session, project_id, "beat")
            if beats:
                return [{"title": beat.title, "summary": beat.summary or beat.title, "beat_id": beat.id} for beat in beats if beat.status != "cut"]
        artifacts = await artifacts_crud.list_for_project(session, project_id)
    outline = next(
        (item for item in artifacts if item.id == outline_artifact_id or (outline_artifact_id is None and item.kind == "outline")),
        None,
    )
    return list((outline.artifact_metadata.get("beats") if outline else None) or [])


@activity.defn(name="room_known_scenes")
async def known_scene_ids(project_id: int) -> list[int]:
    """Return the ids of every scene in the project's working draft."""
    async with session_scope() as session:
        screenplay = await working_screenplay(session, project_id)
        scenes = await scenes_crud.list_for_screenplay(session, screenplay.id or 0) if screenplay else []
    return [scene.id for scene in scenes if scene.id is not None]


@activity.defn(name="room_propose_outline")
async def propose_outline(project_id: int, run_id: int | None, outline: Outline) -> list[int]:
    """Propose the logline onto the storyline and the beats as the outline."""
    async with session_scope() as session:
        logline = await propose_story_change(
            session, project_id, "storyline", "update", {"logline": outline.logline}, run_id=run_id, summary="Logline from your notes"
        )
        beats = await propose_outline_beats(
            session,
            project_id,
            [beat.model_dump() for beat in outline.beats],
            run_id=run_id,
            summary=f"{len(outline.beats)}-beat outline",
        )
        return [logline.id or 0, beats.id or 0]


@activity.defn(name="room_propose_arcs")
async def propose_arcs(project_id: int, run_id: int | None, arcs: list[dict[str, Any]]) -> list[int]:
    """Propose each arc onto its character profile, plus a timeline event per turning point."""
    proposal_ids: list[int] = []
    async with session_scope() as session:
        cast_rows = {row.name.casefold(): row for row in await story_entities.list_entities(session, project_id, "character")}
        for item in arcs:
            fields = {
                "want": item["want"],
                "need": item["need"],
                "arc_summary": item["arc_summary"],
                **({"flaw": item["flaw"]} if item.get("flaw") else {}),
            }
            row = cast_rows.get(str(item["character"]).casefold())
            if row is None:
                turning = "\n".join(f"- {point}" for point in item.get("turning_points") or [])
                proposal = await propose_story_change(
                    session,
                    project_id,
                    "character",
                    "create",
                    {"name": item["character"], **fields, **({"notes": f"Turning points:\n{turning}"} if turning else {})},
                    run_id=run_id,
                    summary=f"New character {item['character']} with an arc",
                )
                proposal_ids.append(proposal.id or 0)
                continue
            proposal = await propose_story_change(
                session, project_id, "character", "update", fields, entity_id=row.id, run_id=run_id, summary=f"Arc for {row.name}"
            )
            proposal_ids.append(proposal.id or 0)
            for position, point in enumerate(item.get("turning_points") or []):
                event = await propose_story_change(
                    session,
                    project_id,
                    "timeline_event",
                    "create",
                    {"character_id": row.id, "position": position, "title": str(point)[:300]},
                    run_id=run_id,
                    summary=f"{row.name}: turning point {position + 1}",
                )
                proposal_ids.append(event.id or 0)
    return proposal_ids


@activity.defn(name="room_propose_rewrite")
async def propose_rewrite(project_id: int, run_id: int | None, scene_id: int, brief: str, draft: SceneDraft) -> list[int]:
    """Propose the rewrite as one reversible scene change."""
    async with session_scope() as session:
        scene = await _project_scene(session, project_id, scene_id)
        proposal = await proposals_crud.create(
            session,
            AgentProposal(
                project_id=project_id,
                run_id=run_id,
                target_kind="scene",
                target_id=scene.id or 0,
                operation=rewrite_operation(parse_scene_fountain(draft.fountain)),
                diff={"summary": f"Rewrite: {brief[:200]}", "rationale": draft.rationale},
                before=await rewrite_snapshot(session, scene),
                base_version=scene.version,
            ),
        )
    return [proposal.id or 0]


@activity.defn(name="room_propose_scenes")
async def propose_scenes(project_id: int, run_id: int | None, drafts: list[dict[str, Any]]) -> list[int]:
    """Propose every drafted scene, in beat order, appended to the working draft."""
    async with session_scope() as session:
        screenplay = await working_screenplay(session, project_id)
        if screenplay is None:
            raise ValueError("The project has no screenplay to draft into")
        proposal = await proposals_crud.create(
            session,
            AgentProposal(
                project_id=project_id,
                run_id=run_id,
                target_kind="screenplay",
                target_id=screenplay.id or 0,
                operation=append_operation([parse_scene_fountain(item["fountain"]) for item in drafts]),
                diff={"summary": f"{len(drafts)} new scenes: " + "; ".join(item["title"] for item in drafts)},
                before={},
                base_version=1,
            ),
        )
    return [proposal.id or 0]


@activity.defn(name="room_story_brief")
async def story_brief(project_id: int) -> str:
    """Return the current Story twin brief (it changes as the writer approves each stage)."""
    async with session_scope() as session:
        return await story_twin_brief(session, project_id)


@activity.defn(name="room_propose_storyline")
async def propose_storyline(project_id: int, run_id: int | None, draft: StorylineDraft) -> list[int]:
    """Propose the developed storyline as one storyline change."""
    async with session_scope() as session:
        proposal = await propose_story_change(
            session, project_id, "storyline", "update", draft.model_dump(), run_id=run_id, summary=f"Storyline: {draft.logline}"
        )
    return [proposal.id or 0]


@activity.defn(name="room_propose_beats")
async def propose_beats(project_id: int, run_id: int | None, outline: Outline) -> list[int]:
    """Propose an outline's beats (without its logline) as the project outline."""
    async with session_scope() as session:
        proposal = await propose_outline_beats(
            session, project_id, [beat.model_dump() for beat in outline.beats], run_id=run_id, summary=f"{len(outline.beats)}-beat outline"
        )
    return [proposal.id or 0]


@activity.defn(name="room_propose_cast")
async def propose_cast(project_id: int, run_id: int | None, cast: Cast) -> list[int]:
    """Propose each cast member (a new character, or an update to one who already exists)."""
    ids: list[int] = []
    async with session_scope() as session:
        existing = {row.name.casefold(): row for row in await story_entities.list_entities(session, project_id, "character")}
        for member in cast.characters:
            fields = {key: value for key, value in member.model_dump().items() if value}
            row = existing.get(member.name.casefold())
            if row is None:
                proposal = await propose_story_change(session, project_id, "character", "create", fields, run_id=run_id, summary=f"New character: {member.name}")
            else:
                fields.pop("name", None)
                proposal = await propose_story_change(
                    session, project_id, "character", "update", fields, entity_id=row.id, run_id=run_id, summary=f"Develop {row.name}"
                )
            ids.append(proposal.id or 0)
    return ids


@activity.defn(name="room_proposal_states")
async def proposal_states(project_id: int, proposal_ids: list[int]) -> dict[int, dict[str, Any]]:
    """Return each proposal's status and what approving it created (by proposal id)."""
    async with session_scope() as session:
        rows = [await proposals_crud.get(session, proposal_id) for proposal_id in proposal_ids]
    return {
        row.id or 0: {"status": row.status, "target_kind": row.target_kind, "target_id": row.target_id, "created_id": row.diff.get("created_id"), "created_scene_ids": row.diff.get("created_scene_ids")}
        for row in rows
        if row is not None and row.project_id == project_id
    }


@activity.defn(name="room_cast_ids")
async def cast_ids(project_id: int, names: list[str]) -> dict[str, int]:
    """Return the ids of the named characters that now exist."""
    async with session_scope() as session:
        rows = await story_entities.list_entities(session, project_id, "character")
    wanted = {name.casefold() for name in names}
    return {row.name: row.id or 0 for row in rows if row.name.casefold() in wanted}


@activity.defn(name="room_propose_timeline")
async def propose_timeline(project_id: int, run_id: int | None, character_id: int, name: str, timeline: CharacterTimeline) -> list[int]:
    """Propose a character's timeline moments, in order."""
    ids: list[int] = []
    async with session_scope() as session:
        for position, moment in enumerate(timeline.moments):
            proposal = await propose_story_change(
                session,
                project_id,
                "timeline_event",
                "create",
                {"character_id": character_id, "position": position, **moment.model_dump()},
                run_id=run_id,
                summary=f"{name}: {moment.title}",
            )
            ids.append(proposal.id or 0)
    return ids


@activity.defn(name="room_link_beat_scenes")
async def link_beat_scenes(project_id: int, links: list[list[int]]) -> int:
    """Link approved scenes to the beats they dramatise (``[beat_id, scene_id]`` pairs) and mark the beats drafted."""
    linked = 0
    async with session_scope() as session:
        for beat_id, scene_id in links:
            try:
                beat = await story_entities.get_entity(session, project_id, "beat", beat_id)
            except NotFound:
                logfire.info("Beat {beat_id} is gone; its scene stays unlinked", beat_id=beat_id)
                continue
            await story_entities.update_entity(
                session,
                project_id,
                "beat",
                beat_id,
                {"scene_ids": sorted({*beat.scene_ids, scene_id}), "status": "drafted"},
                expected_version=None,
                require_version=False,
                source="agent",
            )
            linked += 1
    return linked


ROOM_ACTIVITIES: list[Callable[..., Any]] = [
    record_progress,
    record_agent_run,
    find_leads,
    load_scene,
    outline_beats,
    known_scene_ids,
    propose_outline,
    propose_arcs,
    propose_rewrite,
    propose_scenes,
    story_brief,
    propose_beats,
    propose_storyline,
    propose_cast,
    proposal_states,
    cast_ids,
    propose_timeline,
    link_beat_scenes,
]


# ---------------------------------------------------------------------------------------------------------------------
# Catalogue and entry points
# ---------------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class RoomWorkflow:
    """One room workflow: what it does, its parameters, and whether it ends in proposals."""

    key: str
    label: str
    description: str
    params: type[BaseModel]
    roles: tuple[str, ...]
    proposes: bool

    @property
    def type_name(self) -> str:
        """Return the Temporal workflow type that runs it."""
        return f"room:{self.key}"


ROOM_WORKFLOWS: dict[str, RoomWorkflow] = {
    workflow.key: workflow
    for workflow in (
        RoomWorkflow("notes_to_outline", "Notes → outline", "Turn your notes into a logline and beat outline, critiqued and revised.", OutlineParams, ("story_editor", "script_doctor"), True),
        RoomWorkflow("draft_scenes", "Outline → scenes", "Draft new scenes from outline beats, in parallel.", DraftScenesParams, ("scene_writer",), True),
        RoomWorkflow("rewrite_scene", "Rewrite a scene", "Rewrite one scene to your brief through a draft-critique loop.", RewriteParams, ("scene_writer", "script_doctor"), True),
        RoomWorkflow("character_arcs", "Character arcs", "Develop want, need, flaw and turning points for your leads.", ArcParams, ("character_specialist",), True),
        RoomWorkflow("brainstorm", "Brainstorm", "Pitch ideas through several lenses in parallel, then shortlist.", BrainstormParams, ("brainstormer", "story_architect"), False),
        RoomWorkflow("audience_panel", "Audience panel", "Test the script on a panel of viewer personas.", PanelParams, ("audience_evaluator",), False),
        RoomWorkflow("coverage", "Coverage", "Studio-style coverage with graded craft and a verdict.", CoverageParams, ("coverage_reader",), False),
        RoomWorkflow("continuity", "Continuity pass", "Find timeline, character, prop and fact inconsistencies.", ContinuityParams, ("continuity_supervisor",), False),
        RoomWorkflow(
            "develop_story",
            "Develop the story",
            "From an idea to storyline, cast, character timelines, a critiqued outline and first scenes — pausing for your approval after each stage.",
            DevelopStoryParams,
            ("story_architect", "character_specialist", "story_editor", "script_doctor", "scene_writer", "coverage_reader"),
            True,
        ),
    )
}


def validate_params(key: str, params: dict[str, Any]) -> BaseModel:
    """Validate a workflow's parameters, raising ``KeyError`` for an unknown workflow."""
    return ROOM_WORKFLOWS[key].params.model_validate(params)


ProgressHook = Callable[[list[dict[str, Any]]], Awaitable[None]]


@dataclass
class WorkflowDeps:
    """Run a room workflow outside the worker: a model instance or ref, the room context, and a progress hook."""

    model: Any
    provider: str
    model_name: str
    room: RoomDeps
    run_id: int | None = None
    progress: ProgressHook | None = None


def _raised(error: BaseException) -> BaseException:
    """Return the application error a Temporal failure wraps, as the builtin type it was raised as."""
    from temporalio.exceptions import ApplicationError

    current: BaseException | None = error
    found: ApplicationError | None = None
    while current is not None:
        if isinstance(current, ApplicationError):
            found = current
        current = getattr(current, "cause", None) or current.__cause__
    if found is None:
        return error
    kind = {"ValueError": ValueError, "KeyError": KeyError, "RuntimeError": RuntimeError}.get(found.type or "", RuntimeError)
    return kind(found.message)


async def run_room_workflow(key: str, params: dict[str, Any], deps: WorkflowDeps) -> dict[str, Any]:
    """Run one room workflow to its gate on an embedded Temporal test server (evals, tests and scripts).

    It is the same durable workflow the worker runs, with the same activities. Only the progress
    activity is replaced, so ``deps.progress`` sees the trail.
    """
    from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
    from temporalio.client import Client, WorkflowFailureError
    from temporalio.testing import WorkflowEnvironment
    from temporalio.worker import Worker

    from draftpilot.agents.room_workflows import ROOM_WORKFLOW_CLASSES
    from draftpilot.agents.runtime import room_agent_activities, run_model

    validate_params(key, params)
    room = replace(deps.room, model_ref=run_model(deps.model, deps.room), workflow_run_id=deps.run_id)

    @activity.defn(name="room_record_progress")
    async def report(update: ProgressUpdate) -> bool:
        """Hand the trail to the caller's hook instead of a run row."""
        if deps.progress is not None:
            await deps.progress(update.trail)
        return False

    activities = [report if item is record_progress else item for item in ROOM_ACTIVITIES] + room_agent_activities()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        config = env.client.config()
        config["plugins"] = [PydanticAIPlugin()]
        client = Client(**config)
        queue = f"room-{uuid.uuid4().hex}"
        async with Worker(client, task_queue=queue, workflows=ROOM_WORKFLOW_CLASSES, activities=activities):
            try:
                result: dict[str, Any] = await client.execute_workflow(
                    ROOM_WORKFLOWS[key].type_name,
                    RoomRunInput(workflow=key, params=params, room=room),
                    id=f"room-{key}-{uuid.uuid4().hex}",
                    task_queue=queue,
                    result_type=dict,
                )
            except WorkflowFailureError as exc:
                raise _raised(exc) from exc
    return result
