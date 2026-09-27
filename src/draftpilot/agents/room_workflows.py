"""The writers' room workflows as Temporal workflows.

This module is deterministic workflow code, and Temporal's sandbox re-imports it for every run.
Each step consults one role through its durable agent, so every model request and tool call is an
activity and a worker crash resumes mid-workflow. Every database read and write goes through an
activity (``agents.workflows``). Loops are plain Python, and fan-outs use ``asyncio.gather``. The
trail is exposed as the ``progress`` query and mirrored into the run's Postgres copy. Any edit here
must pass the replay tests over ``tests/temporal_histories/``.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any, ClassVar

from temporalio import workflow
from temporalio.exceptions import ActivityError, ApplicationError, FailureError

with workflow.unsafe.imports_passed_through():
    from pydantic import BaseModel
    from pydantic_ai.exceptions import AgentRunError

    from draftpilot.agents.deps import RoomDeps
    from draftpilot.agents.runtime import (
        RunMeter,
        model_identity,
        reasoning_ran_away,
        role_run_options,
        room_agents,
    )
    from draftpilot.agents.specs import role_spec
    from draftpilot.agents.workflows import (
        REWRITE_RULES,
        ROOM_WORKFLOWS,
        SELF_CONTAINED,
        STEP_ACTIVITY,
        STEP_GUIDANCE,
        ArcParams,
        BrainstormParams,
        CharacterArc,
        ContinuityParams,
        ContinuityReport,
        Coverage,
        CoverageParams,
        Critique,
        DraftScenesParams,
        IdeaSet,
        Outline,
        OutlineParams,
        PanelParams,
        ProgressUpdate,
        Reaction,
        RewriteParams,
        RoomRunInput,
        SceneDraft,
        Shortlist,
        critique_text,
        find_leads,
        known_scene_ids,
        load_scene,
        outline_beats,
        outline_text,
        propose_arcs,
        propose_outline,
        propose_rewrite,
        propose_scenes,
        record_agent_run,
        record_progress,
        rewrite_facts,
        scope_text,
        summarize_panel,
    )


class RoomWorkflowBase:
    """What every room workflow shares: the trail, the progress query, and ``consult``.

    The agents' activities are registered once for all eight workflows (``room_agent_activities``)
    rather than through ``__pydantic_ai_agents__``, which every subclass would inherit and register again.
    """

    key: ClassVar[str]

    def __init__(self) -> None:
        """Start with an empty trail."""
        self.trail: list[dict[str, Any]] = []
        self.room = RoomDeps(project_id=0)

    @workflow.query
    def progress(self) -> list[dict[str, Any]]:
        """Return the consultations so far (the live trail)."""
        return self.trail

    async def execute[ParamsT: BaseModel](
        self, run: RoomRunInput, params_type: type[ParamsT], body: Callable[[ParamsT], Awaitable[dict[str, Any]]]
    ) -> dict[str, Any]:
        """Run the workflow's body and wrap its result; a plain error fails the workflow instead of retrying its task."""
        self.room = run.room
        try:
            result = await body(params_type.model_validate(run.params))
        except (FailureError, AgentRunError):
            raise
        except Exception as exc:
            raise ApplicationError(str(exc), type=type(exc).__name__, non_retryable=True) from exc
        return {"workflow": self.key, "proposes": ROOM_WORKFLOWS[self.key].proposes, **result, "trail": self.trail}

    async def activity(self, fn: Callable[..., Awaitable[Any]], *args: Any) -> Any:
        """Run one database step as an activity."""
        return await workflow.execute_activity(fn, args=list(args), **STEP_ACTIVITY)

    async def consult[OutputT](self, step: str, role: str, prompt: str, output_type: type[OutputT], *, tools: bool = True) -> OutputT:
        """Ask one role for a typed output, record its AgentRun and the trail, and stop if the writer cancelled.

        A role that reasons past its budget answers once more without reasoning.
        """
        spec = role_spec(role)
        deps = replace(self.room, tools=self.room.tools and tools)
        provider, model_name = model_identity(deps.model_ref)
        started = workflow.time()
        thinking: bool | None = None
        prompt = f"{prompt}\n\n{STEP_GUIDANCE if tools else SELF_CONTAINED}"
        while True:
            meter = RunMeter(deps.project_id, role, "workflow", provider, model_name, deps.workflow_run_id, started=0.0)
            attempt_started = workflow.time()
            try:
                result = await room_agents()[role].run(prompt, **role_run_options(spec, deps, output_type, thinking))
            except (ActivityError, AgentRunError) as exc:
                await self.activity(record_agent_run, meter.fields(None, exc, _ms_since(attempt_started)))
                if thinking is None and reasoning_ran_away(exc):
                    # The model reasoned past its budget (tokens, or the server's no-data timeout): answer without reasoning.
                    thinking = False
                    continue
                raise
            break
        agent_run_id = await self.activity(record_agent_run, meter.fields(result, None, _ms_since(attempt_started)))
        output: OutputT = result.output
        self.trail.append(
            {
                "step": step,
                "role": role,
                "agent_run_id": agent_run_id,
                "duration_ms": _ms_since(started),
                "output": output.model_dump(mode="json") if isinstance(output, BaseModel) else output,
            }
        )
        update = ProgressUpdate(deps.workflow_run_id, deps.project_id, self.key, self.trail)
        if await self.activity(record_progress, update):
            raise ApplicationError("The writer cancelled the workflow", type="WorkflowCancelled", non_retryable=True)
        return output


