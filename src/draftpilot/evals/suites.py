"""Eval suites for the writers' room, each a ``pydantic_evals`` dataset plus the task that runs it."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic_evals import Case, Dataset, increment_eval_metric, set_eval_attribute

from draftpilot.agents.deps import RoomDeps
from draftpilot.agents.runtime import run_role
from draftpilot.agents.specs import role_spec
from draftpilot.agents.workflows import (
    Cast,
    StorylineDraft,
    WorkflowDeps,
    run_room_workflow,
    scene_fountain,
)
from draftpilot.core.config import settings
from draftpilot.core.db import session_scope
from draftpilot.core.screenplay.hydrate import blocks_for_scene
from draftpilot.evals.evaluators import (
    CastDeveloped,
    CritiqueImproved,
    FoundPlanted,
    Judges,
    KeepsCast,
    MentionsAny,
    NoHallucinatedScenes,
    OutlineShape,
    Shorter,
    StorylineComplete,
    UsedTools,
    ValidScene,
)
from draftpilot.evals.harness import EvalProject

Task = Callable[[Any], Awaitable[Any]]


@dataclass(frozen=True)
class Suite:
    """One eval suite: build its dataset and task against a seeded project and the models."""

    name: str
    description: str
    build: Callable[[EvalProject, Any, str, Judges], Awaitable[tuple[Dataset[Any, Any, Any], Task]]]


def _room(project: EvalProject) -> RoomDeps:
    """Return read-only room deps bound to the eval project."""
    return RoomDeps(project_id=project.project_id, permission_mode="chat_only")


def _measure(record: Any) -> None:
    """Attach an agent run's cost to the current eval case."""
    increment_eval_metric("requests", record.requests)
    increment_eval_metric("tokens", record.input_tokens + record.output_tokens)


def _workflow_deps(project: EvalProject, model: Any, name: str) -> WorkflowDeps:
    """Return workflow deps for the eval project on LM Studio."""
    return WorkflowDeps(model=model, provider="lm_studio", model_name=name, room=_room(project))


# ---------------------------------------------------------------------------------------------------------------------


async def room_qa(project: EvalProject, model: Any, name: str, judges: Judges) -> tuple[Dataset[Any, Any, Any], Task]:
    """Ask the script editor questions only the script can answer."""
    cases = [
        Case(name="second_scene_heading", inputs="What is the exact scene heading of the second scene? Answer with the heading only.",
             expected_output="INT. WILL'S BEDROOM - NIGHT (1973)", evaluators=(MentionsAny(["will's bedroom"]),)),
        Case(name="wills_wife", inputs="What is the name of Will's wife?", expected_output="Josephine",
             evaluators=(MentionsAny(["josephine"]),)),
        Case(name="wills_mother", inputs="What is Will's mother's first name?", expected_output="Sandra",
             evaluators=(MentionsAny(["sandra"]),)),
        Case(name="witch_eye", inputs="What is special about the witch's eye, and what do the boys see in it?",
             expected_output="She has a glass eye; looking into it shows you how you will die.",
             evaluators=(MentionsAny(["glass"]), MentionsAny(["die", "death"]))),
        Case(name="catfish_ring", inputs="In Edward's opening story, what did the uncatchable fish take from him?",
             expected_output="His (gold) wedding ring.", evaluators=(MentionsAny(["ring"]),)),
    ]
    dataset = Dataset[Any, Any, Any](
        name="room_qa",
        cases=cases,
        evaluators=[
            UsedTools(),
            *judges.evaluators(
                rubric="The reply gives the same answer as the expected output for the Big Fish screenplay. Extra accurate "
                "context is fine; fail only if the answer is wrong, missing, or contradicts the expected output.",
                include_input=True, include_expected_output=True,
            ),
        ],
    )

    async def task(question: str) -> str:
        """Answer one question through the MCP tools."""
        reply: str
        reply, record = await run_role(role_spec("script_editor"), model, _room(project), question, str,
                                       provider="lm_studio", model_name=name, kind="eval")
        _measure(record)
        set_eval_attribute("tools", record.tools_used)
        return reply

    return dataset, task


