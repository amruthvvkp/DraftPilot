"""Identity of DraftPilot's in-app agents when they call the MCP server in-process.

In-app agents use the same MCP server as external clients (Claude Code, Codex). While a tool
call runs, this context identifies it as the internal client bound to exactly one project: it
holds implicit grants for that project only, and approval-required capabilities still produce
writer approval requests — the room can never approve its own writes.

Durable agents share one MCP session per process, so the identity cannot ride on the caller's
context. Every in-app tool call instead carries it in the request ``_meta``, signed with a key
that never leaves the process (in-app tool calls reach the in-memory server of the process that
made them). The server verifies the signature and binds the identity for that call only; an
external client cannot forge it.
"""

import hashlib
import hmac
import json
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from draftpilot.core.config import settings


@dataclass(frozen=True)
class InternalAgent:
    """Describe the in-app agent run currently calling MCP tools."""

    project_id: int
    role: str
    run_id: int | None = None
    # An approval probe only authorizes: it records the writer-approval request a write needs and
    # never runs the tool. Chat uses it to turn the writer's in-chat approval into an approval_id.
    probe: bool = False

    @property
    def client_id(self) -> str:
        """Return the MCP client identity used for authorization and audit."""
        return settings.mcp.internal_client_id


_current: ContextVar[InternalAgent | None] = ContextVar("draftpilot_internal_agent", default=None)


def current_internal_agent() -> InternalAgent | None:
    """Return the in-app agent bound to the current task, if any."""
    return _current.get()


@contextmanager
def acting_as(agent: InternalAgent | None) -> Iterator[InternalAgent | None]:
    """Bind an in-app agent identity (or explicitly none) for the duration of one tool call."""
    token = _current.set(agent)
    try:
        yield agent
    finally:
        _current.reset(token)


META_KEY = "draftpilot/internal-agent"
_SIGNING_KEY = secrets.token_bytes(32)


def _signature(claims: str) -> str:
    """Return the process-local HMAC of serialized identity claims."""
    return hmac.new(_SIGNING_KEY, claims.encode(), hashlib.sha256).hexdigest()


def identity_meta(agent: InternalAgent) -> dict[str, Any]:
    """Return the signed request ``_meta`` that identifies an in-app agent's tool call."""
    claims = json.dumps(
        {"project_id": agent.project_id, "role": agent.role, "run_id": agent.run_id, "probe": agent.probe}, sort_keys=True
    )
    return {META_KEY: {"claims": claims, "signature": _signature(claims)}}


def agent_from_meta(meta: Any) -> InternalAgent | None:
    """Return the in-app agent a request ``_meta`` names, or ``None`` if absent or not signed by this process."""
    stamp = meta.get(META_KEY) if isinstance(meta, dict) else None
    if not isinstance(stamp, dict):
        return None
    claims, signature = stamp.get("claims"), stamp.get("signature")
    if not isinstance(claims, str) or not isinstance(signature, str) or not hmac.compare_digest(signature, _signature(claims)):
        return None
    data = json.loads(claims)
    return InternalAgent(
        project_id=int(data["project_id"]), role=str(data["role"]), run_id=data.get("run_id"), probe=bool(data.get("probe"))
    )