def _ms_since(started: float) -> int:
    """Return workflow-clock milliseconds since ``started``."""
    return round((workflow.time() - started) * 1000)


@workflow.defn(name="room:notes_to_outline")
class NotesToOutline(RoomWorkflowBase):
    """Draft an outline from notes, critique and revise it until it is good enough, then propose it."""

    key = "notes_to_outline"

    @workflow.run
    async def run(self, run: RoomRunInput) -> dict[str, Any]:
        """Run the evaluator-optimizer loop to its gate."""
        return await self.execute(run, OutlineParams, self.body)

    async def body(self, params: OutlineParams) -> dict[str, Any]:
        """Draft, critique, revise, propose."""
        draft = await self.consult(
            "draft",
            "story_editor",
            "Turn the writer's notes into a logline and a causal beat outline for a feature (three acts, "
            f"roughly 12-24 beats). Keep the writer's intentions; invent only connective tissue.\n\nNotes:\n{params.notes}",
            Outline,
            tools=False,
        )
        rounds = 0
        critique = await self._critique(params, draft, rounds)
        while critique.score < params.target_score and rounds < params.max_rounds:
            rounds += 1
            draft = await self.consult(
                f"revise_{rounds}",
                "story_editor",
                f"Revise this outline to address the critique. Keep what works.\n\nNotes:\n{params.notes}\n\n"
                f"Outline:\n{outline_text(draft)}\n\nCritique:\n{critique_text(critique)}",
                Outline,
                tools=False,
            )
            critique = await self._critique(params, draft, rounds)
        proposal_ids = await self.activity(propose_outline, self.room.project_id, self.room.workflow_run_id, draft)
        return {"outline": draft.model_dump(), "critique": critique.model_dump(), "rounds": rounds, "proposal_ids": proposal_ids}

    async def _critique(self, params: OutlineParams, draft: Outline, rounds: int) -> Critique:
        """Have the script doctor grade the current outline."""
        return await self.consult(
            f"critique_{rounds + 1}",
            "script_doctor",
            "Grade this outline against the writer's notes: causality, escalation, a clear midpoint and climax, "
            f"and whether it honours the notes.\n\nNotes:\n{params.notes}\n\nOutline:\n{outline_text(draft)}",
            Critique,
            tools=False,
        )


@workflow.defn(name="room:brainstorm")
class Brainstorm(RoomWorkflowBase):
    """Pitch ideas through every lens in parallel, then shortlist the best."""

    key = "brainstorm"

    @workflow.run
    async def run(self, run: RoomRunInput) -> dict[str, Any]:
        """Fan out over the lenses, then shortlist."""
        return await self.execute(run, BrainstormParams, self.body)

    async def body(self, params: BrainstormParams) -> dict[str, Any]:
        """One brainstormer per lens, then the story architect's shortlist."""
        groups = await asyncio.gather(*(self._ideate(params.topic, lens) for lens in params.lenses))
        pitches = "\n".join(f"- ({group['lens']}) {idea['title']}: {idea['pitch']}" for group in groups for idea in group["ideas"])
        picks = await self.consult(
            "shortlist",
            "story_architect",
            f"The room pitched these ideas for: {params.topic}\n\n{pitches}\n\n"
            "Shortlist the best 3 for this project and writer, say why, and synthesise a recommendation.",
            Shortlist,
            tools=False,
        )
        return {"lenses": list(groups), "shortlist": picks.model_dump()}

    async def _ideate(self, topic: str, lens: str) -> dict[str, Any]:
        """Have a brainstormer pitch ideas through one lens."""
        ideas = await self.consult(
            f"ideas: {lens}",
            "brainstormer",
            f"Brainstorm through the lens '{lens}'. Pitch 3 distinct ideas that fit this project.\n\nQuestion:\n{topic}",
            IdeaSet,
        )
        return {"lens": lens, "ideas": [idea.model_dump() for idea in ideas.ideas]}


