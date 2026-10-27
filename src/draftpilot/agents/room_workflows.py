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
from datetime import timedelta
from typing import Any, ClassVar

from temporalio import workflow
from temporalio.exceptions import ActivityError, ApplicationError, FailureError

with workflow.unsafe.imports_passed_through():
    from pydantic import BaseModel
    from pydantic_ai.durable_exec.temporal import AgentEventStream
    from pydantic_ai.exceptions import AgentRunError
    from pydantic_ai.tools import DeferredToolRequests, ToolDefinition
    from pydantic_ai.toolsets import ExternalToolset

    from draftpilot.agents.chat import (
        ChatTurn,
        reply_text,
        save_chat_thread,
        save_chat_turn,
    )
    from draftpilot.agents.deps import RoomDeps
    from draftpilot.agents.runtime import (
        RunMeter,
        chat_agents,
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
        Cast,
        CharacterArc,
        CharacterTimeline,
        ContinuityParams,
        ContinuityReport,
        Coverage,
        CoverageParams,
        Critique,
        DevelopStoryParams,
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
        StorylineDraft,
        cast_ids,
        critique_text,
        find_leads,
        known_scene_ids,
        link_beat_scenes,
        load_scene,
        outline_beats,
        outline_text,
        proposal_states,
        propose_arcs,
        propose_beats,
        propose_cast,
        propose_outline,
        propose_rewrite,
        propose_scenes,
        propose_storyline,
        propose_timeline,
        record_agent_run,
        record_progress,
        rewrite_facts,
        scope_text,
        story_brief,
        summarize_panel,
    )

# Temporal needs durable agents built outside any workflow. The first (host) import of this module
# builds them, and the sandbox's re-imports get the cached ones.
room_agents()
chat_agents()


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


# A continuity pass over this many scenes or fewer gets their text in the prompt.
INLINE_SCENES = 12


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
        scope, tools = scope_text(params.scene_ids, params.focus), True
        if params.scene_ids and len(params.scene_ids) <= INLINE_SCENES and workflow.patched("continuity-inline-scenes"):
            # Hand over the scenes and check only them, without tools: told only their ids, the supervisor
            # wandered the script and re-read empty story records until it ran out of requests.
            texts = [await self.activity(load_scene, self.room.project_id, scene_id) for scene_id in params.scene_ids]
            scenes = "\n\n".join(f"[scene {scene_id}]\n{text}" for scene_id, text in zip(params.scene_ids, texts, strict=True))
            scope = (
                "Check only these scenes, against each other and the Story twin above."
                + (f" Focus: {params.focus}" if params.focus else "")
                + f"\n\n{scenes}"
            )
            tools = False
        report = await self.consult(
            "continuity",
            "continuity_supervisor",
            "Find continuity problems (timeline, character, props, locations, established facts). Cite scene ids. " + scope,
            ContinuityReport,
            tools=tools,
        )
        known = set(await self.activity(known_scene_ids, self.room.project_id))
        issues = [issue.model_dump() for issue in report.issues if all(scene_id in known for scene_id in issue.scene_ids)]
        return {"issues": issues, "dropped": len(report.issues) - len(issues)}


@workflow.defn(name="room:chat")
class RoomChat:
    """Run one chat turn, publishing its events to the workflow's stream for the studio to relay."""

    @workflow.init
    def __init__(self, turn: ChatTurn) -> None:
        """Host the event stream the chat agent publishes to."""
        self.events = AgentEventStream()

    @workflow.run
    async def run(self, turn: ChatTurn) -> str:
        """Answer the conversation (or ask the writer to approve a write), then record the run, transcript and thread."""
        provider, model_name = model_identity(turn.deps.model_ref)
        meter = RunMeter(turn.deps.project_id, turn.role, "chat", provider, model_name, None, started=0.0)
        started = workflow.time()
        agui = workflow.patched("agui-chat")
        options = role_run_options(role_spec(turn.role), turn.deps, [str, DeferredToolRequests] if agui else str, None)
        extra: dict[str, Any] = {}
        if agui:
            extra["deferred_tool_results"] = turn.deferred
            if turn.frontend_tools:
                extra["toolsets"] = [ExternalToolset([ToolDefinition(**tool) for tool in turn.frontend_tools], id="studio")]
        try:
            async with self.events:
                result = await chat_agents()[turn.role].run(message_history=turn.history, **options, **extra)
        except (ActivityError, AgentRunError) as exc:
            await workflow.execute_activity(record_agent_run, meter.fields(None, exc, _ms_since(started)), **STEP_ACTIVITY)
            raise
        reply = reply_text(result.output)
        await workflow.execute_activity(
            save_chat_turn, args=[turn, reply, meter.fields(result, None, _ms_since(started))], **STEP_ACTIVITY
        )
        if agui and turn.thread_id:
            await workflow.execute_activity(
                save_chat_thread,
                args=[turn.thread_id, turn.deps.project_id, turn.role, turn.prompt[:80], result.all_messages()],
                **STEP_ACTIVITY,
            )
        return reply


