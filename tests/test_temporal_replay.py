"""Replay tests: Temporal workflow code must stay deterministic and compatible with recorded histories.

SDLC rule: any workflow edit must pass these. ``test_every_workflow_replays_its_own_history`` runs one
scenario per workflow type and replays what it recorded, which catches nondeterminism in the current
code. ``test_recorded_histories_still_replay`` replays the committed ``tests/temporal_histories/``,
which catches changes that would break runs already in flight. When a change is intentionally
incompatible, version it with ``workflow.patched`` or re-record the histories with
``TEMPORAL_RECORD=1 uv run pytest tests/test_temporal_replay.py`` and say why in the commit.
"""

import json
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
from _async import run_async
from _temporal import temporal_worker
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlmodel.ext.asyncio.session import AsyncSession
from temporalio.client import WorkflowFailureError, WorkflowHistory
from temporalio.worker import Replayer
from test_room_workflows import (  # noqa: F401 - project is a fixture
    SCENE,
    _outline,
    _scope_for,
    _scores,
    project,
)

from draftpilot.agents.chat import ChatTurn
from draftpilot.agents.deps import RoomDeps
from draftpilot.agents.models import register_model
from draftpilot.agents.workflows import RoomRunInput
from draftpilot.core import temporal
from draftpilot.models import WorkflowRun
from draftpilot.worker.activities import all_activities
from draftpilot.worker.workflows import all_workflows

HISTORIES = Path(__file__).parent / "temporal_histories"
# Recorded runs carry this model ref; replay only plans requests with it, so any scripted model will do.
REPLAY_MODEL = "replay-scripted"

PAYLOADS: dict[str, Any] = {
    "Outline": lambda count: _outline("", count),
    "Critique": lambda count: _scores(5, 9)("", count),
    "IdeaSet": lambda _count: {"ideas": [{"title": "Idea", "pitch": "A pitch."}]},
    "Shortlist": lambda _count: {"picks": [{"title": "Idea", "reason": "Fresh."}], "synthesis": "Go."},
    "CharacterArc": lambda _count: {"character": "Will", "want": "w", "need": "n", "arc_summary": "s"},
    "SceneDraft": lambda _count: {"fountain": SCENE, "rationale": "Tighter."},
    "Reaction": lambda _count: {"persona": "?", "engagement": 7, "would_recommend": True, "lost_at": ["act 2"]},
    "Coverage": lambda _count: {"logline": "L", "synopsis": "S", "premise": 8, "structure": 6, "character": 9, "dialogue": 7, "pacing": 5, "verdict": "consider"},
    "StorylineDraft": lambda _count: {"title": "T", "logline": "L", "premise": "P", "synopsis": "S", "theme": "Th", "tone": "To"},
    "ContinuityReport": lambda _count: {"issues": [{"scene_ids": [1], "kind": "fact", "description": "The river changes name."}]},
}

ROOM_SCENARIOS: dict[str, dict[str, Any]] = {
    "notes_to_outline": {"notes": "Father and son; tall tales; a river.", "max_rounds": 2},
    "brainstorm": {"topic": "How does Will learn the truth?", "lenses": ["character-driven", "genre twist"]},
    "character_arcs": {"characters": ["Will", "Edward"]},
    "rewrite_scene": {"scene_id": 1, "brief": "Make it about the fish."},
    "draft_scenes": {"beats": [{"title": "Circus", "summary": "Edward joins."}]},
    "audience_panel": {"personas": ["Genre fan", "Arthouse critic"], "scene_ids": [1]},
    "coverage": {},
    "continuity": {},
}


