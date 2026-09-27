"""Room workflows: the writers' room as repeatable multi-agent graphs with a human gate at the end.

Each workflow is a ``pydantic_graph`` graph whose steps consult room roles for typed outputs.
Generative workflows (outline, character arcs, scene rewrite, scene drafting) end in reviewable
proposals the writer approves; analytic ones (brainstorm, audience panel, coverage, continuity)
return a report. Nothing is ever written to the script or story silently.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from statistics import mean
from time import monotonic
from typing import TYPE_CHECKING, Any, Literal, Protocol

from pydantic import BaseModel, Field, field_validator
from pydantic_graph import GraphBuilder, StepContext, reduce_list_append
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.agents.deps import RoomDeps
from draftpilot.agents.runtime import run_role
from draftpilot.agents.specs import role_spec
from draftpilot.core.db import session_scope
from draftpilot.core.scene_proposals import (
    append_operation,
    parse_scene_fountain,
    rewrite_operation,
    rewrite_snapshot,
)
from draftpilot.core.screenplay.adapters.fountain import render_fountain
from draftpilot.core.screenplay.hydrate import scene_to_doc
from draftpilot.core.screenplay.schema import ActDoc, ScreenplayDoc
from draftpilot.core.twins import working_screenplay
from draftpilot.crud import agent_proposals as proposals_crud
from draftpilot.crud import knowledge_graph as graph_crud
from draftpilot.crud import scenes as scenes_crud
from draftpilot.crud import story_artifacts as artifacts_crud
from draftpilot.models import AgentProposal, Scene, StoryArtifact

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


class ContinuityParams(BaseModel):
    """Check continuity across the draft (or some scenes)."""

    focus: str = Field(default="", max_length=2000)
    scene_ids: list[int] = Field(default_factory=list, max_length=60)


# ---------------------------------------------------------------------------------------------------------------------
# Graph state, deps, and the one consult helper every step uses
# ---------------------------------------------------------------------------------------------------------------------

ProgressHook = Callable[[list[dict[str, Any]]], Awaitable[None]]


@dataclass
class WorkflowDeps:
    """What every step needs: the model, the room context, and where to report progress."""

    model: Any
    provider: str
    model_name: str
    room: RoomDeps
    run_id: int | None = None
    progress: ProgressHook | None = None


@dataclass
class WorkflowState:
    """The trail of consultations plus working values a loop carries between rounds."""

    trail: list[dict[str, Any]] = field(default_factory=list)
    rounds: int = 0
    draft: Any = None
    critique: Critique | None = None
    context: str = ""


if TYPE_CHECKING:

    class Ctx[InputT](Protocol):
        """Type-checking view of a step context (mypy cannot read pydantic_graph's inferred-variance TypeVars)."""

        @property
        def state(self) -> "WorkflowState":
            """Return the shared graph state."""
            ...

        @property
        def deps(self) -> "WorkflowDeps":
            """Return the run's dependencies."""
            ...

        @property
        def inputs(self) -> InputT:
            """Return this step's input."""
            ...

else:

    class Ctx:
        """Alias ``Ctx[InputT]`` to ``StepContext[WorkflowState, WorkflowDeps, InputT]`` at runtime."""

        def __class_getitem__(cls, item: object) -> object:
            """Return the real parametrised step context type."""
            return StepContext[WorkflowState, WorkflowDeps, item]


STEP_GUIDANCE = (
    "You are one step of a writers' room workflow. Work from the material above; use DraftPilot tools only "
    "to check something it does not contain, and read as little as you need. Submit your result with the output tool."
)


SELF_CONTAINED = (
    "You are one step of a writers' room workflow. Everything you need is above. "
    "Submit your result with the output tool."
)


async def consult[OutputT](
    ctx: Ctx[Any], step: str, role: str, prompt: str, output_type: type[OutputT], *, tools: bool = True
) -> OutputT:
    """Ask one room role for a typed output, record it on the trail, and report progress."""
    deps = ctx.deps
    started = monotonic()
    output: OutputT
    output, record = await run_role(
        role_spec(role),
        deps.model,
        deps.room,
        f"{prompt}\n\n{STEP_GUIDANCE if tools else SELF_CONTAINED}",
        output_type,
        provider=deps.provider,
        model_name=deps.model_name,
        kind="workflow",
        workflow_run_id=deps.run_id,
        tools=tools,
    )
    ctx.state.trail.append(
        {
            "step": step,
            "role": role,
            "agent_run_id": record.id,
            "duration_ms": round((monotonic() - started) * 1000),
            "output": output.model_dump(mode="json") if isinstance(output, BaseModel) else output,
        }
    )
    if deps.progress is not None:
        await deps.progress(ctx.state.trail)
    return output


def _critique_text(critique: Critique) -> str:
    """Render a critique for the next revision prompt."""
    return (
        f"Score {critique.score}/10.\nProblems:\n- " + "\n- ".join(critique.problems or ["(none)"])
        + "\nFixes, most important first:\n- " + "\n- ".join(critique.fixes or ["(none)"])
    )


def _outline_text(outline: Outline) -> str:
    """Render an outline as numbered beats."""
    beats = "\n".join(f"{index}. [Act {beat.act}] {beat.title}: {beat.summary}" for index, beat in enumerate(outline.beats, 1))
    return f"Logline: {outline.logline}\n{beats}"


# ---------------------------------------------------------------------------------------------------------------------
# Human gates: proposals the writer reviews
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
    session: AsyncSession, deps: WorkflowDeps, artifact: StoryArtifact, operation: dict[str, Any], summary: str
) -> int:
    """Create a reviewable artifact proposal and return its id."""
    proposal = await proposals_crud.create(
        session,
        AgentProposal(
            project_id=deps.room.project_id,
            run_id=deps.run_id,
            target_kind="artifact",
            target_id=artifact.id or 0,
            operation=operation,
            diff={"summary": summary},
            before={key: getattr(artifact, key) for key in operation},
            base_version=artifact.version,
        ),
    )
    return proposal.id or 0


