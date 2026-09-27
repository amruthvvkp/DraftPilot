"""Test that agents read scenes as compact Fountain by default and as typed blocks on request."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from _async import run_async
from _db import memory_session
from fastmcp import Client
from fastmcp.exceptions import ToolError

from draftpilot.core.agent_identity import InternalAgent, acting_as
from draftpilot.core.screenplay.adapters.fountain import parse_fountain
from draftpilot.core.screenplay.hydrate import save_screenplay_doc
from draftpilot.models import Project, Screenplay

BIG_FISH = Path(__file__).parent / "test_screenplays" / "Big-Fish.fountain"


class _NoRedis:
    """Drop live-sync publishes."""

    async def publish(self, *_args: object) -> None:
        """Ignore the event."""


def test_scene_reads_default_to_compact_fountain(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fountain pages carry scene ids and numbers and are several times smaller than block pages."""
    from draftpilot.mcp import server

    async def scenario() -> None:
        """Import Big Fish and read the same page in both formats."""
        async with memory_session() as session:
            project = Project(title="Big Fish")
            session.add(project)
            await session.flush()
            screenplay = Screenplay(project_id=project.id or 0, title="Big Fish")
            session.add(screenplay)
            await session.commit()
            await save_screenplay_doc(session, screenplay.id or 0, parse_fountain(BIG_FISH.read_text()))

            @asynccontextmanager
            async def scope() -> AsyncIterator[object]:
                """Share the seeded session."""
                yield session

            monkeypatch.setattr(server, "session_scope", scope)
            monkeypatch.setattr("draftpilot.core.events.get_redis", lambda: _NoRedis())
            with acting_as(InternalAgent(project_id=1, role="script_editor")):
                async with Client(server.mcp) as client:
                    compact = (await client.call_tool("read_screenplay_scenes", {"project_id": 1, "screenplay_id": 1})).structured_content
                    blocks = (
                        await client.call_tool("read_screenplay_scenes", {"project_id": 1, "screenplay_id": 1, "format": "blocks"})
                    ).structured_content
                    with pytest.raises(ToolError):
                        await client.call_tool("read_screenplay_scenes", {"project_id": 1, "screenplay_id": 1, "format": "xml"})
            assert compact is not None and blocks is not None
            assert len(compact["scenes"]) == 10 and compact["total_scenes"] == 191
            second = compact["scenes"][1]
            assert second["number"] == 2 and second["fountain"].startswith("INT.  WILL'S BEDROOM")
            assert "block" not in json.dumps(compact) and "id" in blocks["scenes"][0]["blocks"][0]
            assert len(json.dumps(compact)) * 4 < len(json.dumps(blocks))

    run_async(scenario())
