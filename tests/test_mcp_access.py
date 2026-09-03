"""Test durable MCP invocation authorization and audit redaction."""

import asyncio

import pytest

from draftpilot.crud import mcp_access
from draftpilot.models import MCPAuditEvent, MCPGrant


class _Session:
    """Capture persisted audit records for an isolated CRUD test."""

    def __init__(self) -> None:
        self.events: list[MCPAuditEvent] = []

    def add(self, value: object) -> None:
        """Capture a model added to the session."""
        if isinstance(value, MCPAuditEvent):
            self.events.append(value)

    async def commit(self) -> None:
        """Complete the isolated transaction."""


def test_denied_invocation_is_audited_without_sensitive_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Audit a denied project-scoped invocation with redacted payload."""
    async def run() -> None:
        """Exercise the asynchronous authorization helper."""
        session = _Session()
        async def grants(_session: object, _project: int, _client: str) -> list[MCPGrant]:
            """Return no grants for the isolated client."""
            return []
        monkeypatch.setattr(mcp_access, "list_grants", grants)
        with pytest.raises(PermissionError, match="not granted"):
            await mcp_access.authorize_invocation(
                session, "claude", 4, "timeline.propose", "propose", {"text": "secret"}
            )
        assert session.events[0].allowed is False
        assert session.events[0].payload["text"] == "[REDACTED]"
    asyncio.run(run())