def _markdown_outline(outline: Outline) -> str:
    """Render an outline as the markdown an outline artifact holds."""
    lines = [f"**Logline:** {outline.logline}", ""]
    for act in sorted({beat.act for beat in outline.beats}):
        lines.append(f"## Act {act}")
        lines.extend(f"- **{beat.title}** — {beat.summary}" for beat in outline.beats if beat.act == act)
        lines.append("")
    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------------------------------------------------
# notes → outline: draft, critique, revise until good enough, then propose
# ---------------------------------------------------------------------------------------------------------------------


def _outline_graph() -> Any:
    """Build the evaluator-optimizer graph that turns notes into a critiqued outline."""
    g = GraphBuilder(
        name="notes_to_outline", state_type=WorkflowState, deps_type=WorkflowDeps, input_type=OutlineParams, output_type=dict
    )

    @g.step
    async def draft(ctx: Ctx[OutlineParams]) -> OutlineParams:
        """Have the story editor turn the notes into a first outline."""
        ctx.state.draft = await consult(
            ctx,
            "draft",
            "story_editor",
            "Turn the writer's notes into a logline and a causal beat outline for a feature (three acts, "
            f"roughly 12-24 beats). Keep the writer's intentions; invent only connective tissue.\n\nNotes:\n{ctx.inputs.notes}",
            Outline,
            tools=False,
        )
        return ctx.inputs

    @g.step
    async def critique(ctx: Ctx[OutlineParams]) -> OutlineParams:
        """Have the script doctor grade the current outline."""
        ctx.state.critique = await consult(
            ctx,
            f"critique_{ctx.state.rounds + 1}",
            "script_doctor",
            "Grade this outline against the writer's notes: causality, escalation, a clear midpoint and climax, "
            f"and whether it honours the notes.\n\nNotes:\n{ctx.inputs.notes}\n\nOutline:\n{_outline_text(ctx.state.draft)}",
            Critique,
            tools=False,
        )
        return ctx.inputs

    @g.step
    async def revise(ctx: Ctx[OutlineParams]) -> OutlineParams:
        """Have the story editor revise the outline against the critique."""
        ctx.state.rounds += 1
        assert ctx.state.critique is not None
        ctx.state.draft = await consult(
            ctx,
            f"revise_{ctx.state.rounds}",
            "story_editor",
            f"Revise this outline to address the critique. Keep what works.\n\nNotes:\n{ctx.inputs.notes}\n\n"
            f"Outline:\n{_outline_text(ctx.state.draft)}\n\nCritique:\n{_critique_text(ctx.state.critique)}",
            Outline,
            tools=False,
        )
        return ctx.inputs

    @g.step
    async def gate(ctx: Ctx[OutlineParams]) -> dict:
        """Propose the logline into the brief and the beats into the outline for the writer to review."""
        outline: Outline = ctx.state.draft
        project_id = ctx.deps.room.project_id
        async with session_scope() as session:
            brief = await _artifact(session, project_id, "brief", "Brief")
            outline_artifact = await _artifact(session, project_id, "outline", "Outline")
            proposals = [
                await _propose_artifact(session, ctx.deps, brief, {"content": outline.logline}, "Logline from your notes"),
                await _propose_artifact(
                    session,
                    ctx.deps,
                    outline_artifact,
                    {
                        "content": _markdown_outline(outline),
                        "artifact_metadata": {
                            **outline_artifact.artifact_metadata,
                            "beats": [
                                {**beat.model_dump(), "sequence": index} for index, beat in enumerate(outline.beats, 1)
                            ],
                        },
                    },
                    f"{len(outline.beats)}-beat outline",
                ),
            ]
        return {
            "outline": outline.model_dump(),
            "critique": ctx.state.critique.model_dump() if ctx.state.critique else None,
            "rounds": ctx.state.rounds,
            "proposal_ids": proposals,
        }

    def good_enough(ctx_inputs: OutlineParams, state: WorkflowState) -> bool:
        """Return whether the loop should stop: the target is met or the rounds are used up."""
        assert state.critique is not None
        return state.critique.score >= ctx_inputs.target_score or state.rounds >= ctx_inputs.max_rounds

    decide = _loop_decision(g, good_enough, gate, revise)
    g.add(
        g.edge_from(g.start_node).to(draft),
        g.edge_from(draft).to(critique),
        g.edge_from(critique).to(decide),
        g.edge_from(revise).to(critique),
        g.edge_from(gate).to(g.end_node),
    )
    return g.build()


