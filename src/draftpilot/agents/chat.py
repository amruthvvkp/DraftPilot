"""Stream a room agent's reply to the studio over the Vercel AI SDK UI-message protocol.

Each chat turn is a short durable workflow (``room:chat`` in ``agents/room_workflows.py``) run by
the worker. The web process starts it and relays the run's events from its Workflow Stream
through the Vercel adapter's encoder, so the studio's ``useChat`` stream is unchanged. Each turn
gets its own workflow, not one long workflow per thread, because ``useChat`` resends the
conversation every turn and the transcript table already keeps it.
"""

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import timedelta
from typing import Any

import logfire
from fastapi import Request
from fastapi.responses import StreamingResponse
from pydantic_ai.durable_exec.temporal import stream_agent_events
from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart
from pydantic_ai.ui import NativeEvent
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from temporalio import activity

from draftpilot.agents.deps import RoomDeps
from draftpilot.agents.runtime import (
    CHAT_TOPIC,
    chat_agents,
    failure_text,
    save_agent_run,
)
from draftpilot.agents.specs import RoleSpec
from draftpilot.core import temporal
from draftpilot.core.config import settings
from draftpilot.core.db import session_scope
from draftpilot.crud import copilot_messages as messages_crud
from draftpilot.models import AgentRun, CopilotMessageCreate

CHAT_WORKFLOW = "room:chat"
CHAT_TIMEOUT = timedelta(hours=1)


@dataclass
class ChatTurn:
    """One chat turn for the workflow: the role, the writer's message, the conversation, and the room context."""

    role: str
    prompt: str
    history: list[ModelMessage]
    deps: RoomDeps
    citations: list[dict[str, Any]] = field(default_factory=list)


def last_user_text(messages: list[Any]) -> str:
    """Return the text of the writer's latest message in a UI conversation."""
    for message in reversed(messages):
        if isinstance(message, ModelRequest):
            for part in reversed(message.parts):
                if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                    return part.content
    return ""


@activity.defn(name="room_save_chat_turn")
async def save_chat_turn(turn: ChatTurn, reply: str, run_fields: dict[str, Any]) -> int:
    """Record the turn's AgentRun and keep both messages in the project transcript; return the run id."""
    record = await save_agent_run(AgentRun.model_validate(run_fields))
    deps = turn.deps
    async with session_scope() as session:
        for role, content in (("user", turn.prompt), ("assistant", reply)):
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


CHAT_ACTIVITIES: list[Callable[..., Any]] = [save_chat_turn]


async def stream_room_chat(
    request: Request,
    *,
    spec: RoleSpec,
    model_ref: str,
    deps_without_context: RoomDeps,
    retrieve: Callable[[int, str], Awaitable[list[dict[str, Any]]]],
) -> StreamingResponse:
    """Start one chat turn on Temporal and stream its events back as AI SDK v6 UI messages."""
    adapter = await VercelAIAdapter.from_request(request, agent=chat_agents()[spec.key], sdk_version=6)
    prompt = last_user_text(adapter.messages)
    context = await retrieve(deps_without_context.project_id, prompt) if prompt else []
    deps = replace(deps_without_context, retrieved_context=context, model_ref=model_ref)
    turn = ChatTurn(
        role=spec.key,
        prompt=prompt,
        history=adapter.sanitize_messages(adapter.messages, deferred_tool_results=adapter.deferred_tool_results),
        deps=deps,
        citations=[item["citation"] for item in context if isinstance(item.get("citation"), dict)],
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
        stream = stream_agent_events(client, handle, CHAT_TOPIC, output_type=str)
        async with stream:
            async for event in stream:
                yield event
        try:
            # The transcript and AgentRun are saved after the run; finish the stream only once they are.
            await handle.result()
        except Exception as exc:
            logfire.warning("Room chat failed: {exc}", exc=failure_text(exc))
            raise RuntimeError(failure_text(exc)) from exc

    return adapter.streaming_response(adapter.transform_stream(events()))
