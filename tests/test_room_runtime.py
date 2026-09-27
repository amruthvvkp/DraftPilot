"""Test room agents working through DraftPilot's in-process MCP server (deterministic models)."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from _async import run_async
from _db import memory_session
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import (
    AgentInfo,
    DeltaToolCall,
    DeltaToolCalls,
    FunctionModel,
)
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.agents import runtime
from draftpilot.agents.deps import RoomDeps
from draftpilot.agents.specs import load_specs, role_spec
from draftpilot.models import (
    Act,
    AgentRun,
    Block,
    MCPApprovalRequest,
    Project,
    Scene,
    Screenplay,
    StoryArtifact,
)


def _script(*steps: dict[str, Any] | str) -> FunctionModel:
    """Return a model that makes the given tool calls in order, then answers with the last text."""
    calls = [step for step in steps if isinstance(step, dict)]
    final = next(step for step in reversed(steps) if isinstance(step, str))

    def respond(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        """Emit the next scripted tool call, or the final answer once calls are exhausted."""
        made = sum(isinstance(part, ToolCallPart) for message in messages for part in getattr(message, "parts", []))
        if made < len(calls):
            step = calls[made]
            return ModelResponse(parts=[ToolCallPart(tool_name=step["tool"], args=step["args"])])
        return ModelResponse(parts=[TextPart(content=final)])

    async def stream(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str | DeltaToolCalls]:
        """Stream the same scripted step for streamed runs."""
        part = respond(messages, info).parts[0]
        if isinstance(part, ToolCallPart):
            yield {0: DeltaToolCall(name=part.tool_name, json_args=json.dumps(part.args))}
        else:
            yield part.content

    return FunctionModel(respond, stream_function=stream)


def _tool_returns(messages: list[ModelMessage]) -> list[str]:
    """Return every tool result (or retry prompt) the model saw, as text."""
    seen: list[str] = []
    for message in messages:
        for part in getattr(message, "parts", []):
            if isinstance(part, ToolReturnPart) or part.part_kind == "retry-prompt":
                seen.append(part.model_response_str() if hasattr(part, "model_response_str") else str(part.content))
    return seen


@pytest.fixture
def room(monkeypatch: pytest.MonkeyPatch) -> AsyncSession:
    """Seed two projects in one in-memory database and route MCP + AgentRun writes to it."""
    context = memory_session()
    session = run_async(context.__aenter__())

    async def seed() -> None:
        """Persist the room's project (with a scene and artifact) and an unrelated project."""
        mine, other = Project(title="Big Fish"), Project(title="Someone else's film")
        session.add_all([mine, other])
        await session.flush()
        screenplay = Screenplay(project_id=mine.id or 0, title="Big Fish", title_page={"Author": "John August"})
        session.add(screenplay)
        await session.flush()
        act = Act(screenplay_id=screenplay.id or 0)
        session.add(act)
        await session.flush()
        scene = Scene(act_id=act.id or 0, heading="EXT. RIVER - DAY")
        session.add(scene)
        await session.flush()
        session.add(Block(scene_id=scene.id or 0, text="Edward catches the fish."))
        session.add(StoryArtifact(project_id=mine.id or 0, kind="brief", title="Brief", content="A tall tale."))
        await session.commit()

    run_async(seed())

    @asynccontextmanager
    async def scope() -> AsyncIterator[AsyncSession]:
        """Hand every MCP tool and AgentRun write the shared test session."""
        yield session

    monkeypatch.setattr("draftpilot.mcp.server.session_scope", scope)
    monkeypatch.setattr("draftpilot.agents.runtime.session_scope", scope)
    monkeypatch.setattr("draftpilot.core.events.get_redis", lambda: _NoRedis())
    monkeypatch.setattr("draftpilot.core.queue.pool.get_arq_pool", _no_pool)
    yield session
    run_async(context.__aexit__(None, None, None))


class _NoRedis:
    """Drop live-sync publishes in tests."""

    async def publish(self, *_args: object) -> None:
        """Ignore the event."""