async def rewrite(project: EvalProject, model: Any, name: str, judges: Judges) -> tuple[Dataset[Any, Any, Any], Task]:
    """Rewrite real scenes to briefs through the draft-critique loop."""
    bedroom, front_hall = project.scene(2), project.scene(4)
    cases = [
        Case(name="bedroom_subtext", inputs={"scene_id": bedroom.id, "brief": "Make it shorter and let Will's resentment show through subtext, not statements."},
             evaluators=(Shorter(),)),
        Case(name="front_hall_tension", inputs={"scene_id": front_hall.id, "brief": "Raise the tension between Will and Sandra as they wait for Edward; keep it the same length or shorter."}),
    ]
    dataset = Dataset[Any, Any, Any](
        name="rewrite",
        cases=cases,
        evaluators=[
            ValidScene(),
            KeepsCast(),
            CritiqueImproved(),
            *judges.evaluators(
                rubric="Given the brief and the original scene, the rewrite delivers the brief, keeps the characters' "
                "voices and the scene's story function, and is correctly formatted screenplay text.",
                include_input=True,
            ),
        ],
    )

    async def task(inputs: dict[str, Any]) -> dict[str, Any]:
        """Run the rewrite workflow with one revision round at most."""
        async with session_scope() as session:
            scene = next(item for item in project.scenes if item.id == inputs["scene_id"])
            original = await scene_fountain(session, scene)
            assert await blocks_for_scene(session, scene.id or 0)
        result = await run_room_workflow("rewrite_scene", {**inputs, "max_rounds": 1}, _workflow_deps(project, model, name))
        increment_eval_metric("steps", len(result["trail"]))
        return {"original": original, "fountain": result["fountain"], "critique": result["critique"], "brief": inputs["brief"]}

    return dataset, task


NOTES = """A lighthouse keeper's daughter, MARA (16), on a remote Scottish island in 1962.
Her father is going blind and hides it. A supply boat stops coming after a storm.
She has to keep the light running and decide whether to row to the mainland for help,
which would reveal his secret and cost him the only job he has. Ends with her choosing the
light over her own escape, and him finally admitting he needs her. Tone: quiet, windswept, hopeful."""


async def outline(project: EvalProject, model: Any, name: str, judges: Judges) -> tuple[Dataset[Any, Any, Any], Task]:
    """Turn fresh notes into a critiqued outline (from scratch, not from the script)."""
    dataset = Dataset[Any, Any, Any](
        name="outline",
        cases=[Case(name="lighthouse", inputs=NOTES, evaluators=(MentionsAny(["mara", "light", "blind", "boat", "storm"], minimum=4),))],
        evaluators=[
            OutlineShape(),
            CritiqueImproved(),
            *judges.evaluators(
                rubric="The outline is a causal, escalating three-act story that honours every element of the writer's "
                "notes (characters, setting, dilemma, ending, tone) without contradicting them.",
                include_input=True,
            ),
        ],
    )

    async def task(notes: str) -> dict[str, Any]:
        """Run notes→outline with one revision round at most."""
        result = await run_room_workflow("notes_to_outline", {"notes": notes, "max_rounds": 1}, _workflow_deps(project, model, name))
        increment_eval_metric("steps", len(result["trail"]))
        return {"outline": result["outline"], "critique": result["critique"]}

    return dataset, task


async def continuity(project: EvalProject, model: Any, name: str, judges: Judges) -> tuple[Dataset[Any, Any, Any], Task]:
    """Plant a timeline contradiction (Will ages 18 years in 11) and check the supervisor catches it."""
    front_hall, paris = project.scene(4), project.scene(5)
    async with session_scope() as session:
        for block in await blocks_for_scene(session, paris.id or 0):
            if "now 28" in block.text:
                block.text = block.text.replace("now 28", "now 35")
                session.add(block)
        await session.commit()
    dataset = Dataset[Any, Any, Any](
        name="continuity",
        cases=[Case(name="planted_age", inputs=[front_hall.id, paris.id],
                    evaluators=(FoundPlanted(kind="timeline", terms=["35", "age", "older"]),))],
        evaluators=[NoHallucinatedScenes()],
    )

    async def task(scene_ids: list[int]) -> dict[str, Any]:
        """Run the continuity pass over the two scenes."""
        result = await run_room_workflow("continuity", {"scene_ids": scene_ids}, _workflow_deps(project, model, name))
        return {"issues": result["issues"], "dropped": result["dropped"]}

    return dataset, task


