"""Stream a room agent's reply to the studio over the Vercel AI SDK UI-message protocol."""

from typing import Any

import logfire
from fastapi import Request
from fastapi.responses import StreamingResponse
from pydantic_ai.messages import ModelRequest, UserPromptPart
from pydantic_ai.run import AgentRunResult
from pydantic_ai.ui.vercel_ai import VercelAIAdapter

from draftpilot.agents.deps import RoomDeps
from draftpilot.agents.runtime import (
    RunMeter,
    build_room_agent,
    measured_run,
    usage_limits,
)
from draftpilot.agents.specs import RoleSpec
from draftpilot.core.db import session_scope
from draftpilot.crud import copilot_messages as messages_crud
from draftpilot.models import CopilotMessageCreate


def last_user_text(messages: list[Any]) -> str:
    """Return the text of the writer's latest message in a UI conversation."""
    for message in reversed(messages):
        if isinstance(message, ModelRequest):
            for part in reversed(message.parts):
                if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                    return part.content
    return ""


async def stream_room_chat(
    request: Request,
    *,
    spec: RoleSpec,
    model: Any,
    deps_without_context: RoomDeps,
    provider: str,
    model_name: str,
    retrieve: Any,
) -> StreamingResponse:
    """Run one streamed chat turn as the internal agent and record its AgentRun and transcript."""
    agent = build_room_agent(spec, model, deps_without_context.permission_mode)
    adapter = await VercelAIAdapter.from_request(request, agent=agent, sdk_version=6)
    prompt = last_user_text(adapter.messages)
    context = await retrieve(deps_without_context.project_id, prompt) if prompt else []
    deps = RoomDeps(**{**deps_without_context.__dict__, "retrieved_context": context})
    meter = RunMeter(deps.project_id, spec.key, "chat", provider, model_name)

    async def on_complete(result: AgentRunResult[Any]) -> None:
        """Record the measured run and keep the conversation in the project transcript."""
        record = await meter.finish(result)
        async with session_scope() as session:
            for role, content in (("user", prompt), ("assistant", str(result.output))):
                await messages_crud.create(
                    session,
                    CopilotMessageCreate(
                        project_id=deps.project_id,
                        role=role,
                        content=content,
                        page=deps.page or "studio",
                        artifact=deps.artifact,
                        selection=deps.selection,
                        instruction_layers={"agent_role": spec.key, "permission_mode": deps.permission_mode, "agent_run_id": record.id},
                        citations=[item["citation"] for item in context if isinstance(item.get("citation"), dict)],
                    ),
                )

    async def events() -> Any:
        """Stream protocol events while bound to the internal agent identity."""
        async with measured_run(meter):
            try:
                async for event in adapter.run_stream(deps=deps, usage_limits=usage_limits(spec), on_complete=on_complete):
                    yield event
            except Exception as exc:
                logfire.warning("Room chat failed: {exc}", exc=str(exc))
                await meter.finish(None, exc)
                raise

    return adapter.streaming_response(events())