@workflow.defn(name="room:character_arcs")
class CharacterArcs(RoomWorkflowBase):
    """Develop each character's arc in parallel and propose them together."""

    key = "character_arcs"

    @workflow.run
    async def run(self, run: RoomRunInput) -> dict[str, Any]:
        """Fan out over the cast, then propose."""
        return await self.execute(run, ArcParams, self.body)

    async def body(self, params: ArcParams) -> dict[str, Any]:
        """Named characters, or the Story twin's leads, one specialist each."""
        cast = params.characters or await self.activity(find_leads, self.room.project_id, params.top)
        arcs = list(await asyncio.gather(*(self._arc(name) for name in cast)))
        proposal_ids = await self.activity(propose_arcs, self.room.project_id, self.room.workflow_run_id, arcs)
        return {"arcs": arcs, "proposal_ids": proposal_ids}

    async def _arc(self, name: str) -> dict[str, Any]:
        """Have the character specialist develop one character's arc from the script."""
        arc = await self.consult(
            f"arc: {name}",
            "character_specialist",
            f"Develop {name}'s arc in this project: want, need, flaw, the turning points in order "
            "(cite scenes), and a short arc summary. Ground it in what the script actually shows.",
            CharacterArc,
        )
        return arc.model_dump()


@workflow.defn(name="room:rewrite_scene")
class RewriteScene(RoomWorkflowBase):
    """Rewrite one scene to a brief through a draft-critique loop, then propose the rewrite."""

    key = "rewrite_scene"

    @workflow.run
    async def run(self, run: RoomRunInput) -> dict[str, Any]:
        """Run the evaluator-optimizer loop to its gate."""
        return await self.execute(run, RewriteParams, self.body)

    async def body(self, params: RewriteParams) -> dict[str, Any]:
        """Load, draft, critique, revise, propose."""
        original = await self.activity(load_scene, self.room.project_id, params.scene_id)
        draft = await self.consult(
            "draft",
            "scene_writer",
            f"Rewrite this scene to the brief, in the writer's voice. Return the whole scene in Fountain, "
            f"heading first. {REWRITE_RULES}\n\nBrief: {params.brief}\n\nCurrent scene:\n{original}",
            SceneDraft,
            tools=False,
        )
        rounds = 0
        critique = await self._critique(params, original, draft, rounds)
        while critique.score < params.target_score and rounds < params.max_rounds:
            rounds += 1
            draft = await self.consult(
                f"revise_{rounds}",
                "scene_writer",
                f"Revise your rewrite to address the critique. Return the whole scene in Fountain. {REWRITE_RULES}\n\n"
                f"Measured: {rewrite_facts(original, draft.fountain)}\n\nBrief: {params.brief}\n\n"
                f"Your rewrite:\n{draft.fountain}\n\nCritique:\n{critique_text(critique)}",
                SceneDraft,
                tools=False,
            )
            critique = await self._critique(params, original, draft, rounds)
        proposal_ids = await self.activity(
            propose_rewrite, self.room.project_id, self.room.workflow_run_id, params.scene_id, params.brief, draft
        )
        return {
            "fountain": draft.fountain,
            "rationale": draft.rationale,
            "critique": critique.model_dump(),
            "rounds": rounds,
            "proposal_ids": proposal_ids,
        }

    async def _critique(self, params: RewriteParams, original: str, draft: SceneDraft, rounds: int) -> Critique:
        """Have the script doctor grade the rewrite against the brief."""
        return await self.consult(
            f"critique_{rounds + 1}",
            "script_doctor",
            f"Grade this rewrite against the brief and the original. Does it deliver the brief without losing what "
            f"worked? Score below 8 if it breaks the brief (for example, not shorter when asked) or adds speaking "
            f"characters the brief did not ask for.\n\nMeasured: {rewrite_facts(original, draft.fountain)}"
            f"\n\nBrief: {params.brief}\n\nOriginal:\n{original}\n\nRewrite:\n{draft.fountain}",
            Critique,
            tools=False,
        )


