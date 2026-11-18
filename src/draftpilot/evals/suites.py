"""Eval suites for the writers' room, each a ``pydantic_evals`` dataset plus the task that runs it."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Any

from pydantic_evals import Case, Dataset, increment_eval_metric, set_eval_attribute

from draftpilot.agents.deps import RoomDeps
from draftpilot.agents.runtime import run_role
from draftpilot.agents.specs import role_spec
from draftpilot.agents.workflows import (
    Cast,
    JourneyTimeline,
    SharedMoments,
    StorylineDraft,
    WorkflowDeps,
    journey_cards,
    run_room_workflow,
    scene_fountain,
)
from draftpilot.core.db import session_scope
from draftpilot.core.screenplay.hydrate import blocks_for_scene
from draftpilot.core.story import entities
from draftpilot.core.twins import story_twin_brief
from draftpilot.evals.evaluators import (
    CastDeveloped,
    CritiqueImproved,
    FindsSharedMoments,
    FlagsArc,
    FoundPlanted,
    Judges,
    KeepsCast,
    MentionsAny,
    NoHallucinatedScenes,
    OutlineShape,
    SensibleIntensities,
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


# The Journey map seeded for the journey suite: (character, role, [(title, story_time, intensity, scene number)]).
# Edward and Will share the wedding and the river; Will's lane is flat; Karl has a single card.
JOURNEY_MAP: list[tuple[str, str, list[tuple[str, str, int, int | None]]]] = [
    ("Edward", "protagonist", [
        ("Sees his death in the witch's glass eye", "1937", -3, None),
        ("Tells the catfish story at Will's wedding, stealing the toast", "1998", 3, 1),
        ("Asks Will to tell him how it ends", "today", -2, None),
        ("Will carries him to the river, where everyone waits", "today", 4, None),
    ]),
    ("Will", "supporting", [
        ("His father steals his wedding toast with the fish story", "1998", -1, 1),
        ("Stops speaking to his father for three years", "1998-2001", 0, None),
        ("Carries his father to the river and tells the ending", "today", -1, None),
    ]),
    ("Karl", "supporting", [("Leaves his cave and follows a stranger out of the valley", "1940s", 2, None)]),
]


async def _seed_journey(project: EvalProject) -> dict[str, int]:
    """Lay out ``JOURNEY_MAP`` on the eval project (reusing the Story twin's characters) and return card ids by title."""
    cards: dict[str, int] = {}
    async with session_scope() as session:
        existing = {row.name.casefold(): row for row in await entities.list_entities(session, project.project_id, "character")}
        for name, role, events in JOURNEY_MAP:
            character = existing.get(name.casefold())
            if character is None:
                character = await entities.create_entity(session, project.project_id, "character", {"name": name, "role": role})
            else:
                character = await entities.update_entity(session, project.project_id, "character", character.id, {"role": role}, expected_version=None, require_version=False)
            for position, (title, story_time, intensity, scene) in enumerate(events):
                fields = {"character_id": character.id, "title": title, "story_time": story_time, "intensity": intensity, "position": position,
                          "chrono_index": float(position + 1), "scene_id": project.scene(scene).id if scene else None}
                cards[title] = (await entities.create_entity(session, project.project_id, "timeline_event", fields)).id
    return cards


SHARED_MOMENTS_PROMPT = (
    "These are the approved timelines of the cast, card by card. Find the moments two or more characters share "
    "(the same event seen from each side: the same scene, place and time). For each, give a title, the story time, "
    "one line on what happens, and the card ids (#n) of every participant's side. Propose only real meetings; "
    "an empty list is a fine answer."
)


async def journey(project: EvalProject, model: Any, name: str, judges: Judges) -> tuple[Dataset[Any, Any, Any], Task]:
    """The Journey map agents: a timeline with intensity and motivation, shared moments across lanes, and the arc check."""
    cards = await _seed_journey(project)
    edward, will = (titles for _name, _role, titles in JOURNEY_MAP[:2])
    meetings = [[cards[edward[1][0]], cards[will[0][0]]], [cards[edward[3][0]], cards[will[2][0]]]]
    unrelated = [cards[edward[0][0]], cards[will[1][0]], cards[JOURNEY_MAP[2][2][0][0]]]
    dataset = Dataset[Any, Any, Any](
        name="journey",
        cases=[
            Case(name="edward_timeline", inputs={"kind": "timeline", "character": "Edward"}, evaluators=(
                SensibleIntensities(),
                *judges.evaluators(
                    rubric="Each moment's intensity fits it on the -5 (lowest low) to +5 (highest high) scale: losses and fears "
                    "are negative, triumphs and reconciliations positive. Each motivation says why Edward acts, true to Big Fish.",
                    include_input=False,
                ),
            )),
            Case(name="shared_moments", inputs={"kind": "moments"}, evaluators=(FindsSharedMoments(expected=meetings, unrelated=unrelated),)),
            Case(name="arc_check", inputs={"kind": "arc_check"}, evaluators=(FlagsArc("Will", "flat_arc"), FlagsArc("Karl", "too_few_cards"))),
        ],
    )

    async def task(inputs: dict[str, Any]) -> dict[str, Any]:
        """Run one journey agent step: the develop_story timeline prompt, its shared-moment prompt, or the arc-check workflow."""
        if inputs["kind"] == "timeline":
            character = inputs["character"]
            prompt = (
                f"Trace {character}'s arc through the story as 4-8 moments in story order: when it happens, what happens, "
                "what they want in that moment, why they act (motivation), how they feel, and its intensity from -5 "
                "(their lowest low) to +5 (their highest high). Let the intensity rise and fall: an arc turns."
            )
            # As in develop_story: the story so far arrives as the Story twin brief, and the step has no tools.
            async with session_scope() as session:
                room = replace(_room(project), story_brief=await story_twin_brief(session, project.project_id))
            timeline: JourneyTimeline
            timeline, record = await run_role(role_spec("character_specialist"), model, room, prompt, JourneyTimeline,
                                              provider="lm_studio", model_name=name, kind="eval", tools=False)
            _measure(record)
            return timeline.model_dump()
        if inputs["kind"] == "moments":
            text = (await journey_cards(project.project_id, list(cards.values())))["text"]
            found: SharedMoments
            found, record = await run_role(role_spec("story_editor"), model, _room(project), f"{SHARED_MOMENTS_PROMPT}\n\n{text}", SharedMoments,
                                           provider="lm_studio", model_name=name, kind="eval", tools=False)
            _measure(record)
            return found.model_dump()
        result = await run_room_workflow("arc_check", {}, _workflow_deps(project, model, name))
        return {"findings": result["findings"], "report": result["report"]}

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
        Suite("journey", "Journey map agents: intensity and motivation, shared moments, the arc check", journey),
    )
}
