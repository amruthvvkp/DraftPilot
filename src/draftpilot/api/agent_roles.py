"""Built-in agent role discovery endpoint."""

from fastapi import APIRouter

from draftpilot.core.agent_roles import AgentRole, agent_roles

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("/roles", response_model=list[AgentRole])
def list_agent_roles() -> list[AgentRole]:
    """Return the supported built-in agent roles and defaults."""
    return agent_roles()