@workflow.defn(name="room:draft_scenes")
class DraftScenes(RoomWorkflowBase):
    """Dramatise beats as new scenes in parallel and propose appending them, in beat order."""

    key = "draft_scenes"

    @workflow.run
    async def run(self, run: RoomRunInput) -> dict[str, Any]:
        """Fan out over the beats, then propose."""
        return await self.execute(run, DraftScenesParams, self.body)

    async def body(self, params: DraftScenesParams) -> dict[str, Any]:
        """The given beats, or the outline artifact's, one scene writer each."""
        chosen = [beat.model_dump() for beat in params.beats] or await self.activity(
            outline_beats, self.room.project_id, params.outline_artifact_id
        )
        if not chosen:
            raise ValueError("No beats given and the outline has none yet")
        beats = [{"index": index, **beat} for index, beat in enumerate(chosen[: params.limit])]
        drafts = sorted(await asyncio.gather(*(self._write(beat) for beat in beats)), key=lambda item: item["index"])
        proposal_ids = await self.activity(propose_scenes, self.room.project_id, self.room.workflow_run_id, drafts)
        return {"scenes": drafts, "proposal_ids": proposal_ids}

    async def _write(self, beat: dict[str, Any]) -> dict[str, Any]:
        """Have the scene writer dramatise one beat."""
        draft = await self.consult(
            f"scene: {beat['title']}",
            "scene_writer",
            f"Write this beat as one new screenplay scene in Fountain, heading first, in the writer's voice and "
            f"consistent with the project.\n\nBeat: {beat['title']} — {beat['summary']}",
            SceneDraft,
        )
        return {"index": beat["index"], "title": beat["title"], **draft.model_dump()}


@workflow.defn(name="room:audience_panel")
class AudiencePanel(RoomWorkflowBase):
    """Run one audience evaluator per persona in parallel, then score the panel."""

    key = "audience_panel"

    @workflow.run
    async def run(self, run: RoomRunInput) -> dict[str, Any]:
        """Fan out over the personas, then summarise."""
        return await self.execute(run, PanelParams, self.body)

    async def body(self, params: PanelParams) -> dict[str, Any]:
        """Every persona reacts; the panel is scored."""
        scope = scope_text(params.scene_ids, params.focus)
        reactions = list(await asyncio.gather(*(self._react(persona, scope) for persona in params.personas)))
        return {"reactions": reactions, "summary": summarize_panel(reactions)}

    async def _react(self, persona: str, scope: str) -> dict[str, Any]:
        """Have an audience evaluator react as one persona."""
        reaction = await self.consult(
            f"persona: {persona}",
            "audience_evaluator",
            f"React to this script as this viewer: {persona}. Be honest and specific; cite scenes. {scope}",
            Reaction,
        )
        return {**reaction.model_dump(), "persona": persona}


@workflow.defn(name="room:coverage")
class CoverageReport(RoomWorkflowBase):
    """Write studio coverage of the working draft."""

    key = "coverage"

    @workflow.run
    async def run(self, run: RoomRunInput) -> dict[str, Any]:
        """Consult the coverage reader."""
        return await self.execute(run, CoverageParams, self.body)

    async def body(self, params: CoverageParams) -> dict[str, Any]:
        """One coverage report."""
        report = await self.consult(
            "coverage",
            "coverage_reader",
            "Write studio coverage of the working draft: logline, synopsis, 1-10 grades for premise, structure, "
            "character, dialogue and pacing, strengths, weaknesses and a verdict." + (f" Focus: {params.focus}" if params.focus else ""),
            Coverage,
        )
        return {"coverage": report.model_dump()}


@workflow.defn(name="room:continuity")
class ContinuityPass(RoomWorkflowBase):
    """Find continuity problems, then drop issues citing scenes outside the draft."""

    key = "continuity"

    @workflow.run
    async def run(self, run: RoomRunInput) -> dict[str, Any]:
        """Consult the continuity supervisor and check its citations."""
        return await self.execute(run, ContinuityParams, self.body)

    async def body(self, params: ContinuityParams) -> dict[str, Any]:
        """One pass; keep only issues about real scenes."""
        report = await self.consult(
            "continuity",
            "continuity_supervisor",
            "Find continuity problems (timeline, character, props, locations, established facts). Cite scene ids. "
            + scope_text(params.scene_ids, params.focus),
            ContinuityReport,
        )
        known = set(await self.activity(known_scene_ids, self.room.project_id))
        issues = [issue.model_dump() for issue in report.issues if all(scene_id in known for scene_id in issue.scene_ids)]
        return {"issues": issues, "dropped": len(report.issues) - len(issues)}


ROOM_WORKFLOW_CLASSES: list[type] = [
    NotesToOutline,
    DraftScenes,
    RewriteScene,
    CharacterArcs,
    Brainstorm,
    AudiencePanel,
    CoverageReport,
    ContinuityPass,
]
