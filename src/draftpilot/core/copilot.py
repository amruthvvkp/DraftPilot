"""Provider-backed Copilot response generation."""

import httpx
import logfire
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

from draftpilot.agents.context import load_room_context
from draftpilot.agents.deps import RoomDeps
from draftpilot.agents.runtime import run_room_agent
from draftpilot.agents.specs import role_spec
from draftpilot.core import rag_client
from draftpilot.core.agent_roles import AgentRoleKey
from draftpilot.core.config import LLMSettings, settings
from draftpilot.core.db import session_scope
from draftpilot.core.providers import build_chat_model


async def retrieve_context(project_id: int, query: str) -> list[dict[str, object]]:
    """Retrieve bounded project context without making RAG availability a chat prerequisite."""
    if not query.strip():
        return []
    try:
        payload = await rag_client.search(project_id, query[:2_000], settings.rag.max_results, timeout=3.0)
        results = payload.get("results", [])
        if not isinstance(results, list):
            return []
        return [item for item in results[: settings.rag.max_results] if isinstance(item, dict)]
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        logfire.warning("Copilot retrieval skipped: {exc}", exc=str(exc))
        return []


def history_messages(history: list[dict[str, str]], current: str) -> list[ModelMessage]:
    """Convert stored Copilot turns into model messages, dropping the current prompt."""
    turns = list(history[-13:])
    if turns and turns[-1].get("role") == "user" and turns[-1].get("content") == current:
        turns.pop()
    messages: list[ModelMessage] = []
    for turn in turns[-12:]:
        text = str(turn.get("content", ""))
        if turn.get("role") == "assistant":
            messages.append(ModelResponse(parts=[TextPart(content=text)]))
        elif turn.get("role") == "user":
            messages.append(ModelRequest(parts=[UserPromptPart(content=text)]))
    return messages


async def generate_reply(
    content: str,
    page: str,
    artifact: str | None,
    selection: str | None,
    agent_role: AgentRoleKey,
    history: list[dict[str, str]],
    llm_settings: LLMSettings | None = None,
    retrieved_context: list[dict[str, object]] | None = None,
    *,
    project_id: int,
    permission_mode: str = "chat_only",
    kind: str = "chat",
    workflow_run_id: int | None = None,
) -> str:
    """Generate one context-scoped reply from a room agent working through DraftPilot's MCP tools."""
    config = llm_settings or settings.llm
    if not config.enabled:
        raise RuntimeError("LLM provider is disabled")
    model, model_name = await build_chat_model(config)
    async with session_scope() as session:
        context = await load_room_context(session, project_id)
    deps = RoomDeps(
        project_id=project_id,
        page=page,
        artifact=artifact,
        selection=selection,
        permission_mode=permission_mode,
        project_instruction=context.project_instruction,
        writer_brief=context.writer_brief,
        story_brief=context.story_brief,
        retrieved_context=retrieved_context or [],
    )
    reply, _record = await run_room_agent(
        role_spec(agent_role),
        model,
        deps,
        content,
        provider=config.provider,
        model_name=model_name,
        kind=kind,
        history=history_messages(history, content),
        workflow_run_id=workflow_run_id,
    )
    return reply