def _model() -> FunctionModel:
    """Answer every typed output with its scripted payload, and plain chat with text."""
    counts: dict[str, int] = {}

    def respond(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        """Call the output tool with this output type's payload, or reply in text."""
        if not info.output_tools:
            return ModelResponse(parts=[TextPart(content="Open on the river.")])
        tool = info.output_tools[0]
        title = str(tool.parameters_json_schema.get("title"))
        counts[title] = counts.get(title, 0) + 1
        return ModelResponse(parts=[ToolCallPart(tool_name=tool.name, args=PAYLOADS[title](counts[title]))])

    async def stream(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[str]:
        """Stream the chat reply."""
        yield "Open on the river."

    return FunctionModel(respond, stream_function=stream, model_name="scripted")


@pytest.fixture
def studio(project: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> Iterator[AsyncSession]:  # noqa: F811 - the fixture above
    """Point every job and run activity at the seeded project database."""
    for target in ("draftpilot.worker.functions", "draftpilot.agents.workflow_runner", "draftpilot.agents.chat"):
        monkeypatch.setattr(f"{target}.session_scope", _scope_for(project))
    yield project


async def _record(database: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> dict[str, WorkflowHistory]:
    """Run one scenario per workflow type on a time-skipping server and return every history, by workflow id."""
    ref = register_model(_model(), REPLAY_MODEL)

    async def describe(_profile_id: int | None = None) -> str:
        """Resolve every run to the scripted model."""
        return ref

    monkeypatch.setattr("draftpilot.agents.workflow_runner.describe_model", describe)
    room = RoomDeps(project_id=1, permission_mode="chat_only", model_ref=ref)
    async with temporal_worker(all_workflows(), all_activities()) as (client, queue):
        ids: dict[str, str] = {}
        for key, params in ROOM_SCENARIOS.items():
            ids[f"room-{key}"] = f"replay-room-{key}"
            await client.execute_workflow(f"room:{key}", RoomRunInput(workflow=key, params=params, room=room), id=ids[f"room-{key}"], task_queue=queue)
        turn = ChatTurn(role="story_architect", prompt="Where should we open?", history=[ModelRequest(parts=[UserPromptPart(content="Where should we open?")])], deps=room)
        ids["room-chat"] = "replay-room-chat"
        await client.execute_workflow("room:chat", turn, id=ids["room-chat"], task_queue=queue)
        threaded = ChatTurn(role="story_architect", prompt="And the ending?", history=turn.history, deps=room, thread_id="replay-thread")
        ids["room-chat-agui"] = "replay-room-chat-agui"
        await client.execute_workflow("room:chat", threaded, id=ids["room-chat-agui"], task_queue=queue)
        # The pipeline waits at its first checkpoint; with no writer decision it stops after the wait (time-skipped).
        ids["room-develop_story"] = "replay-room-develop_story"
        pipeline = RoomRunInput(workflow="develop_story", params={"idea": "A tall tale.", "stages": ["storyline"], "wait_hours": 1}, room=room)
        with pytest.raises(WorkflowFailureError):
            await client.execute_workflow("room:develop_story", pipeline, id=ids["room-develop_story"], task_queue=queue)
        async with AsyncSession(database.bind, expire_on_commit=False) as session:
            evaluation = WorkflowRun(project_id=1, kind="evaluation", input={"screenplay_id": 1}, max_attempts=2)
            room_run = WorkflowRun(project_id=1, kind="room_workflow", input={"workflow": "coverage", "params": {}}, max_attempts=1, permission_mode="suggest")
            session.add_all([evaluation, room_run])
            await session.commit()
            run_ids = (evaluation.id or 0, room_run.id or 0)
        for name, run_id in zip(("run-evaluation", "run-room"), run_ids, strict=True):
            ids[name] = temporal.run_workflow_id(run_id)
            await client.execute_workflow(temporal.RUN_WORKFLOW, run_id, id=ids[name], task_queue=queue)
        ids["run-room-child"] = f"{ids['run-room']}-room"
        ids["job-refresh_story_twin"] = "replay-refresh-story-twin"
        await client.execute_workflow("refresh_story_twin", 1, id=ids["job-refresh_story_twin"], task_queue=queue)
        return {workflow_id: await client.get_workflow_handle(workflow_id).fetch_history() for workflow_id in ids.values()}


async def _replay(histories: list[WorkflowHistory]) -> None:
    """Replay histories against the current workflow code, failing on any nondeterminism."""
    register_model(_model(), REPLAY_MODEL)
    replayer = Replayer(workflows=all_workflows(), plugins=[PydanticAIPlugin()])
    for history in histories:
        await replayer.replay_workflow(history)


def test_every_workflow_replays_its_own_history(studio: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """Each workflow type, run once, replays deterministically; ``TEMPORAL_RECORD=1`` saves the histories."""
    histories = run_async(_record(studio, monkeypatch))
    types = {json.loads(history.to_json())["events"][0]["workflowExecutionStartedEventAttributes"]["workflowType"]["name"] for history in histories.values()}
    assert types == {workflow.__temporal_workflow_definition.name for workflow in all_workflows()} - {"index_rag_document", "delete_rag_document", "reindex_project", "purge_rag_project"}
    run_async(_replay(list(histories.values())))
    if os.environ.get("TEMPORAL_RECORD") == "1":
        HISTORIES.mkdir(exist_ok=True)
        for workflow_id, history in histories.items():
            (HISTORIES / f"{workflow_id}.json").write_text(history.to_json() + "\n")


def test_recorded_histories_still_replay() -> None:
    """Runs recorded by earlier code must replay on the current code (a break would strand in-flight runs)."""
    files = sorted(HISTORIES.glob("*.json"))
    assert files, "record histories with TEMPORAL_RECORD=1 uv run pytest tests/test_temporal_replay.py"
    run_async(_replay([WorkflowHistory.from_json(path.stem, path.read_text()) for path in files]))