async def storyline(project: EvalProject, model: Any, name: str, judges: Judges) -> tuple[Dataset[Any, Any, Any], Task]:
    """Develop the lighthouse notes into a storyline (logline, premise, synopsis, theme, tone)."""
    dataset = Dataset[Any, Any, Any](
        name="storyline",
        cases=[Case(name="lighthouse", inputs=NOTES, evaluators=(MentionsAny(["mara", "light", "storm"], minimum=2),))],
        evaluators=[
            StorylineComplete(),
            *judges.evaluators(
                rubric="The storyline is specific and dramatic: the logline names a protagonist, a goal and an obstacle; "
                "the synopsis runs from beginning to end; theme and tone fit the writer's notes, which it never contradicts.",
                include_input=True,
            ),
        ],
    )

    async def task(notes: str) -> dict[str, Any]:
        """Ask the story architect for a storyline."""
        draft: StorylineDraft
        draft, record = await run_role(role_spec("story_architect"), model, _room(project),
                                       f"Develop these notes into a storyline.\n\nNotes:\n{notes}", StorylineDraft,
                                       provider="lm_studio", model_name=name, kind="eval", tools=False)
        _measure(record)
        return draft.model_dump()

    return dataset, task


async def cast(project: EvalProject, model: Any, name: str, judges: Judges) -> tuple[Dataset[Any, Any, Any], Task]:
    """Build the lighthouse cast: profiles with want, need, motive, objective, flaw and arc."""
    dataset = Dataset[Any, Any, Any](
        name="cast",
        cases=[Case(name="lighthouse", inputs=NOTES)],
        evaluators=[
            CastDeveloped(),
            *judges.evaluators(
                rubric="The characters' wants collide; each has an inner need distinct from their want; the cast serves "
                "the writer's notes and includes the characters the notes name.",
                include_input=True,
            ),
        ],
    )

    async def task(notes: str) -> dict[str, Any]:
        """Ask the character specialist for the principal cast."""
        result: Cast
        result, record = await run_role(role_spec("character_specialist"), model, _room(project),
                                        f"Create the principal cast (3-5 characters, leads first) for these notes.\n\nNotes:\n{notes}", Cast,
                                        provider="lm_studio", model_name=name, kind="eval", tools=False)
        _measure(record)
        return result.model_dump()

    return dataset, task


EXACT_QUESTIONS = (
    ("scene_count", "How many scenes does the script have? Give the exact number.", "191", ["191"]),
    ("top_speaker", "Which character speaks the most dialogue, counted in words, and what share of all dialogue words is theirs?", "Edward, about 45%", ["edward"]),
    ("night_scenes", "How many scenes are set at NIGHT according to their headings? Give the exact number.", "50", ["50"]),
)


async def code_mode(project: EvalProject, model: Any, name: str, judges: Judges) -> tuple[Dataset[Any, Any, Any], Task]:
    """Ask exact questions about Big Fish with code mode (one Monty snippet) and with plain tool calls."""
    cases = [
        Case(
            name=f"{key}_{mode}",
            inputs={"question": question, "code_mode": mode == "code"},
            expected_output=expected,
            evaluators=(MentionsAny(terms),) + ((UsedTools(any_of=["analyze_script"]),) if mode == "code" else ()),
        )
        for key, question, expected, terms in EXACT_QUESTIONS
        for mode in ("code", "tools")
    ]
    dataset = Dataset[Any, Any, Any](name="code_mode", cases=cases)

    async def task(inputs: dict[str, Any]) -> str:
        """Answer one question as the researcher, with Monty on and code mode on or off for the run."""
        enabled = settings.monty.enabled
        settings.monty.enabled = True
        try:
            room = RoomDeps(project_id=project.project_id, permission_mode="chat_only", code_mode=inputs["code_mode"])
            reply: str
            reply, record = await run_role(role_spec("researcher"), model, room, inputs["question"], str,
                                           provider="lm_studio", model_name=name, kind="eval")
        finally:
            settings.monty.enabled = enabled
        _measure(record)
        increment_eval_metric("tool_calls", record.tool_calls)
        set_eval_attribute("tools", record.tools_used)
        return reply

    return dataset, task


SUITES: dict[str, Suite] = {
    suite.name: suite
    for suite in (
        Suite("room_qa", "Grounded answers about Big Fish through the MCP tools", room_qa),
        Suite("rewrite", "Scene rewrites to a brief through the draft-critique loop", rewrite),
        Suite("outline", "Notes → outline from scratch", outline),
        Suite("continuity", "Catching a planted timeline contradiction", continuity),
        Suite("storyline", "Notes → storyline (logline, premise, synopsis, theme, tone)", storyline),
        Suite("cast", "Notes → a principal cast with motives and objectives", cast),
        Suite("code_mode", "Exact Big Fish stats: code mode (Monty) vs plain tool calls", code_mode),
    )
}