async def _no_pool() -> Any:
    """Simulate an unavailable queue; enqueues are best-effort."""
    raise ConnectionError("no queue in tests")


def _run(model: FunctionModel, mode: str, prompt: str = "Help.") -> tuple[str, AgentRun, list[ModelMessage]]:
    """Run the story architect once and return the reply, AgentRun, and messages."""
    captured: list[list[ModelMessage]] = []
    original = runtime.build_room_agent

    def build(spec: Any, model_: Any, permission_mode: str, output_type: Any = str, **kwargs: Any) -> Any:
        """Build the real agent and capture its messages after the run."""
        agent = original(spec, model_, permission_mode, output_type, **kwargs)
        run = agent.run

        async def tracked(*args: Any, **kwargs: Any) -> Any:
            """Run the agent and keep its full message history."""
            result = await run(*args, **kwargs)
            captured.append(result.all_messages())
            return result

        agent.run = tracked  # type: ignore[method-assign]
        return agent

    runtime.build_room_agent = build  # type: ignore[assignment]
    try:
        reply, record = run_async(
            runtime.run_room_agent(
                role_spec("story_architect"),
                model,
                RoomDeps(project_id=1, permission_mode=mode),
                prompt,
                provider="test",
                model_name="scripted",
            )
        )
    finally:
        runtime.build_room_agent = original  # type: ignore[assignment]
    return reply, record, captured[0]


def test_every_role_spec_loads_with_real_instructions() -> None:
    """All seven room roles have validated specs."""
    specs = load_specs()
    assert set(specs) >= {
        "story_architect",
        "researcher",
        "character_specialist",
        "script_editor",
        "continuity_supervisor",
        "associate_director",
        "audience_evaluator",
    }
    assert all(len(spec.instructions) > 100 for spec in specs.values())


def test_permission_modes_widen_tools_from_read_to_propose_to_edit() -> None:
    """chat_only reads, suggest also proposes, project_edit may also request edits."""
    chat, suggest, edit = (runtime.tools_for_mode(mode) for mode in ("chat_only", "suggest", "project_edit"))
    assert "read_project_overview" in chat and "propose_screenplay_change" not in chat
    assert "propose_screenplay_change" in suggest and "apply_story_operation" not in suggest
    assert "apply_story_operation" in edit


def test_agent_reads_its_project_through_mcp_and_is_measured(room: AsyncSession) -> None:
    """The agent calls the real MCP tool as the internal client and the run is recorded."""
    model = _script({"tool": "read_project_overview", "args": {"project_id": 1}}, "The river scene anchors it.")
    reply, record, messages = _run(model, "chat_only")
    assert reply == "The river scene anchors it."
    overview = json.loads(_tool_returns(messages)[0])
    assert overview["drafts"][0]["scene_index"][0]["heading"] == "EXT. RIVER - DAY"
    assert overview["drafts"][0]["title_page"] == {"Author": "John August"}
    assert (record.role, record.status, record.tools_used) == ("story_architect", "succeeded", ["read_project_overview"])
    assert record.requests == 2 and record.trace_id is None or len(record.trace_id or "") == 32
    stored = run_async(room.exec(select(AgentRun))).all()
    assert len(stored) == 1


def test_agent_cannot_read_another_project(room: AsyncSession) -> None:
    """The internal client is scoped to its run's project even if the model asks for another."""
    model = _script({"tool": "read_project_overview", "args": {"project_id": 2}}, "I could not read it.")
    _reply, _record, messages = _run(model, "chat_only")
    returns = " ".join(_tool_returns(messages))
    assert "not granted" in returns
    assert "Someone else" not in returns


def test_chat_only_agents_cannot_even_see_proposal_tools(room: AsyncSession) -> None:
    """A tool outside the permission mode is unknown to the agent, not merely refused."""
    model = _script(
        {"tool": "propose_screenplay_change", "args": {"project_id": 1, "scene_id": 1, "operation": {}}},
        "Understood.",
    )
    _reply, _record, messages = _run(model, "chat_only")
    assert any("Unknown tool" in text or "not found" in text.casefold() for text in _tool_returns(messages))