@dataclass
class _Checked[InputT]:
    """Carry step inputs plus whether the evaluator-optimizer loop is done."""

    inputs: InputT
    done: bool


def _loop_decision(g: Any, done: Callable[[Any, WorkflowState], bool], finish: Any, again: Any) -> Any:
    """Build the decision that ends a draft-critique loop or sends it round again."""

    @g.step
    async def check(ctx: Ctx[Any]) -> _Checked[Any]:
        """Decide from the latest critique whether another round is needed."""
        return _Checked(ctx.inputs, done(ctx.inputs, ctx.state))

    @g.step
    async def unwrap_finish(ctx: Ctx[_Checked[Any]]) -> Any:
        """Pass the original inputs on to the gate."""
        return ctx.inputs.inputs

    @g.step
    async def unwrap_again(ctx: Ctx[_Checked[Any]]) -> Any:
        """Pass the original inputs on to another revision."""
        return ctx.inputs.inputs

    g.add(
        g.edge_from(check).to(
            g.decision()
            .branch(g.match(_Checked, matches=lambda item: item.done).label("good enough").to(unwrap_finish))
            .branch(g.match(_Checked).label("revise").to(unwrap_again))
        ),
        g.edge_from(unwrap_finish).to(finish),
        g.edge_from(unwrap_again).to(again),
    )
    return check


