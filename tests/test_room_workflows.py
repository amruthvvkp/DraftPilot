"""Test the room workflow graphs end to end with a scripted model and a real database."""

from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from _async import run_async
from _db import memory_session
from pydantic import ValidationError
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.agents.deps import RoomDeps
from draftpilot.agents.workflows import (
    ROOM_WORKFLOWS,
    WorkflowDeps,
    run_room_workflow,
    summarize_panel,
    validate_params,
)
from draftpilot.models import (
    Act,
    AgentProposal,
    AgentRun,
    Block,
    KnowledgeNode,
    Project,
    Scene,
    Screenplay,
    StoryArtifact,
)

SCENE = "INT. RIVER BANK - DAY\n\nEdward wades in.\n\nEDWARD\nThere she is.\n"
Responder = Callable[[str, int], dict[str, Any]]


def _room(responders: dict[str, Responder]) -> FunctionModel:
    """Return a model that answers each typed output (by schema title) with a scripted payload."""
    calls: dict[str, int] = {}

    async def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        """Call the output tool with the scripted payload for this output type."""
        tool = info.output_tools[0]
        title = str(tool.parameters_json_schema.get("title"))
        prompt = next(
            part.content
            for message in reversed(messages)
            if isinstance(message, ModelRequest)
            for part in message.parts
            if isinstance(part, UserPromptPart) and isinstance(part.content, str)
        )
        count = calls[title] = calls.get(title, 0) + 1
        return ModelResponse(parts=[ToolCallPart(tool_name=tool.name, args=responders[title](prompt, count))])

    return FunctionModel(respond)


def _outline(_prompt: str, count: int) -> dict[str, Any]:
    """Return a three-beat outline; revisions say so in the logline."""
    return {
        "logline": "A son chases his dying father's tall tales." + (" (revised)" if count > 1 else ""),
        "beats": [
            {"act": 1, "title": "The wedding toast", "summary": "Edward steals Will's wedding."},
            {"act": 2, "title": "The witch's eye", "summary": "Young Edward sees his death."},
            {"act": 3, "title": "The river", "summary": "Will carries Edward to the river."},
        ],
    }


def _scores(*scores: int) -> Responder:
    """Return a critique responder that grades successive drafts with the given scores."""

    def critique(_prompt: str, count: int) -> dict[str, Any]:
        """Grade the draft."""
        return {"score": scores[min(count, len(scores)) - 1], "problems": ["Act 2 sags"], "fixes": ["Raise the stakes"]}

    return critique


