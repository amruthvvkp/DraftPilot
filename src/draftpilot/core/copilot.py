"""Provider-backed Copilot response generation."""

import json

import httpx
import logfire
from pydantic_ai import Agent

from draftpilot.core.agent_roles import AgentRoleKey
from draftpilot.core.config import LLMSettings, settings
from draftpilot.core.providers import create_chat_model


async def retrieve_context(project_id: int, query: str) -> list[dict[str, object]]:
    """Retrieve bounded project context without making RAG availability a chat prerequisite."""
    if not query.strip():
        return []
    url = f"{settings.rag.service_url.rstrip('/')}/projects/{project_id}/search"
    headers = {"Authorization": f"Bearer {settings.rag.auth_token.get_secret_value()}"}
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.post(
                url,
                json={"query": query[:2_000], "limit": settings.rag.max_results},
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
        results = payload.get("results", []) if isinstance(payload, dict) else []
        if not isinstance(results, list):
            return []
        return [item for item in results[: settings.rag.max_results] if isinstance(item, dict)]
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        logfire.warning("Copilot retrieval skipped: {exc}", exc=str(exc))
        return []


async def generate_reply(
    content: str,
    page: str,
    artifact: str | None,
    selection: str | None,
    agent_role: AgentRoleKey,
    history: list[dict[str, str]],
    llm_settings: LLMSettings | None = None,
    retrieved_context: list[dict[str, object]] | None = None,
) -> str:
    """Generate one context-scoped Copilot reply through the configured provider."""
    config = llm_settings or settings.llm
    if not config.enabled:
        raise RuntimeError("LLM provider is disabled")
    model = create_chat_model(config)
    agent = Agent(
        model,
        system_prompt=(
            f"You are the {agent_role.replace('_', ' ')} for DraftPilot. "
            "Answer the writer directly, preserve the source screenplay language, "
            "and describe proposed changes without applying them."
        ),
    )
    prompt = json.dumps(
        {
            "page": page,
            "artifact": artifact,
            "selection": selection,
            "history": history[-12:],
            "retrieved_context": retrieved_context or [],
            "instruction": content,
        },
        ensure_ascii=False,
    )
    result = await agent.run(prompt)
    return str(result.output)