# ---------------------------------------------------------------------------------------------------------------------
# brainstorm: parallel lenses, then a shortlist
# ---------------------------------------------------------------------------------------------------------------------


def _brainstorm_graph() -> Any:
    """Build the fan-out graph: one brainstormer per lens in parallel, then a ranked shortlist."""
    g = GraphBuilder(
        name="brainstorm", state_type=WorkflowState, deps_type=WorkflowDeps, input_type=BrainstormParams, output_type=dict
    )

    @g.step
    async def lenses(ctx: Ctx[BrainstormParams]) -> list[str]:
        """Fan the topic out, one branch per lens."""
        ctx.state.context = ctx.inputs.topic
        return ctx.inputs.lenses

    @g.step
    async def ideate(ctx: Ctx[str]) -> dict[str, Any]:
        """Have a brainstormer pitch ideas through one lens."""
        ideas = await consult(
            ctx,
            f"ideas: {ctx.inputs}",
            "brainstormer",
            f"Brainstorm through the lens '{ctx.inputs}'. Pitch 3 distinct ideas that fit this project.\n\n"
            f"Question:\n{ctx.state.context}",
            IdeaSet,
        )
        return {"lens": ctx.inputs, "ideas": [idea.model_dump() for idea in ideas.ideas]}

    collect = g.join(reduce_list_append, initial_factory=list[dict[str, Any]])

    @g.step
    async def shortlist(ctx: Ctx[list[dict[str, Any]]]) -> dict:
        """Have the story architect rank the room's ideas."""
        pitches = "\n".join(
            f"- ({group['lens']}) {idea['title']}: {idea['pitch']}" for group in ctx.inputs for idea in group["ideas"]
        )
        picks = await consult(
            ctx,
            "shortlist",
            "story_architect",
            f"The room pitched these ideas for: {ctx.state.context}\n\n{pitches}\n\n"
            "Shortlist the best 3 for this project and writer, say why, and synthesise a recommendation.",
            Shortlist,
            tools=False,
        )
        return {"lenses": ctx.inputs, "shortlist": picks.model_dump()}

    g.add(
        g.edge_from(g.start_node).to(lenses),
        g.edge_from(lenses).map().to(ideate),
        g.edge_from(ideate).to(collect),
        g.edge_from(collect).to(shortlist),
        g.edge_from(shortlist).to(g.end_node),
    )
    return g.build()


# ---------------------------------------------------------------------------------------------------------------------
# character arcs: one specialist per character in parallel, then propose
# ---------------------------------------------------------------------------------------------------------------------


async def lead_characters(session: AsyncSession, project_id: int, top: int) -> list[str]:
    """Return the Story twin's leads: characters with the most dialogue."""
    nodes = [node for node in await graph_crud.list_nodes(session, project_id) if node.kind == "character"]
    nodes.sort(key=lambda node: int(node.node_metadata.get("dialogue_lines") or 0), reverse=True)
    return [node.label for node in nodes[:top]]


