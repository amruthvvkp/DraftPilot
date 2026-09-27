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
from draftpilot.core.rag import HashEmbedder, IndexedDocument, SQLiteHybridIndex
from draftpilot.core.rag_client import local_index
from draftpilot.core.rag_sources import project_documents
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
def big_fish(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[AsyncSession]:
    """Import Big Fish into a file-backed project and route MCP tools to it."""
    context = memory_session(f"sqlite+aiosqlite:///{tmp_path / 'room.db'}")
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
    index = SQLiteHybridIndex(tmp_path / "rag.sqlite3", HashEmbedder(64))

    async def build_index() -> None:
        """Index the project so retrieve_project_context works without the RAG service."""
        await index.ensure_schema()
        for document in await project_documents(session, 1):
            await index.upsert(IndexedDocument(project_id=1, **document))  # type: ignore[arg-type]

    run_async(build_index())
    run_async(session.close())  # release SQLite's lock so per-call sessions can write

    @asynccontextmanager
    async def scope() -> AsyncIterator[AsyncSession]:
        """Give each MCP tool call its own session, as production does, so parallel calls stay isolated."""
        async with AsyncSession(session.bind, expire_on_commit=False) as scoped:
            yield scoped

    monkeypatch.setattr("draftpilot.mcp.server.session_scope", scope)
    monkeypatch.setattr("draftpilot.agents.runtime.session_scope", scope)
    monkeypatch.setattr("draftpilot.agents.workflows.session_scope", scope)
    monkeypatch.setattr("draftpilot.core.events.get_redis", lambda: _NoRedis())
    monkeypatch.setattr("draftpilot.core.queue.pool.get_arq_pool", _no_pool)
    with local_index(index):
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


def test_showrunner_delegates_to_a_specialist(lmstudio: LMStudio, big_fish: AsyncSession) -> None:
    """The showrunner consults at least one specialist and synthesises their answer."""
    config = LLMSettings(provider="lm_studio", base_url=lmstudio.base_url, model=settings.eval.chat_model or "auto")

    async def scenario() -> tuple[str, Any]:
        """Ask the showrunner for a character read that needs a specialist."""
        model, name = await build_chat_model(config)
        return await run_room_agent(
            role_spec("showrunner"),
            model,
            RoomDeps(project_id=1, permission_mode="chat_only"),
            "Consult the character specialist: in two sentences, what does Will want from his father "
            "Edward in this script? Then give me your one-line synthesis.",
            provider="lm_studio",
            model_name=name,
        )

    reply, record = run_async(scenario())
    print(f"\n[showrunner] tools={record.tools_used} {record.duration_ms}ms reply={reply!r}")
    assert record.status == "succeeded"
    assert "consult" in record.tools_used
    assert "EDWARD" in reply.upper() or "FATHER" in reply.upper()


def test_rewrite_workflow_proposes_a_valid_scene_on_big_fish(lmstudio: LMStudio, big_fish: AsyncSession) -> None:
    """The scene writer and script doctor loop on a real scene and end in a parseable, reviewable proposal."""
    from draftpilot.agents.workflows import WorkflowDeps, run_room_workflow
    from draftpilot.core.scene_proposals import parse_scene_fountain

    config = LLMSettings(provider="lm_studio", base_url=lmstudio.base_url, model=settings.eval.chat_model or "auto")

    async def scenario() -> dict[str, Any]:
        """Rewrite scene 2 (Will's bedroom) with one revision round at most."""
        model, name = await build_chat_model(config)
        deps = WorkflowDeps(model, "lm_studio", name, RoomDeps(project_id=1, permission_mode="chat_only"))
        return await run_room_workflow(
            "rewrite_scene",
            {"scene_id": 2, "brief": "Make it shorter and let Will's resentment show through subtext.", "max_rounds": 1},
            deps,
        )

    result = run_async(scenario())
    print(f"\n[rewrite] trail={[(s['step'], s['duration_ms']) for s in result['trail']]} "
          f"critique={result['critique']} fountain={result['fountain'][:600]!r}")
    assert result["proposal_ids"] and parse_scene_fountain(result["fountain"]).blocks
    assert result["trail"][0]["role"] == "scene_writer" and result["trail"][1]["role"] == "script_doctor"
