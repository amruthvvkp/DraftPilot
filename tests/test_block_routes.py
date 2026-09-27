"""Test versioned block delete and reorder routes against a real database."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
from _async import run_async
from _db import memory_session
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.api.projects import router
from draftpilot.core.db import async_get_db
from draftpilot.core.screenplay.hydrate import blocks_for_scene
from draftpilot.models import Act, Block, Project, Scene, Screenplay


@pytest.fixture
def seeded(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, AsyncSession, AsyncMock]:
    """Serve the projects router over a seeded in-memory database."""
    changed = AsyncMock()
    monkeypatch.setattr("draftpilot.api.projects.scene_changed", changed)
    context = memory_session()
    session = run_async(context.__aenter__())

    async def seed() -> None:
        """Persist one scene with three blocks."""
        project = Project(title="Big Fish")
        session.add(project)
        await session.flush()
        screenplay = Screenplay(project_id=project.id or 0, title="Big Fish")
        session.add(screenplay)
        await session.flush()
        act = Act(screenplay_id=screenplay.id or 0)
        session.add(act)
        await session.flush()
        scene = Scene(act_id=act.id or 0, heading="INT. HOUSE", version=1)
        session.add(scene)
        await session.flush()
        session.add_all([Block(scene_id=scene.id or 0, position=i, text=t) for i, t in enumerate(["A", "B", "C"])])
        await session.commit()

    run_async(seed())
    app = FastAPI()

    async def dependency() -> AsyncGenerator[AsyncSession]:
        """Yield the shared seeded session."""
        yield session

    app.dependency_overrides[async_get_db] = dependency
    app.include_router(router, prefix="/api/v1")
    yield TestClient(app), session, changed
    run_async(context.__aexit__(None, None, None))


def _texts(session: AsyncSession) -> list[str]:
    """Return the scene's block texts in order."""
    return [block.text for block in run_async(blocks_for_scene(session, 1))]


def test_reorder_requires_version_and_the_exact_block_set(seeded: tuple[TestClient, AsyncSession, AsyncMock]) -> None:
    """Reordering is versioned and must list every block exactly once."""
    client, session, changed = seeded
    url = "/api/v1/projects/1/scenes/1/blocks/order"
    assert client.put(url, json={"block_ids": [3, 2, 1]}).status_code == 428
    assert client.put(url, json={"block_ids": [3, 2, 1]}, headers={"If-Match": "9"}).status_code == 409
    assert client.put(url, json={"block_ids": [3, 1]}, headers={"If-Match": "1"}).status_code == 422
    response = client.put(url, json={"block_ids": [3, 1, 2]}, headers={"If-Match": "1"})
    assert response.status_code == 200
    assert [block["text"] for block in response.json()] == ["C", "A", "B"]
    assert _texts(session) == ["C", "A", "B"]
    assert changed.await_args.kwargs == {"reason": "blocks.reordered"}


def test_delete_closes_the_position_gap_and_bumps_the_version(seeded: tuple[TestClient, AsyncSession, AsyncMock]) -> None:
    """Deleting a block renumbers the rest and requires the current scene version."""
    client, session, changed = seeded
    assert client.delete("/api/v1/projects/1/scenes/1/blocks/2", headers={"If-Match": "1"}).status_code == 204
    assert _texts(session) == ["A", "C"]
    assert [block.position for block in run_async(blocks_for_scene(session, 1))] == [0, 1]
    assert client.delete("/api/v1/projects/1/scenes/1/blocks/3", headers={"If-Match": "1"}).status_code == 409
    assert client.delete("/api/v1/projects/1/scenes/1/blocks/99", headers={"If-Match": "2"}).status_code == 404
    assert changed.await_args.kwargs == {"reason": "block.deleted"}


def test_writer_edits_take_authorship_but_no_op_saves_do_not(seeded: tuple[TestClient, AsyncSession, AsyncMock]) -> None:
    """Changing a block's text marks it human-authored; saving identical text keeps its origin."""
    client, session, _changed = seeded
    block = run_async(blocks_for_scene(session, 1))[0]
    block.origin = "import"
    session.add(block)
    run_async(session.commit())
    same = client.patch("/api/v1/projects/1/scenes/1/blocks/1", json={"text": "A"}, headers={"If-Match": "1"})
    assert same.json()["origin"] == "import"
    edited = client.patch("/api/v1/projects/1/scenes/1/blocks/1", json={"text": "A, rewritten."}, headers={"If-Match": "2"})
    assert edited.status_code == 200 and edited.json()["origin"] == "human"