@pytest.fixture
def project(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[AsyncSession]:
    """Seed a small Big Fish project in a file database; give every scope its own session."""
    context = memory_session(f"sqlite+aiosqlite:///{tmp_path / 'room.db'}")
    session = run_async(context.__aenter__())

    async def seed() -> None:
        """Persist a draft with one scene, a brief, and two Story-twin characters."""
        project = Project(title="Big Fish")
        session.add(project)
        await session.flush()
        screenplay = Screenplay(project_id=project.id or 0, title="Big Fish")
        session.add(screenplay)
        await session.flush()
        act = Act(screenplay_id=screenplay.id or 0)
        session.add(act)
        await session.flush()
        scene = Scene(act_id=act.id or 0, heading="EXT. RIVER - DAY", version=2)
        session.add(scene)
        await session.flush()
        session.add(Block(scene_id=scene.id or 0, text="The river is wide.", origin="human"))
        session.add(StoryArtifact(project_id=project.id or 0, kind="brief", title="Brief", content="A tall tale."))
        for label, lines in (("Will", 145), ("Edward", 307), ("Karl", 12)):
            session.add(
                KnowledgeNode(project_id=project.id or 0, kind="character", label=label, node_metadata={"dialogue_lines": lines})
            )
        await session.commit()
        await session.close()

    run_async(seed())

    @asynccontextmanager
    async def scope() -> AsyncIterator[AsyncSession]:
        """Open a fresh session per scope, as production does, so parallel branches stay isolated."""
        async with AsyncSession(session.bind, expire_on_commit=False) as scoped:
            yield scoped

    for target in ("draftpilot.mcp.server", "draftpilot.agents.runtime", "draftpilot.agents.workflows"):
        monkeypatch.setattr(f"{target}.session_scope", scope)
    monkeypatch.setattr("draftpilot.core.events.get_redis", lambda: _NoRedis())
    yield session
    run_async(context.__aexit__(None, None, None))


class _NoRedis:
    """Drop live-sync publishes."""

    async def publish(self, *_args: object) -> None:
        """Ignore the event."""


def _run(key: str, params: dict[str, Any], responders: dict[str, Responder]) -> tuple[dict[str, Any], list[int]]:
    """Run one workflow with the scripted room and return its result and every progress trail length."""
    progress: list[int] = []

    async def report(trail: list[dict[str, Any]]) -> None:
        """Record how long the trail was at each report."""
        progress.append(len(trail))

    deps = WorkflowDeps(
        model=_room(responders),
        provider="test",
        model_name="scripted",
        room=RoomDeps(project_id=1, permission_mode="chat_only"),
        run_id=None,
        progress=report,
    )
    return run_async(run_room_workflow(key, params, deps)), progress


def _all(session: AsyncSession, model: type[Any]) -> list[Any]:
    """Return every row of a model through a fresh query."""

    async def query() -> list[Any]:
        """Select every row."""
        async with AsyncSession(session.bind) as fresh:
            return list((await fresh.exec(select(model))).all())

    return run_async(query())


def test_notes_to_outline_revises_until_the_critique_passes_then_proposes(project: AsyncSession) -> None:
    """A weak first critique triggers one revision; the result is proposed, never applied."""
    result, progress = _run(
        "notes_to_outline",
        {"notes": "Father and son; tall tales; a river.", "max_rounds": 3, "target_score": 8},
        {"Outline": _outline, "Critique": _scores(5, 9)},
    )
    assert [step["step"] for step in result["trail"]] == ["draft", "critique_1", "revise_1", "critique_2"]
    assert [step["role"] for step in result["trail"]] == ["story_editor", "script_doctor", "story_editor", "script_doctor"]
    assert progress == [1, 2, 3, 4]
    assert result["rounds"] == 1 and result["outline"]["logline"].endswith("(revised)")
    proposals = _all(project, AgentProposal)
    assert [proposal.id for proposal in proposals] == result["proposal_ids"]
    assert all(proposal.status == "proposed" and proposal.target_kind == "artifact" for proposal in proposals)
    brief, outline = (next(a for a in _all(project, StoryArtifact) if a.id == p.target_id) for p in proposals)
    assert brief.content == "A tall tale."  # untouched until the writer approves
    assert outline.kind == "outline" and outline.content == ""
    assert proposals[0].before == {"content": "A tall tale."}
    assert [beat["sequence"] for beat in proposals[1].operation["artifact_metadata"]["beats"]] == [1, 2, 3]
    assert "## Act 2" in proposals[1].operation["content"]
    runs = _all(project, AgentRun)
    assert len(runs) == 4 and {run.kind for run in runs} == {"workflow"}


def test_the_loop_stops_at_max_rounds_even_when_the_critique_is_poor(project: AsyncSession) -> None:
    """``max_rounds=0`` means draft, critique once, then propose."""
    result, _ = _run(
        "notes_to_outline",
        {"notes": "A river.", "max_rounds": 0},
        {"Outline": _outline, "Critique": _scores(2)},
    )
    assert [step["step"] for step in result["trail"]] == ["draft", "critique_1"]
    assert result["critique"]["score"] == 2 and len(result["proposal_ids"]) == 2


def test_brainstorm_fans_out_one_brainstormer_per_lens_then_shortlists(project: AsyncSession) -> None:
    """Every lens is explored in parallel; the shortlist sees all of them; nothing is proposed."""
    seen: list[str] = []

    def ideas(prompt: str, _count: int) -> dict[str, Any]:
        """Pitch one idea named after the lens in the prompt."""
        lens = prompt.split("'")[1]
        return {"ideas": [{"title": f"{lens} idea", "pitch": "A pitch."}]}

    def shortlist(prompt: str, _count: int) -> dict[str, Any]:
        """Pick the first idea and remember what was pitched."""
        seen.append(prompt)
        return {"picks": [{"title": "genre twist idea", "reason": "Fresh."}], "synthesis": "Go with the twist."}

    result, _ = _run(
        "brainstorm",
        {"topic": "How does Will learn the truth?", "lenses": ["character-driven", "genre twist", "visual set piece"]},
        {"IdeaSet": ideas, "Shortlist": shortlist},
    )
    assert sorted(group["lens"] for group in result["lenses"]) == ["character-driven", "genre twist", "visual set piece"]
    assert all(lens in seen[0] for lens in ("character-driven idea", "genre twist idea", "visual set piece idea"))
    assert result["shortlist"]["synthesis"] == "Go with the twist." and result["proposes"] is False
    assert _all(project, AgentProposal) == []


def test_character_arcs_default_to_the_story_twins_leads(project: AsyncSession) -> None:
    """With no names given, the two characters with the most dialogue get arcs, proposed as one change."""

    def arc(prompt: str, _count: int) -> dict[str, Any]:
        """Return an arc for the character named first in the prompt."""
        name = prompt.split("Develop ")[1].split("'s arc")[0]
        return {"character": name, "want": "To be believed.", "need": "To be known.", "arc_summary": f"{name} changes."}

    result, _ = _run("character_arcs", {"top": 2}, {"CharacterArc": arc})
    assert sorted(item["character"] for item in result["arcs"]) == ["Edward", "Will"]
    (proposal,) = _all(project, AgentProposal)
    assert proposal.id == result["proposal_ids"][0]
    assert sorted(item["character"] for item in proposal.operation["artifact_metadata"]["character_arcs"]) == ["Edward", "Will"]
    assert next(a for a in _all(project, StoryArtifact) if a.id == proposal.target_id).kind == "character"


def test_rewrite_retries_invalid_fountain_and_proposes_a_reversible_scene_change(project: AsyncSession) -> None:
    """A draft that is not screenplay text is sent back; the valid rewrite becomes a scene proposal."""

    def draft(_prompt: str, count: int) -> dict[str, Any]:
        """Return blank text first, then a real scene."""
        return {"fountain": "   " if count == 1 else SCENE, "rationale": "Tighter."}

    result, _ = _run(
        "rewrite_scene",
        {"scene_id": 1, "brief": "Make it about the fish."},
        {"SceneDraft": draft, "Critique": _scores(9)},
    )
    assert [step["step"] for step in result["trail"]] == ["draft", "critique_1"]
    (proposal,) = _all(project, AgentProposal)
    assert proposal.target_kind == "scene" and proposal.base_version == 2
    assert proposal.operation["heading"] == "INT. RIVER BANK - DAY"
    assert [block["text"] for block in proposal.operation["blocks"]] == ["Edward wades in.", "EDWARD", "There she is."]
    assert proposal.before["blocks"][0]["text"] == "The river is wide."
    assert [block.text for block in _all(project, Block)] == ["The river is wide."]  # unchanged until approved


def test_rewrite_rejects_scenes_outside_the_project(project: AsyncSession) -> None:
    """A scene id that is not in the working draft fails before any model call."""
    with pytest.raises(ValueError, match="working draft"):
        _run("rewrite_scene", {"scene_id": 999, "brief": "x"}, {})


def test_draft_scenes_writes_beats_in_parallel_and_proposes_them_in_order(project: AsyncSession) -> None:
    """Scenes come back in beat order however the parallel branches finish; one append proposal results."""

    def scene(prompt: str, _count: int) -> dict[str, Any]:
        """Write a scene whose heading names the beat."""
        title = prompt.split("Beat: ")[1].split(" — ")[0]
        return {"fountain": f"EXT. {title.upper()} - DAY\n\nSomething happens.\n"}

    result, _ = _run(
        "draft_scenes",
        {"beats": [{"title": "Circus", "summary": "Edward joins."}, {"title": "Spectre", "summary": "A town."}]},
        {"SceneDraft": scene},
    )
    (proposal,) = _all(project, AgentProposal)
    assert proposal.target_kind == "screenplay" and proposal.id == result["proposal_ids"][0]
    assert [item["heading"] for item in proposal.operation["append_scenes"]] == ["EXT. CIRCUS - DAY", "EXT. SPECTRE - DAY"]


def test_draft_scenes_falls_back_to_the_outline_artifacts_beats(project: AsyncSession) -> None:
    """With no beats given, the outline's beats are drafted (up to the limit)."""

    async def outline() -> None:
        """Add an outline artifact with three beats."""
        async with AsyncSession(project.bind) as session:
            beats = [{"title": f"Beat {index}", "summary": "s", "sequence": index} for index in range(1, 4)]
            session.add(StoryArtifact(project_id=1, kind="outline", title="Outline", artifact_metadata={"beats": beats}))
            await session.commit()

    run_async(outline())
    result, _ = _run(
        "draft_scenes", {"limit": 2}, {"SceneDraft": lambda prompt, _c: {"fountain": "INT. ROOM - DAY\n\nA beat.\n"}}
    )
    assert [item["title"] for item in result["scenes"]] == ["Beat 1", "Beat 2"]


def test_audience_panel_scores_every_persona(project: AsyncSession) -> None:
    """Each persona reacts in parallel; the summary averages engagement and finds shared sticking points."""

    def react(prompt: str, _count: int) -> dict[str, Any]:
        """Engage more with the genre fan than the critic."""
        fan = "Genre fan" in prompt
        return {
            "persona": "?",
            "engagement": 9 if fan else 5,
            "would_recommend": fan,
            "lost_at": ["the witch scene"],
        }

    result, _ = _run(
        "audience_panel",
        {"personas": ["Genre fan", "Arthouse critic"], "scene_ids": [1]},
        {"Reaction": react},
    )
    assert sorted(item["persona"] for item in result["reactions"]) == ["Arthouse critic", "Genre fan"]
    assert result["summary"] == {"mean_engagement": 7, "recommend_rate": 0.5, "shared_sticking_points": ["the witch scene"]}


def test_continuity_drops_issues_that_cite_scenes_outside_the_draft(project: AsyncSession) -> None:
    """Hallucinated scene ids are filtered out and counted."""

    def report(_prompt: str, _count: int) -> dict[str, Any]:
        """Report one real and one invented issue."""
        return {
            "issues": [
                {"scene_ids": [1], "kind": "fact", "description": "The river changes name."},
                {"scene_ids": [42], "kind": "prop", "description": "The ring vanishes."},
            ]
        }

    result, _ = _run("continuity", {}, {"ContinuityReport": report})
    assert [issue["scene_ids"] for issue in result["issues"]] == [[1]] and result["dropped"] == 1


def test_coverage_returns_graded_coverage(project: AsyncSession) -> None:
    """Coverage is a single typed report."""
    grades = {"premise": 8, "structure": 6, "character": 9, "dialogue": 7, "pacing": 5}
    result, _ = _run(
        "coverage",
        {},
        {"Coverage": lambda _p, _c: {"logline": "L", "synopsis": "S", "verdict": "consider", **grades}},
    )
    assert result["coverage"]["verdict"] == "consider" and result["coverage"]["pacing"] == 5


def test_params_are_validated_and_the_catalogue_is_complete() -> None:
    """Bad parameters and unknown workflows are rejected; every workflow's roles exist."""
    from draftpilot.agents.specs import load_specs

    with pytest.raises(ValidationError):
        validate_params("rewrite_scene", {"brief": "x"})
    with pytest.raises(KeyError):
        validate_params("write_my_movie", {})
    assert {role for workflow in ROOM_WORKFLOWS.values() for role in workflow.roles} <= set(load_specs())
    assert summarize_panel([]) == {"mean_engagement": 0, "recommend_rate": 0, "shared_sticking_points": []}


def _durable(project: AsyncSession, monkeypatch: pytest.MonkeyPatch, responders: dict[str, Responder]) -> int:
    """Route the worker to the scripted room and persist a queued notes→outline run."""
    from draftpilot.agents import workflow_runner
    from draftpilot.core.config import LLMSettings

    for target in ("draftpilot.worker.functions", "draftpilot.agents.workflow_runner"):
        monkeypatch.setattr(f"{target}.session_scope", _scope_for(project))

    async def llm(_profile: object) -> LLMSettings:
        """Enable a provider for the run."""
        return LLMSettings(enabled=True)

    async def build(_config: object) -> tuple[FunctionModel, str]:
        """Hand the worker the scripted room."""
        return _room(responders), "scripted"

    monkeypatch.setattr(workflow_runner, "_llm_settings", llm)
    monkeypatch.setattr(workflow_runner, "build_chat_model", build)

    async def create() -> int:
        """Persist the queued run."""
        async with AsyncSession(project.bind, expire_on_commit=False) as session:
            run = await workflow_runner.create_room_workflow_run(session, 1, "notes_to_outline", {"notes": "A river.", "max_rounds": 1})
            return run.id or 0

    return run_async(create())


def _scope_for(project: AsyncSession) -> Any:
    """Return a session_scope replacement that opens a fresh session on the test database."""

    @asynccontextmanager
    async def scope() -> AsyncIterator[AsyncSession]:
        """Open a fresh session."""
        async with AsyncSession(project.bind, expire_on_commit=False) as scoped:
            yield scoped

    return scope


def test_the_worker_runs_a_durable_workflow_and_persists_its_result(project: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """A queued run executes in the worker, links its proposals and agent runs, and ends succeeded."""
    from draftpilot.models import WorkflowRun
    from draftpilot.worker.functions import execute_workflow

    run_id = _durable(project, monkeypatch, {"Outline": _outline, "Critique": _scores(9)})
    outcome = run_async(execute_workflow({}, run_id))
    assert outcome["workflow"] == "notes_to_outline" and len(outcome["proposal_ids"]) == 2
    (run,) = _all(project, WorkflowRun)
    assert run.status == "succeeded" and run.permission_mode == "suggest"
    assert [step["step"] for step in run.result["trail"]] == ["draft", "critique_1"]
    assert {proposal.run_id for proposal in _all(project, AgentProposal)} == {run_id}
    assert {agent_run.workflow_run_id for agent_run in _all(project, AgentRun)} == {run_id}


def test_cancelling_a_running_workflow_stops_it_at_the_next_step(project: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """Once the writer cancels, the next progress report stops the graph and nothing is proposed."""
    from draftpilot.models import WorkflowRun
    from draftpilot.worker.functions import execute_workflow

    def cancel_then_outline(prompt: str, count: int) -> dict[str, Any]:
        """Cancel the run from 'the writer's side' while the first step is in flight."""

        async def cancel() -> None:
            """Mark the run cancelled."""
            async with AsyncSession(project.bind) as session:
                run = await session.get(WorkflowRun, run_id)
                assert run is not None
                run.status = "cancelled"
                session.add(run)
                await session.commit()

        import asyncio

        asyncio.get_running_loop().create_task(cancel())
        return _outline(prompt, count)

    run_id = _durable(project, monkeypatch, {"Outline": cancel_then_outline, "Critique": _scores(9)})
    assert run_async(execute_workflow({}, run_id)) == {"status": "cancelled"}
    (run,) = _all(project, WorkflowRun)
    assert run.status == "cancelled" and _all(project, AgentProposal) == []


def test_the_room_api_lists_workflows_and_queues_valid_runs(project: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """The launcher sees every workflow's schema; starts are validated before anything is queued."""
    from collections.abc import AsyncGenerator
    from unittest.mock import AsyncMock, MagicMock

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from draftpilot.api.room import router
    from draftpilot.core.db import async_get_db

    pool = MagicMock(enqueue_job=AsyncMock())

    async def get_pool() -> MagicMock:
        """Return the fake queue."""
        return pool

    monkeypatch.setattr("draftpilot.api.room.get_arq_pool", get_pool)
    app = FastAPI()

    async def dependency() -> AsyncGenerator[AsyncSession]:
        """Yield a fresh session on the test database."""
        async with AsyncSession(project.bind, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[async_get_db] = dependency
    app.include_router(router, prefix="/api/v1")
    client = TestClient(app)

    listed = client.get("/api/v1/projects/1/room/workflows").json()
    assert [item["key"] for item in listed] == list(ROOM_WORKFLOWS)
    assert "notes" in next(item for item in listed if item["key"] == "notes_to_outline")["params_schema"]["properties"]

    assert client.post("/api/v1/projects/1/room/workflows", json={"workflow": "nope"}).status_code == 404
    assert client.post("/api/v1/projects/1/room/workflows", json={"workflow": "rewrite_scene", "params": {}}).status_code == 422
    assert client.post("/api/v1/projects/9/room/workflows", json={"workflow": "coverage"}).status_code == 404
    pool.enqueue_job.assert_not_awaited()

    started = client.post("/api/v1/projects/1/room/workflows", json={"workflow": "coverage", "params": {"focus": "Act 2"}})
    assert started.status_code == 202, started.text
    body = started.json()
    assert body["kind"] == "room_workflow" and body["input"]["params"] == {"focus": "Act 2"} and body["max_attempts"] == 1
    pool.enqueue_job.assert_awaited_once_with("execute_workflow", body["id"])


def test_self_contained_steps_get_no_tools_but_reading_steps_do(project: AsyncSession) -> None:
    """Loop steps are handed the material, so they cannot wander the project; arcs still read it."""
    seen: dict[str, int] = {}

    offered: list[tuple[str, int]] = []

    async def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        """Record the tools offered, then answer."""
        tool = info.output_tools[0]
        title = str(tool.parameters_json_schema.get("title"))
        offered.append((title, len(info.function_tools)))
        seen[title] = seen.get(title, 0) + 1
        payload = {"Outline": _outline, "Critique": _scores(9)}.get(title) or (
            lambda _p, _c: {"character": "Will", "want": "w", "need": "n", "arc_summary": "s"}
        )
        return ModelResponse(parts=[ToolCallPart(tool_name=tool.name, args=payload("", seen[title]))])

    deps = WorkflowDeps(model=FunctionModel(respond), provider="test", model_name="scripted", room=RoomDeps(project_id=1, permission_mode="chat_only"))
    run_async(run_room_workflow("notes_to_outline", {"notes": "A river.", "max_rounds": 0}, deps))
    run_async(run_room_workflow("character_arcs", {"characters": ["Will"]}, deps))
    assert offered[0] == ("Outline", 0) and offered[1] == ("Critique", 0)
    assert offered[2][0] == "CharacterArc" and offered[2][1] > 0


def test_rewrite_facts_measure_length_and_added_speakers() -> None:
    """The grader is told the measured length ratio and any speaker the rewrite added."""
    from draftpilot.agents.workflows import rewrite_facts

    original = "INT. HALL - NIGHT\n\nWill waits by the door for a long time.\n\nWILL\nWhere is he?\n"
    assert rewrite_facts(original, original).endswith("no new speaking characters.")
    shorter = "INT. HALL - NIGHT\n\nWill waits.\n\nSANDRA\nHe'll come.\n"
    facts = rewrite_facts(original, shorter)
    assert facts.startswith("the rewrite is 5") and "new speaking characters: SANDRA." in facts
