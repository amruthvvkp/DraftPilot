"""Identity of DraftPilot's in-app agents when they call the MCP server in-process.

In-app agents use the same MCP server as external clients (Claude Code, Codex). While an
agent run is active, this context identifies it as the internal client bound to exactly one
project: it holds implicit grants for that project only, and approval-required capabilities
still produce writer approval requests — the room can never approve its own writes.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from draftpilot.core.config import settings


@dataclass(frozen=True)
class InternalAgent:
    """Describe the in-app agent run currently calling MCP tools."""

    project_id: int
    role: str
    run_id: int | None = None

    @property
    def client_id(self) -> str:
        """Return the MCP client identity used for authorization and audit."""
        return settings.mcp.internal_client_id


_current: ContextVar[InternalAgent | None] = ContextVar("draftpilot_internal_agent", default=None)


def current_internal_agent() -> InternalAgent | None:
    """Return the in-app agent bound to the current task, if any."""
    return _current.get()


@contextmanager
def acting_as(agent: InternalAgent) -> Iterator[InternalAgent]:
    """Bind an in-app agent identity for the duration of one agent run."""
    token = _current.set(agent)
    try:
        yield agent
    finally:
        _current.reset(token)