def _arcs_graph() -> Any:
    """Build the fan-out graph that develops each character's arc and proposes them together."""
    g = GraphBuilder(name="character_arcs", state_type=WorkflowState, deps_type=WorkflowDeps, input_type=ArcParams, output_type=dict)

    @g.step
    async def cast(ctx: Ctx[ArcParams]) -> list[str]:
        """Fan out over the named characters, or the Story twin's leads."""
        if ctx.inputs.characters:
            return ctx.inputs.characters
        async with session_scope() as session:
            leads = await lead_characters(session, ctx.deps.room.project_id, ctx.inputs.top)
        if not leads:
            raise ValueError("No characters named and the Story twin has none yet")
        return leads

    @g.step
    async def arc(ctx: Ctx[str]) -> dict[str, Any]:
        """Have the character specialist develop one character's arc from the script."""
        result = await consult(
            ctx,
            f"arc: {ctx.inputs}",
            "character_specialist",
            f"Develop {ctx.inputs}'s arc in this project: want, need, flaw, the turning points in order "
            "(cite scenes), and a short arc summary. Ground it in what the script actually shows.",
            CharacterArc,
        )
        return result.model_dump()

    collect = g.join(reduce_list_append, initial_factory=list[dict[str, Any]])

    @g.step
    async def gate(ctx: Ctx[list[dict[str, Any]]]) -> dict:
        """Propose every arc into the characters artifact for the writer to review."""
        async with session_scope() as session:
            artifact = await _artifact(session, ctx.deps.room.project_id, "character", "Characters")
            arcs = [
                {"character": item["character"], "want": item["want"], "need": item["need"], "turning_points": item["turning_points"]}
                for item in ctx.inputs
            ]
            proposal = await _propose_artifact(
                session,
                ctx.deps,
                artifact,
                {
                    "content": "\n\n".join(f"**{item['character']}** — {item['arc_summary']}" for item in ctx.inputs),
                    "artifact_metadata": {**artifact.artifact_metadata, "character_arcs": arcs},
                },
                f"Arcs for {', '.join(item['character'] for item in ctx.inputs)}",
            )
        return {"arcs": ctx.inputs, "proposal_ids": [proposal]}

    g.add(
        g.edge_from(g.start_node).to(cast),
        g.edge_from(cast).map().to(arc),
        g.edge_from(arc).to(collect),
        g.edge_from(collect).to(gate),
        g.edge_from(gate).to(g.end_node),
    )
    return g.build()


# ---------------------------------------------------------------------------------------------------------------------
# rewrite a scene: draft, critique, revise, then propose the rewrite
# ---------------------------------------------------------------------------------------------------------------------


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


def _rewrite_graph() -> Any:
    """Build the evaluator-optimizer graph that rewrites a scene to a brief."""
    g = GraphBuilder(name="rewrite_scene", state_type=WorkflowState, deps_type=WorkflowDeps, input_type=RewriteParams, output_type=dict)

    @g.step
    async def load(ctx: Ctx[RewriteParams]) -> RewriteParams:
        """Load the scene as Fountain."""
        async with session_scope() as session:
            scene = await _project_scene(session, ctx.deps.room.project_id, ctx.inputs.scene_id)
            ctx.state.context = await scene_fountain(session, scene)
        return ctx.inputs

    @g.step
    async def draft(ctx: Ctx[RewriteParams]) -> RewriteParams:
        """Have the scene writer rewrite the scene to the brief."""
        ctx.state.draft = await consult(
            ctx,
            "draft",
            "scene_writer",
            f"Rewrite this scene to the brief, in the writer's voice. Return the whole scene in Fountain, "
            f"heading first.\n\nBrief: {ctx.inputs.brief}\n\nCurrent scene:\n{ctx.state.context}",
            SceneDraft,
            tools=False,
        )
        return ctx.inputs

    @g.step
    async def critique(ctx: Ctx[RewriteParams]) -> RewriteParams:
        """Have the script doctor grade the rewrite against the brief."""
        ctx.state.critique = await consult(
            ctx,
            f"critique_{ctx.state.rounds + 1}",
            "script_doctor",
            f"Grade this rewrite against the brief and the original. Does it deliver the brief without losing what "
            f"worked?\n\nBrief: {ctx.inputs.brief}\n\nOriginal:\n{ctx.state.context}\n\nRewrite:\n{ctx.state.draft.fountain}",
            Critique,
            tools=False,
        )
        return ctx.inputs

    @g.step
    async def revise(ctx: Ctx[RewriteParams]) -> RewriteParams:
        """Have the scene writer revise against the critique."""
        ctx.state.rounds += 1
        assert ctx.state.critique is not None
        ctx.state.draft = await consult(
            ctx,
            f"revise_{ctx.state.rounds}",
            "scene_writer",
            f"Revise your rewrite to address the critique. Return the whole scene in Fountain.\n\nBrief: {ctx.inputs.brief}\n\n"
            f"Your rewrite:\n{ctx.state.draft.fountain}\n\nCritique:\n{_critique_text(ctx.state.critique)}",
            SceneDraft,
            tools=False,
        )
        return ctx.inputs

    @g.step
    async def gate(ctx: Ctx[RewriteParams]) -> dict:
        """Propose the rewrite as one reversible scene change."""
        draft: SceneDraft = ctx.state.draft
        async with session_scope() as session:
            scene = await _project_scene(session, ctx.deps.room.project_id, ctx.inputs.scene_id)
            proposal = await proposals_crud.create(
                session,
                AgentProposal(
                    project_id=ctx.deps.room.project_id,
                    run_id=ctx.deps.run_id,
                    target_kind="scene",
                    target_id=scene.id or 0,
                    operation=rewrite_operation(parse_scene_fountain(draft.fountain)),
                    diff={"summary": f"Rewrite: {ctx.inputs.brief[:200]}", "rationale": draft.rationale},
                    before=await rewrite_snapshot(session, scene),
                    base_version=scene.version,
                ),
            )
        return {
            "fountain": draft.fountain,
            "rationale": draft.rationale,
            "critique": ctx.state.critique.model_dump() if ctx.state.critique else None,
            "rounds": ctx.state.rounds,
            "proposal_ids": [proposal.id],
        }

    def good_enough(inputs: RewriteParams, state: WorkflowState) -> bool:
        """Return whether the rewrite loop should stop."""
        assert state.critique is not None
        return state.critique.score >= inputs.target_score or state.rounds >= inputs.max_rounds

    decide = _loop_decision(g, good_enough, gate, revise)
    g.add(
        g.edge_from(g.start_node).to(load),
        g.edge_from(load).to(draft),
        g.edge_from(draft).to(critique),
        g.edge_from(critique).to(decide),
        g.edge_from(revise).to(critique),
        g.edge_from(gate).to(g.end_node),
    )
    return g.build()


