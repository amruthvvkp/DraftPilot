"""Test deleting (backup first), recovering, and duplicating whole projects against a real database."""

from collections.abc import AsyncGenerator, Iterator
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from _async import run_async
from _db import memory_session
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.api.backups import router as backups_router
from draftpilot.api.lifecycle import router as lifecycle_router
from draftpilot.core.db import async_get_db
from draftpilot.core.project_lifecycle import project_tables
from draftpilot.core.screenplay.adapters.fountain import parse_fountain
from draftpilot.core.screenplay.hydrate import save_screenplay_doc
from draftpilot.core.twins import refresh_story_twin
from draftpilot.models import (
    AgentFeedback,
    AgentProposal,
    AgentRun,
    Block,
    DialogueTranslation,
    MCPApprovalRequest,
    Project,
    Scene,
    SceneRevision,
    Screenplay,
    StoryArtifact,
    WorkflowRun,
    WriterMemory,
)

BIG_FISH = Path(__file__).parent / "test_screenplays" / "Big-Fish.fountain"


@pytest.fixture
def studio(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[tuple[TestClient, AsyncSession, AsyncMock]]:
    """Seed a fully used Big Fish project and a neighbour, and serve the lifecycle and backup routes."""
    monkeypatch.setattr("draftpilot.core.config.settings.backup.root", tmp_path / "backups")
    enqueue = AsyncMock()
    monkeypatch.setattr("draftpilot.core.temporal.start_best_effort", enqueue)
    monkeypatch.setattr("draftpilot.api.lifecycle.events.publish", AsyncMock())
    monkeypatch.setattr("draftpilot.api.backups._enqueue_restored_artifacts", AsyncMock())
    monkeypatch.setattr("draftpilot.api.lifecycle._enqueue_restored_artifacts", AsyncMock())
    context = memory_session()
    session = run_async(context.__aenter__())

    async def seed() -> None:
        """Create one project touching every kind of data, plus an unrelated project."""
        big_fish, neighbour = Project(title="Big Fish"), Project(title="Neighbour")
        session.add_all([big_fish, neighbour])
        await session.flush()
        draft = Screenplay(project_id=big_fish.id or 0, title="Big Fish")
        other = Screenplay(project_id=neighbour.id or 0, title="Neighbour")
        session.add_all([draft, other])
        await session.commit()
        await save_screenplay_doc(session, draft.id or 0, parse_fountain(BIG_FISH.read_text()))
        await save_screenplay_doc(session, other.id or 0, parse_fountain("INT. HOUSE - DAY\n\nA door.\n"))
        await refresh_story_twin(session, big_fish.id or 0)
        block = (await session.exec(select(Block).join(Scene).where(Scene.heading.contains("BEDROOM")))).scalars().first()  # type: ignore[attr-defined]
        run = WorkflowRun(project_id=big_fish.id or 0, kind="room_workflow")
        session.add_all([StoryArtifact(project_id=big_fish.id or 0, kind="brief", title="Brief", content="A tall tale."), run])
        await session.flush()
        agent_run = AgentRun(project_id=big_fish.id or 0, workflow_run_id=run.id, role="scene_writer")
        session.add(agent_run)
        await session.flush()
        session.add_all(
            [
                AgentProposal(project_id=big_fish.id or 0, run_id=run.id, target_kind="scene", target_id=block.scene_id, operation={}, base_version=1),
                AgentFeedback(project_id=big_fish.id or 0, agent_run_id=agent_run.id, rating=1),
                DialogueTranslation(block_id=block.id, language="French", text="Bonjour", source_version=1),
                SceneRevision(scene_id=block.scene_id, rev_number=1, message="first", snapshot={}),
                MCPApprovalRequest(client_id="codex", project_id=big_fish.id or 0, capability="story.operation", action="apply", arguments_digest="x" * 64, summary="", expires_at=run.created_at),
                WriterMemory(kind="note", text="Big Fish only", project_id=big_fish.id),
                WriterMemory(kind="taboo", text="Everywhere"),
            ]
        )
        await session.commit()

    run_async(seed())
    app = FastAPI()

    async def dependency() -> AsyncGenerator[AsyncSession]:
        """Yield the shared seeded session."""
        yield session

    app.dependency_overrides[async_get_db] = dependency
    app.include_router(lifecycle_router, prefix="/api/v1")
    app.include_router(backups_router, prefix="/api/v1")
    yield TestClient(app), session, enqueue
    run_async(context.__aexit__(None, None, None))


def _count(session: AsyncSession, model: type, *where: object) -> int:
    """Count rows of a model."""
    return run_async(session.exec(select(func.count()).select_from(model).where(*where))).one()[0]  # type: ignore[arg-type]


def test_every_project_table_is_covered() -> None:
    """New tables that hold project data are picked up automatically, children before parents."""
    names = [table.name for table in project_tables()]
    assert {"block", "scene", "act", "screenplay", "agent_run", "agent_feedback", "workflow_run", "knowledge_node", "mcp_approval_request"} <= set(names)
    assert names.index("block") < names.index("scene") < names.index("act") < names.index("screenplay")
    assert names.index("agent_feedback") < names.index("agent_run") < names.index("workflow_run")


def test_delete_backs_up_then_removes_everything_and_can_be_restored(studio: tuple[TestClient, AsyncSession, AsyncMock]) -> None:
    """Nothing of the project survives except its backup; the neighbour and global memories are untouched."""
    client, session, enqueue = studio
    scenes_before = _count(session, Scene)
    deleted = client.delete("/api/v1/projects/1")
    assert deleted.status_code == 200, deleted.text
    body = deleted.json()
    assert body["title"] == "Big Fish" and body["backup"].endswith(".json.gz")
    assert body["removed"]["block"] > 2000 and body["removed"]["knowledge_node"] > 20
    enqueue.assert_any_await("purge_rag_project", 1, description="RAG project purge enqueue")
    session.expire_all()
    assert _count(session, Project) == 1 and _count(session, Scene) == 1 < scenes_before
    for model in (AgentProposal, AgentRun, AgentFeedback, DialogueTranslation, SceneRevision, MCPApprovalRequest, StoryArtifact, WorkflowRun):
        assert _count(session, model) == 0, model
    assert [memory.text for memory in run_async(session.exec(select(WriterMemory))).scalars()] == ["Everywhere"]
    assert client.delete("/api/v1/projects/1").status_code == 404

    deleted_list = client.get("/api/v1/projects/deleted").json()
    assert [(item["project_id"], item["title"]) for item in deleted_list] == [(1, "Big Fish")]
    assert client.post("/api/v1/projects/deleted/2/dismiss").status_code == 409  # still exists
    restored = client.post(f"/api/v1/projects/1/backups/{deleted_list[0]['filename']}/restore")
    assert restored.status_code == 201, restored.text
    new_id = restored.json()["project_id"]
    session.expire_all()
    assert _count(session, Scene) == scenes_before
    assert run_async(session.get(Project, new_id)).title == "Big Fish"
    assert client.get("/api/v1/projects/deleted").json() == []


def test_duplicate_copies_every_draft_under_a_new_title(studio: tuple[TestClient, AsyncSession, AsyncMock]) -> None:
    """The copy has its own ids and the same scenes; the original is untouched."""
    client, session, enqueue = studio
    blocks_before = _count(session, Block)
    copy = client.post("/api/v1/projects/1/duplicate", json={})
    assert copy.status_code == 201, copy.text
    assert copy.json()["title"] == "Big Fish (copy)" and copy.json()["id"] == 3
    named = client.post("/api/v1/projects/2/duplicate", json={"title": "Neighbour v2"}).json()
    assert named["title"] == "Neighbour v2"
    session.expire_all()
    assert _count(session, Block) == blocks_before * 2  # both projects were copied, block for block
    assert _count(session, Screenplay, Screenplay.project_id == 3) == 1
    enqueue.assert_any_await("reindex_project", 3, description="RAG reindex enqueue")
    assert client.post("/api/v1/projects/99/duplicate", json={}).status_code == 404


def test_dismissing_hides_a_deleted_project_but_keeps_its_backup(studio: tuple[TestClient, AsyncSession, AsyncMock], tmp_path: Path) -> None:
    """Dismiss removes the entry from Recently deleted without deleting the backup file."""
    client, _session, _enqueue = studio
    backup = client.delete("/api/v1/projects/2").json()["backup"]
    assert [item["project_id"] for item in client.get("/api/v1/projects/deleted").json()] == [2]
    assert client.post("/api/v1/projects/deleted/2/dismiss").json() == {"hidden": 1}
    assert client.get("/api/v1/projects/deleted").json() == []
    assert (tmp_path / "backups" / backup).exists()
