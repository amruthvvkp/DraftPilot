"""Stream a room agent's reply to the studio over the AG-UI protocol, with in-chat writer approvals.

Each chat turn is a short durable workflow (``room:chat`` in ``agents/room_workflows.py``) run by
the worker. The web process parses the AG-UI ``RunAgentInput``, starts the workflow and relays the
run's events from its Workflow Stream through Pydantic AI's AG-UI encoder.

When the agent calls a write tool, its turn ends with an AG-UI interrupt asking the writer to
approve that exact call. The writer's answer arrives with the next turn as AG-UI ``resume``
entries. For each approved call, an approval probe asks the MCP server to record the writer
approval the call needs (bound to its exact arguments), the writer's decision is recorded on it,
and the call resumes with that ``approval_id``. Denied calls go back to the agent as denials.

The thread (``threadId``) keeps the full Pydantic AI history server-side, so a reopened studio
can show the conversation again.
"""

import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any

import logfire
from fastapi import Request
from fastapi.responses import StreamingResponse
from fastmcp import Client
from fastmcp.exceptions import ToolError
from pydantic_ai import DeferredToolResults, ToolApproved, ToolDenied
from pydantic_ai.durable_exec.temporal import stream_agent_events
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.tools import DeferredToolRequests
from pydantic_ai.ui import NativeEvent
from pydantic_ai.ui.ag_ui import AGUIAdapter
from temporalio import activity

from draftpilot.agents.deps import RoomDeps
from draftpilot.agents.runtime import (
    APPROVAL_TOOLS,
    CHAT_TOPIC,
    chat_agents,
    failure_text,
    save_agent_run,
)
from draftpilot.agents.specs import RoleSpec
from draftpilot.core import temporal
from draftpilot.core.agent_identity import InternalAgent, identity_meta
from draftpilot.core.config import settings
from draftpilot.core.db import session_scope
from draftpilot.crud import copilot_messages as messages_crud
from draftpilot.crud.mcp_access import decide_approval
from draftpilot.models import AgentRun, ChatThread, CopilotMessageCreate

CHAT_WORKFLOW = "room:chat"
CHAT_TIMEOUT = timedelta(hours=1)
_PENDING = re.compile(r"approval request (\d+) is pending")


@dataclass
class ChatTurn:
    """One chat turn for the workflow: the role, the writer's message, the conversation, and the room context."""

    role: str
    prompt: str
    history: list[ModelMessage]
    deps: RoomDeps
    citations: list[dict[str, Any]] = field(default_factory=list)
    thread_id: str | None = None
    # The writer's answers to the previous turn's approval requests (AG-UI resume).
    deferred: DeferredToolResults | None = None
    # Tools the studio itself runs (navigate, open a scene): name, description, JSON-schema parameters.
    frontend_tools: list[dict[str, Any]] = field(default_factory=list)


def last_user_text(messages: list[Any]) -> str:
    """Return the text of the writer's latest message in a conversation."""
    for message in reversed(messages):
        if isinstance(message, ModelRequest):
            for part in reversed(message.parts):
                if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                    return part.content
    return ""


def reply_text(output: Any) -> str:
    """Return what the assistant said this turn, or what it is waiting on."""
    if isinstance(output, DeferredToolRequests):
        names = ", ".join(call.tool_name for call in [*output.approvals, *output.calls])
        return f"(waiting for you: {names})"
    return str(output)


@activity.defn(name="room_save_chat_turn")
async def save_chat_turn(turn: ChatTurn, reply: str, run_fields: dict[str, Any]) -> int:
    """Record the turn's AgentRun and keep both messages in the project transcript; return the run id."""
    record = await save_agent_run(AgentRun.model_validate(run_fields))
    deps = turn.deps
    async with session_scope() as session:
        for role, content in (("user", turn.prompt), ("assistant", reply)):
            if not content:
                continue
            await messages_crud.create(
                session,
                CopilotMessageCreate(
                    project_id=deps.project_id,
                    role=role,
                    content=content,
                    page=deps.page or "studio",
                    artifact=deps.artifact,
                    selection=deps.selection,
                    instruction_layers={"agent_role": turn.role, "permission_mode": deps.permission_mode, "agent_run_id": record.id},
                    citations=turn.citations,
                ),
            )
    return record.id or 0


@activity.defn(name="room_save_chat_thread")
async def save_chat_thread(thread_id: str, project_id: int, role: str, title: str, messages: list[ModelMessage]) -> None:
    """Keep a thread's full history so the studio can reopen it."""
    payload = ModelMessagesTypeAdapter.dump_python(messages, mode="json")
    async with session_scope() as session:
        thread = await session.get(ChatThread, thread_id)
        if thread is None:
            thread = ChatThread(id=thread_id, project_id=project_id, role=role, title=(title.strip() or "New conversation")[:200])
        elif thread.project_id != project_id:
            return  # a thread id belongs to one project; never let another project overwrite it
        thread.messages = payload
        thread.role = role
        thread.updated_at = datetime.now(UTC)
        session.add(thread)
        await session.commit()