# ---------------------------------------------------------------------------------------------------------------------
# outline → script: draft new scenes from beats in parallel, propose them appended
# ---------------------------------------------------------------------------------------------------------------------


def _draft_scenes_graph() -> Any:
    """Build the fan-out graph that dramatises beats as new scenes and proposes appending them."""
    g = GraphBuilder(
        name="draft_scenes", state_type=WorkflowState, deps_type=WorkflowDeps, input_type=DraftScenesParams, output_type=dict
    )

    @g.step
    async def beats(ctx: Ctx[DraftScenesParams]) -> list[dict[str, Any]]:
        """Fan out over the given beats, or the outline artifact's beats."""
        chosen = [beat.model_dump() for beat in ctx.inputs.beats]
        if not chosen:
            async with session_scope() as session:
                artifacts = await artifacts_crud.list_for_project(session, ctx.deps.room.project_id)
            outline = next(
                (item for item in artifacts if item.id == ctx.inputs.outline_artifact_id or (ctx.inputs.outline_artifact_id is None and item.kind == "outline")),
                None,
            )
            chosen = list((outline.artifact_metadata.get("beats") if outline else None) or [])
        if not chosen:
            raise ValueError("No beats given and the outline has none yet")
        return [{"index": index, **beat} for index, beat in enumerate(chosen[: ctx.inputs.limit])]

    @g.step
    async def write(ctx: Ctx[dict[str, Any]]) -> dict[str, Any]:
        """Have the scene writer dramatise one beat."""
        draft = await consult(
            ctx,
            f"scene: {ctx.inputs['title']}",
            "scene_writer",
            f"Write this beat as one new screenplay scene in Fountain, heading first, in the writer's voice and "
            f"consistent with the project.\n\nBeat: {ctx.inputs['title']} — {ctx.inputs['summary']}",
            SceneDraft,
        )
        return {"index": ctx.inputs["index"], "title": ctx.inputs["title"], **draft.model_dump()}

    collect = g.join(reduce_list_append, initial_factory=list[dict[str, Any]])

    @g.step
    async def gate(ctx: Ctx[list[dict[str, Any]]]) -> dict:
        """Propose every drafted scene, in beat order, appended to the working draft."""
        drafts = sorted(ctx.inputs, key=lambda item: item["index"])
        async with session_scope() as session:
            screenplay = await working_screenplay(session, ctx.deps.room.project_id)
            if screenplay is None:
                raise ValueError("The project has no screenplay to draft into")
            proposal = await proposals_crud.create(
                session,
                AgentProposal(
                    project_id=ctx.deps.room.project_id,
                    run_id=ctx.deps.run_id,
                    target_kind="screenplay",
                    target_id=screenplay.id or 0,
                    operation=append_operation([parse_scene_fountain(item["fountain"]) for item in drafts]),
                    diff={"summary": f"{len(drafts)} new scenes: " + "; ".join(item["title"] for item in drafts)},
                    before={},
                    base_version=1,
                ),
            )
        return {"scenes": drafts, "proposal_ids": [proposal.id]}

    g.add(
        g.edge_from(g.start_node).to(beats),
        g.edge_from(beats).map().to(write),
        g.edge_from(write).to(collect),
        g.edge_from(collect).to(gate),
        g.edge_from(gate).to(g.end_node),
    )
    return g.build()