def test_approval_required_writes_become_writer_requests(room: AsyncSession) -> None:
    """Even in project_edit mode, a story operation waits for the writer instead of applying."""
    model = _script(
        {
            "tool": "apply_story_operation",
            "args": {"project_id": 1, "artifact_id": 1, "operation": "set_logline", "payload": {"logline": "A tall tale."}},
        },
        "I asked the writer to approve the logline.",
    )
    _reply, _record, messages = _run(model, "project_edit")
    assert "approval request" in " ".join(_tool_returns(messages))
    requests = run_async(room.exec(select(MCPApprovalRequest))).all()
    assert [(item.client_id, item.status) for item in requests] == [("draftpilot-room", "pending")]
    artifact = run_async(room.get(StoryArtifact, 1))
    assert artifact is not None and artifact.artifact_metadata.get("logline") is None


def test_streamed_chat_speaks_the_vercel_protocol_and_records_the_turn(
    room: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /room/chat streams AI SDK v6 events, records an AgentRun, and saves the transcript."""
    from collections.abc import AsyncGenerator

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from draftpilot.api.room import router
    from draftpilot.core.config import settings
    from draftpilot.core.db import async_get_db
    from draftpilot.models import CopilotMessage

    @asynccontextmanager
    async def scope() -> AsyncIterator[AsyncSession]:
        """Hand the transcript writer the shared test session."""
        yield room

    async def dependency() -> AsyncGenerator[AsyncSession]:
        """Yield the shared test session to the route."""
        yield room

    async def model(_config: object) -> tuple[FunctionModel, str]:
        """Return a scripted model instead of reaching a provider."""
        return _script({"tool": "read_project_overview", "args": {"project_id": 1}}, "Open on the river."), "scripted"

    async def no_context(_project_id: int, _query: str) -> list[dict[str, object]]:
        """Skip retrieval."""
        return []

    monkeypatch.setattr("draftpilot.agents.chat.session_scope", scope)
    monkeypatch.setattr("draftpilot.api.room.build_chat_model", model)
    monkeypatch.setattr("draftpilot.api.room.retrieve_context", no_context)
    monkeypatch.setattr(settings.llm, "enabled", True)
    app = FastAPI()
    app.dependency_overrides[async_get_db] = dependency
    app.include_router(router, prefix="/api/v1")
    body = {"trigger": "submit-message", "id": "chat-1", "messages": [{"id": "m1", "role": "user", "parts": [{"type": "text", "text": "Where should we open?"}]}]}
    response = TestClient(app).post("/api/v1/projects/1/room/chat?role=story_architect", json=body)
    assert response.status_code == 200
    assert response.headers["x-vercel-ai-ui-message-stream"] == "v1"
    assert "Open on the river." in response.text and "[DONE]" in response.text
    assert "read_project_overview" in response.text
    runs = run_async(room.exec(select(AgentRun))).all()
    assert [(item.kind, item.status, item.tools_used) for item in runs] == [("chat", "succeeded", ["read_project_overview"])]
    turns = run_async(room.exec(select(CopilotMessage))).all()
    assert [(item.role, item.content) for item in turns] == [("user", "Where should we open?"), ("assistant", "Open on the river.")]


def test_showrunner_delegates_to_a_specialist_and_shares_the_budget(room: AsyncSession) -> None:
    """The showrunner consults a specialist; both runs are recorded and usage is shared."""

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        """Script the showrunner (who has `consult`) and the specialist (who does not)."""
        has_consult = any(tool.name == "consult" for tool in info.function_tools)
        consulted = any(isinstance(part, ToolReturnPart) and part.tool_name == "consult" for message in messages for part in getattr(message, "parts", []))
        if has_consult and not consulted:
            return ModelResponse(parts=[ToolCallPart(tool_name="consult", args={"role": "continuity_supervisor", "brief": "Check Edward's age across scenes."})])
        if has_consult:
            return ModelResponse(parts=[TextPart(content="Continuity says it holds; I agree.")])
        return ModelResponse(parts=[TextPart(content="No contradictions in Edward's age.")])

    async def stream(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[str]:
        """Streaming is unused here."""
        yield respond(messages, info).parts[0].content  # type: ignore[union-attr]

    reply, record = run_async(
        runtime.run_room_agent(
            role_spec("showrunner"),
            FunctionModel(respond, stream_function=stream),
            RoomDeps(project_id=1, permission_mode="chat_only"),
            "Is Edward's age consistent?",
            provider="test",
            model_name="scripted",
        )
    )
    assert reply == "Continuity says it holds; I agree."
    assert record.role == "showrunner" and record.tools_used == ["consult"]
    runs = run_async(room.exec(select(AgentRun).order_by(AgentRun.id))).all()
    delegate = next(run for run in runs if run.kind == "delegate")
    assert (delegate.role, delegate.status) == ("continuity_supervisor", "succeeded")
    assert record.requests >= 3  # two showrunner requests plus the specialist's, on one shared budget


def test_showrunner_is_told_to_retry_on_an_unknown_specialist(room: AsyncSession) -> None:
    """Asking for a role that does not exist sends a retry prompt, not a crash."""
    model = _script({"tool": "consult", "args": {"role": "producer", "brief": "Budget it."}}, "Fine, I'll answer myself.")
    captured: list[list[ModelMessage]] = []
    original = runtime.build_room_agent

    def build(spec: Any, model_: Any, permission_mode: str, output_type: Any = str, **kwargs: Any) -> Any:
        """Capture the showrunner's messages."""
        agent = original(spec, model_, permission_mode, output_type, **kwargs)
        run = agent.run

        async def tracked(*args: Any, **kwargs: Any) -> Any:
            """Run and capture messages."""
            result = await run(*args, **kwargs)
            captured.append(result.all_messages())
            return result

        agent.run = tracked  # type: ignore[method-assign]
        return agent

    runtime.build_room_agent = build  # type: ignore[assignment]
    try:
        reply, _record = run_async(
            runtime.run_room_agent(role_spec("showrunner"), model, RoomDeps(project_id=1), "Budget?", provider="test", model_name="scripted")
        )
    finally:
        runtime.build_room_agent = original  # type: ignore[assignment]
    assert reply == "Fine, I'll answer myself."
    assert "Unknown specialist 'producer'" in " ".join(_tool_returns(captured[0]))


def test_reasoning_follows_the_role_unless_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    """Evaluative roles answer without reasoning; ``LLM__THINKING`` forces it on or off for everyone."""
    critic, writer = role_spec("script_doctor"), role_spec("scene_writer")
    assert runtime.role_model_settings(writer).get("openai_reasoning_effort") is None
    off = runtime.role_model_settings(critic)
    assert off["thinking"] is False and off.get("openai_reasoning_effort") == "none" and off["max_tokens"] == critic.max_tokens
    monkeypatch.setattr(runtime.settings.llm, "thinking", "on")
    assert "thinking" not in runtime.role_model_settings(critic)
    monkeypatch.setattr(runtime.settings.llm, "thinking", "off")
    assert runtime.role_model_settings(writer)["thinking"] is False


def test_a_role_that_reasons_past_its_token_budget_answers_again_without_reasoning(room: AsyncSession) -> None:
    """A truncated, empty first response triggers one retry with reasoning off; both runs are recorded."""
    seen: list[object] = []

    def respond(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        """Run out of tokens while 'reasoning' the first time, then answer."""
        seen.append((info.model_settings or {}).get("openai_reasoning_effort"))
        if len(seen) == 1:
            return ModelResponse(parts=[], finish_reason="length")
        return ModelResponse(parts=[TextPart(content="Short answer.")])

    reply, record = run_async(
        runtime.run_role(role_spec("scene_writer"), FunctionModel(respond), RoomDeps(project_id=1, permission_mode="chat_only"),
                         "Draft it.", str, provider="test", model_name="scripted", tools=False)
    )
    assert reply == "Short answer." and record.status == "succeeded"
    assert seen == [None, "none"]
    runs = run_async(room.exec(select(AgentRun))).all()
    assert [run.status for run in runs] == ["failed", "succeeded"]
