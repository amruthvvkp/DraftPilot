"""Tier 1: a real local LM Studio model works the room through DraftPilot's MCP tools on Big Fish."""

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from _async import run_async
from _db import memory_session
from _lmstudio import LMStudio
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.agents.deps import RoomDeps
from draftpilot.agents.runtime import run_room_agent
from draftpilot.agents.specs import role_spec
from draftpilot.core.config import LLMSettings, settings
from draftpilot.core.providers import build_chat_model
from draftpilot.core.screenplay.adapters.fountain import parse_fountain
from draftpilot.core.screenplay.hydrate import save_screenplay_doc
from draftpilot.models import Project, Screenplay

pytestmark = pytest.mark.lmstudio
BIG_FISH = Path(__file__).parents[1] / "test_screenplays" / "Big-Fish.fountain"


class _NoRedis:
    """Drop live-sync publishes."""

    async def publish(self, *_args: object) -> None:
        """Ignore the event."""


async def _no_pool() -> Any:
    """Simulate an unavailable queue."""
    raise ConnectionError("no queue in tests")


@pytest.fixture
def big_fish(monkeypatch: pytest.MonkeyPatch) -> Iterator[AsyncSession]:
    """Import Big Fish into an in-memory project and route MCP tools to it."""
    context = memory_session()
    session = run_async(context.__aenter__())

    async def seed() -> None:
        """Create the project and import the full Fountain screenplay."""
        project = Project(title="Big Fish", logline="A son pieces together his father's tall tales.")
        session.add(project)
        await session.flush()
        screenplay = Screenplay(project_id=project.id or 0, title="Big Fish")
        session.add(screenplay)
        await session.commit()
        await save_screenplay_doc(session, screenplay.id or 0, parse_fountain(BIG_FISH.read_text()))

    run_async(seed())

    @asynccontextmanager
    async def scope() -> AsyncIterator[AsyncSession]:
        """Hand MCP tools and AgentRun writes the shared session."""
        yield session

    monkeypatch.setattr("draftpilot.mcp.server.session_scope", scope)
    monkeypatch.setattr("draftpilot.agents.runtime.session_scope", scope)
    monkeypatch.setattr("draftpilot.core.events.get_redis", lambda: _NoRedis())
    monkeypatch.setattr("draftpilot.core.queue.pool.get_arq_pool", _no_pool)
    yield session
    run_async(context.__aexit__(None, None, None))


def test_room_agent_reads_big_fish_through_mcp(lmstudio: LMStudio, big_fish: AsyncSession) -> None:
    """A local model uses the MCP tools to answer a question only the script can answer."""
    config = LLMSettings(provider="lm_studio", base_url=lmstudio.base_url, model=settings.eval.chat_model or "auto")

    async def scenario() -> tuple[str, Any, str]:
        """Resolve the loaded model and ask the script editor about scene 2."""
        model, name = await build_chat_model(config)
        reply, record = await run_room_agent(
            role_spec("script_editor"),
            model,
            RoomDeps(project_id=1, permission_mode="chat_only"),
            "What is the exact scene heading of the second scene in the screenplay? "
            "Look it up with the tools, then answer with the heading only.",
            provider="lm_studio",
            model_name=name,
        )
        return reply, record, name

    reply, record, name = run_async(scenario())
    print(f"\n[{name}] tools={record.tools_used} tokens={record.input_tokens}/{record.output_tokens} "
          f"{record.duration_ms}ms reply={reply!r}")
    assert record.status == "succeeded"
    assert any(tool in record.tools_used for tool in ("read_project_overview", "read_screenplay_scenes"))
    assert "WILL'S BEDROOM" in reply.upper()
