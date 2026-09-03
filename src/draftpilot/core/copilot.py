"""Provider-backed Copilot response generation."""

import json

from pydantic_ai import Agent

from draftpilot.core.agent_roles import AgentRoleKey
from draftpilot.core.config import settings
from draftpilot.core.providers import create_chat_model


async def generate_reply(
    content: str,
    page: str,
    artifact: str | None,
    selection: str | None,
    agent_role: AgentRoleKey,
    history: list[dict[str, str]],
) -> str:
    """Generate one context-scoped Copilot reply through the configured provider."""
    if not settings.llm.enabled:
        raise RuntimeError("LLM provider is disabled")
    model = create_chat_model(settings.llm)
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
            "instruction": content,
        },
        ensure_ascii=False,
    )
    result = await agent.run(prompt)
    return str(result.output)