# ---------------------------------------------------------------------------------------------------------------------
# audience panel: parallel personas, then a scored summary
# ---------------------------------------------------------------------------------------------------------------------


def _scope_text(scene_ids: list[int], focus: str) -> str:
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


def _panel_graph() -> Any:
    """Build the fan-out graph that runs one audience evaluator per persona in parallel."""
    g = GraphBuilder(name="audience_panel", state_type=WorkflowState, deps_type=WorkflowDeps, input_type=PanelParams, output_type=dict)

    @g.step
    async def personas(ctx: Ctx[PanelParams]) -> list[str]:
        """Fan out, one branch per persona."""
        ctx.state.context = _scope_text(ctx.inputs.scene_ids, ctx.inputs.focus)
        return ctx.inputs.personas

    @g.step
    async def react(ctx: Ctx[str]) -> dict[str, Any]:
        """Have an audience evaluator react as one persona."""
        reaction = await consult(
            ctx,
            f"persona: {ctx.inputs}",
            "audience_evaluator",
            f"React to this script as this viewer: {ctx.inputs}. Be honest and specific; cite scenes. "
            f"{ctx.state.context}",
            Reaction,
        )
        return {**reaction.model_dump(), "persona": ctx.inputs}

    collect = g.join(reduce_list_append, initial_factory=list[dict[str, Any]])

    @g.step
    async def summarize(ctx: Ctx[list[dict[str, Any]]]) -> dict:
        """Score the panel."""
        return {"reactions": ctx.inputs, "summary": summarize_panel(ctx.inputs)}

    g.add(
        g.edge_from(g.start_node).to(personas),
        g.edge_from(personas).map().to(react),
        g.edge_from(react).to(collect),
        g.edge_from(collect).to(summarize),
        g.edge_from(summarize).to(g.end_node),
    )
    return g.build()


# ---------------------------------------------------------------------------------------------------------------------
# coverage and continuity: single-role reports
# ---------------------------------------------------------------------------------------------------------------------


def _coverage_graph() -> Any:
    """Build the one-step coverage graph."""
    g = GraphBuilder(name="coverage", state_type=WorkflowState, deps_type=WorkflowDeps, input_type=CoverageParams, output_type=dict)

    @g.step
    async def cover(ctx: Ctx[CoverageParams]) -> dict:
        """Have the coverage reader write coverage."""
        report = await consult(
            ctx,
            "coverage",
            "coverage_reader",
            "Write studio coverage of the working draft: logline, synopsis, 1-10 grades for premise, structure, "
            "character, dialogue and pacing, strengths, weaknesses and a verdict." + (f" Focus: {ctx.inputs.focus}" if ctx.inputs.focus else ""),
            Coverage,
        )
        return {"coverage": report.model_dump()}

    g.add(g.edge_from(g.start_node).to(cover), g.edge_from(cover).to(g.end_node))
    return g.build()