@workflow.defn(name="room:develop_story")
class DevelopStory(RoomWorkflowBase):
    """Develop a story stage by stage, pausing at each checkpoint until the writer decides its proposals.

    Stages: storyline → cast (one specialist call) → a timeline per lead (in parallel) → an outline
    through a draft-critique loop → the first beats drafted as scenes (in parallel) → coverage. Each
    stage ends in proposals; the writer's decisions arrive as ``proposal_decided`` signals (the
    proposals API sends them), and the next stage builds only on what the writer approved.
    """

    key = "develop_story"

    def __init__(self) -> None:
        """Track the stage and the writer's decisions."""
        super().__init__()
        self.stage = "starting"
        self.decided: dict[int, str] = {}

    @workflow.signal
    def proposal_decided(self, proposal_id: int, status: str) -> None:
        """Record the writer's decision on one of this run's proposals."""
        self.decided[proposal_id] = status

    @workflow.query
    def current_stage(self) -> str:
        """Return the stage the pipeline is in (or waiting at)."""
        return self.stage

    @workflow.run
    async def run(self, run: RoomRunInput) -> dict[str, Any]:
        """Run every requested stage."""
        return await self.execute(run, DevelopStoryParams, self.body)

    async def _checkpoint(self, stage: str, proposal_ids: list[int], params: DevelopStoryParams) -> dict[int, dict[str, Any]]:
        """Wait until the writer has decided every proposal of a stage, then refresh the story context."""
        self.stage = f"waiting: {stage}"
        states: dict[int, dict[str, Any]] = await self.activity(proposal_states, self.room.project_id, proposal_ids)
        self.decided.update({key: value["status"] for key, value in states.items() if value["status"] != "proposed"})

        def all_decided() -> bool:
            """Return whether every proposal of the stage has a decision."""
            return all(proposal_id in self.decided for proposal_id in proposal_ids)

        try:
            await workflow.wait_condition(all_decided, timeout=timedelta(hours=params.wait_hours))
        except TimeoutError:
            pass
        # Read the final states (a signal may have been lost while the worker was down).
        states = await self.activity(proposal_states, self.room.project_id, proposal_ids)
        if any(value["status"] == "proposed" for value in states.values()):
            raise ApplicationError(f"Still waiting for your decisions on the {stage}", type="WaitingForWriter", non_retryable=True)
        self.room = replace(self.room, story_brief=await self.activity(story_brief, self.room.project_id))
        self.stage = f"done: {stage}"
        return states

    async def body(self, params: DevelopStoryParams) -> dict[str, Any]:
        """Storyline, cast, timelines, outline, scenes, coverage — each gated on the writer."""
        result: dict[str, Any] = {"stages": {}, "proposal_ids": []}

        def record(stage: str, ids: list[int], states: dict[int, dict[str, Any]], **extra: Any) -> None:
            """Keep what a stage proposed and what the writer decided."""
            result["proposal_ids"].extend(ids)
            approved = sum(state["status"] == "approved" for state in states.values())
            result["stages"][stage] = {"proposed": len(ids), "approved": approved, **extra}

        idea = params.idea
        if "storyline" in params.stages:
            self.stage = "storyline"
            draft = await self.consult(
                "storyline",
                "story_architect",
                "Develop this idea into a storyline: a title, a one-sentence logline, the premise (the dramatic question), "
                f"a one-page synopsis from beginning to end, the theme and the tone.\n\nIdea:\n{idea}",
                StorylineDraft,
                tools=False,
            )
            ids = await self.activity(propose_storyline, self.room.project_id, self.room.workflow_run_id, draft)
            record("storyline", ids, await self._checkpoint("storyline", ids, params), logline=draft.logline)
        cast_names: list[str] = []
        if "characters" in params.stages:
            self.stage = "characters"
            cast = await self.consult(
                "cast",
                "character_specialist",
                f"Create the principal cast ({params.cast_size} characters, leads first) for the story in the Story twin"
                f" (and this idea: {idea[:2000]}). For each: role, a one-line summary, want, need, motive, objective, flaw, "
                "arc summary and voice. Make their wants collide.",
                Cast,
                tools=False,
            )
            ids = await self.activity(propose_cast, self.room.project_id, self.room.workflow_run_id, cast)
            states = await self._checkpoint("cast", ids, params)
            cast_names = [member.name for member in cast.characters]
            record("characters", ids, states, cast=cast_names)
        if "timelines" in params.stages:
            self.stage = "timelines"
            known: dict[str, int] = await self.activity(cast_ids, self.room.project_id, cast_names) if cast_names else {}
            leads = list(known.items())[: min(4, max(1, params.cast_size))]

            async def timeline(name: str, character_id: int) -> list[int]:
                """Develop one lead's timeline and propose it."""
                moments = await self.consult(
                    f"timeline: {name}",
                    "character_specialist",
                    f"Trace {name}'s arc through the story as 4-8 moments in story order: when it happens, what happens, "
                    "what they want in that moment, and how they feel.",
                    CharacterTimeline,
                    tools=False,
                )
                ids: list[int] = await self.activity(propose_timeline, self.room.project_id, self.room.workflow_run_id, character_id, name, moments)
                return ids

            ids = [item for batch in await asyncio.gather(*(timeline(name, character_id) for name, character_id in leads)) for item in batch]
            if ids:
                record("timelines", ids, await self._checkpoint("timelines", ids, params), characters=[name for name, _ in leads])
        if "outline" in params.stages:
            self.stage = "outline"
            outline = await self.consult(
                "outline",
                "story_editor",
                "Write the beat outline of this story (three acts, roughly 12-24 causally linked beats). Build on the "
                f"approved storyline, cast and timelines in the Story twin.\n\nIdea:\n{idea[:4000]}",
                Outline,
                tools=False,
            )
            for round_number in range(1, params.outline_rounds + 1):
                critique = await self.consult(
                    f"critique_{round_number}",
                    "script_doctor",
                    f"Critique this outline for causality, stakes, escalation and payoff.\n\n{outline_text(outline)}",
                    Critique,
                    tools=False,
                )
                if critique.score >= 8:
                    break
                outline = await self.consult(
                    f"revise_{round_number}",
                    "story_editor",
                    f"Revise this outline to address the critique. Keep what works.\n\n{outline_text(outline)}\n\n{critique_text(critique)}",
                    Outline,
                    tools=False,
                )
            ids = await self.activity(propose_beats, self.room.project_id, self.room.workflow_run_id, outline)
            record("outline", ids, await self._checkpoint("outline", ids, params), beats=len(outline.beats))
        if "scenes" in params.stages and params.draft_beats:
            self.stage = "scenes"
            beats = (await self.activity(outline_beats, self.room.project_id, None))[: params.draft_beats]
            if beats:

                async def write(index: int, beat: dict[str, Any]) -> dict[str, Any]:
                    """Dramatise one beat as a scene."""
                    cast = beat.get("cast") or []
                    cues = f"\n\nCharacter cues, spelt exactly like this: {', '.join(cast)}." if cast else ""
                    draft = await self.consult(
                        f"scene: {beat['title']}",
                        "scene_writer",
                        "Write this beat as one new screenplay scene in Fountain, heading first, true to each character's voice "
                        f"and objective.\n\nBeat: {beat['title']} — {beat.get('summary', '')}{cues}",
                        SceneDraft,
                    )
                    return {"index": index, "title": beat["title"], "beat_id": beat.get("beat_id"), **draft.model_dump()}

                drafts = sorted(await asyncio.gather(*(write(index, beat) for index, beat in enumerate(beats))), key=lambda item: item["index"])
                ids = await self.activity(propose_scenes, self.room.project_id, self.room.workflow_run_id, drafts)
                states = await self._checkpoint("scenes", ids, params)
                created = next((state.get("created_scene_ids") for state in states.values() if state.get("created_scene_ids")), None) or []
                links = [[draft["beat_id"], scene_id] for draft, scene_id in zip(drafts, created, strict=False) if draft.get("beat_id")]
                linked = await self.activity(link_beat_scenes, self.room.project_id, links) if links else 0
                record("scenes", ids, states, drafted=len(drafts), linked=linked)
        if "coverage" in params.stages:
            self.stage = "coverage"
            report = await self.consult(
                "coverage",
                "coverage_reader",
                "Write studio coverage of the story so far (storyline, cast, outline and any drafted scenes): logline, "
                "synopsis, 1-10 grades for premise, structure, character, dialogue and pacing, strengths, weaknesses, verdict.",
                Coverage,
            )
            result["coverage"] = report.model_dump()
        self.stage = "finished"
        return result


ROOM_WORKFLOW_CLASSES: list[type] = [
    NotesToOutline,
    DraftScenes,
    RewriteScene,
    CharacterArcs,
    Brainstorm,
    AudiencePanel,
    CoverageReport,
    ContinuityPass,
    DevelopStory,
]