CHAT_ACTIVITIES: list[Callable[..., Any]] = [save_chat_turn, save_chat_thread]


def _tool_calls(messages: list[ModelMessage]) -> dict[str, ToolCallPart]:
    """Index the conversation's tool calls by id."""
    return {
        part.tool_call_id: part
        for message in messages
        if isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, ToolCallPart)
    }


async def approve_in_chat(
    project_id: int, role: str, messages: list[ModelMessage], results: DeferredToolResults | None
) -> DeferredToolResults | None:
    """Turn the writer's in-chat approvals into MCP approvals bound to each call's exact arguments.

    An approved call is probed on the MCP server (which records the approval request the call needs
    without running it), the writer's decision is recorded, and the call resumes with that id.
    Anything that cannot be approved this way (unknown call, a tool that needs no approval) is denied.
    """
    if results is None or not results.approvals:
        return results
    from draftpilot.mcp.server import mcp

    calls = _tool_calls(messages)
    approvals: dict[str, Any] = {}
    meta = identity_meta(InternalAgent(project_id=project_id, role=role, probe=True))
    async with Client(mcp) as client:
        for call_id, decision in results.approvals.items():
            call = calls.get(call_id)
            approved = decision is True or isinstance(decision, ToolApproved)
            if not approved or call is None or call.tool_name not in APPROVAL_TOOLS:
                approvals[call_id] = decision if not approved else ToolDenied("This call could not be approved.")
                continue
            args = (decision.override_args if isinstance(decision, ToolApproved) and decision.override_args else None) or call.args_as_dict()
            args = {key: value for key, value in args.items() if key != "approval_id"}
            try:
                await client.call_tool(call.tool_name, args, meta=meta)
            except ToolError as exc:
                match = _PENDING.search(str(exc))
                if match is None:
                    approvals[call_id] = ToolDenied(f"Not approved: {exc}")
                    continue
                approval_id = int(match.group(1))
                async with session_scope() as session:
                    await decide_approval(session, project_id, approval_id, True)
                approvals[call_id] = ToolApproved(override_args={**args, "approval_id": approval_id})
                continue
            approvals[call_id] = ToolDenied("This call needs no approval; call it again.")
    return DeferredToolResults(calls=results.calls, approvals=approvals, metadata=results.metadata)


async def stream_room_chat(
    request: Request,
    *,
    spec: RoleSpec,
    model_ref: str,
    deps_without_context: RoomDeps,
    retrieve: Callable[[int, str], Awaitable[list[dict[str, Any]]]],
    adapter: AGUIAdapter[RoomDeps, Any] | None = None,
) -> StreamingResponse:
    """Start one chat turn on Temporal and stream its events back as AG-UI events."""
    adapter = adapter or await AGUIAdapter.from_request(request, agent=chat_agents()[spec.key])
    prompt = last_user_text(adapter.messages)
    resuming = bool(adapter.deferred_tool_results)
    context = await retrieve(deps_without_context.project_id, prompt) if prompt and not resuming else []
    deps = replace(deps_without_context, retrieved_context=context, model_ref=model_ref)
    deferred = await approve_in_chat(deps.project_id, spec.key, adapter.messages, adapter.deferred_tool_results)
    frontend_tools = [
        {"name": tool.name, "description": tool.description, "parameters_json_schema": tool.parameters}
        for tool in adapter.run_input.tools or []
    ]
    turn = ChatTurn(
        role=spec.key,
        prompt="" if resuming else prompt,
        history=adapter.sanitize_messages(adapter.messages, deferred_tool_results=deferred),
        deps=deps,
        citations=[item["citation"] for item in context if isinstance(item.get("citation"), dict)],
        thread_id=adapter.conversation_id,
        deferred=deferred,
        frontend_tools=frontend_tools,
    )
    client = await temporal.get_client()
    handle = await client.start_workflow(
        CHAT_WORKFLOW,
        turn,
        id=f"chat-{deps.project_id}-{uuid.uuid4().hex}",
        task_queue=settings.temporal.task_queue,
        execution_timeout=CHAT_TIMEOUT,
    )

    async def events() -> AsyncIterator[NativeEvent]:
        """Relay the turn's events, then wait for the turn to be recorded; a failed run raises its failure."""
        stream = stream_agent_events(client, handle, CHAT_TOPIC, output_type=str | DeferredToolRequests)  # type: ignore[arg-type]
        async with stream:
            async for event in stream:
                yield event
        try:
            # The transcript, thread and AgentRun are saved after the run; finish only once they are.
            await handle.result()
        except Exception as exc:
            logfire.warning("Room chat failed: {exc}", exc=failure_text(exc))
            raise RuntimeError(failure_text(exc)) from exc

    return adapter.streaming_response(adapter.transform_stream(events()))


def dump_thread(thread: ChatThread) -> list[dict[str, Any]]:
    """Return a stored thread as AG-UI messages for the studio to render."""
    messages = ModelMessagesTypeAdapter.validate_python(thread.messages)
    return [message.model_dump(mode="json", by_alias=True, exclude_none=True) for message in AGUIAdapter.dump_messages(messages)]