def _continuity_graph() -> Any:
    """Build the continuity graph: one pass, then drop issues citing scenes outside the draft."""
    g = GraphBuilder(name="continuity", state_type=WorkflowState, deps_type=WorkflowDeps, input_type=ContinuityParams, output_type=dict)

    @g.step
    async def check(ctx: Ctx[ContinuityParams]) -> dict:
        """Have the continuity supervisor find problems, then keep only issues about real scenes."""
        report = await consult(
            ctx,
            "continuity",
            "continuity_supervisor",
            "Find continuity problems (timeline, character, props, locations, established facts). Cite scene ids. "
            + _scope_text(ctx.inputs.scene_ids, ctx.inputs.focus),
            ContinuityReport,
        )
        async with session_scope() as session:
            screenplay = await working_screenplay(session, ctx.deps.room.project_id)
            known = {scene.id for scene in await scenes_crud.list_for_screenplay(session, screenplay.id or 0)} if screenplay else set()
        issues = [issue.model_dump() for issue in report.issues if all(scene_id in known for scene_id in issue.scene_ids)]
        return {"issues": issues, "dropped": len(report.issues) - len(issues)}

    g.add(g.edge_from(g.start_node).to(check), g.edge_from(check).to(g.end_node))
    return g.build()


# ---------------------------------------------------------------------------------------------------------------------
# Catalogue and entry point
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
    build: Callable[[], Any]


ROOM_WORKFLOWS: dict[str, RoomWorkflow] = {
    workflow.key: workflow
    for workflow in (
        RoomWorkflow("notes_to_outline", "Notes → outline", "Turn your notes into a logline and beat outline, critiqued and revised.", OutlineParams, ("story_editor", "script_doctor"), True, _outline_graph),
        RoomWorkflow("draft_scenes", "Outline → scenes", "Draft new scenes from outline beats, in parallel.", DraftScenesParams, ("scene_writer",), True, _draft_scenes_graph),
        RoomWorkflow("rewrite_scene", "Rewrite a scene", "Rewrite one scene to your brief through a draft-critique loop.", RewriteParams, ("scene_writer", "script_doctor"), True, _rewrite_graph),
        RoomWorkflow("character_arcs", "Character arcs", "Develop want, need, flaw and turning points for your leads.", ArcParams, ("character_specialist",), True, _arcs_graph),
        RoomWorkflow("brainstorm", "Brainstorm", "Pitch ideas through several lenses in parallel, then shortlist.", BrainstormParams, ("brainstormer", "story_architect"), False, _brainstorm_graph),
        RoomWorkflow("audience_panel", "Audience panel", "Test the script on a panel of viewer personas.", PanelParams, ("audience_evaluator",), False, _panel_graph),
        RoomWorkflow("coverage", "Coverage", "Studio-style coverage with graded craft and a verdict.", CoverageParams, ("coverage_reader",), False, _coverage_graph),
        RoomWorkflow("continuity", "Continuity pass", "Find timeline, character, prop and fact inconsistencies.", ContinuityParams, ("continuity_supervisor",), False, _continuity_graph),
    )
}


def validate_params(key: str, params: dict[str, Any]) -> BaseModel:
    """Validate a workflow's parameters, raising ``KeyError`` for an unknown workflow."""
    return ROOM_WORKFLOWS[key].params.model_validate(params)


async def run_room_workflow(key: str, params: dict[str, Any], deps: WorkflowDeps) -> dict[str, Any]:
    """Run one room workflow to its gate and return its result plus the consultation trail."""
    workflow = ROOM_WORKFLOWS[key]
    state = WorkflowState()
    result = await workflow.build().run(state=state, deps=deps, inputs=validate_params(key, params))
    return {"workflow": key, "proposes": workflow.proposes, **result, "trail": state.trail}
