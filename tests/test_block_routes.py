"""Test versioned block delete, reorder and batched scene content routes against a real database."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import httpx
import pytest
from _async import run_async
from _db import memory_session
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.api.projects import router
from draftpilot.core.db import async_get_db
from draftpilot.core.screenplay.hydrate import blocks_for_scene
from draftpilot.models import (
    Act,
    Block,
    DialogueTranslation,
    Project,
    Scene,
    Screenplay,
)


@pytest.fixture
def seeded(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, AsyncSession, AsyncMock]:
    """Serve the projects router over a seeded in-memory database."""
    changed = AsyncMock()
    monkeypatch.setattr("draftpilot.core.story.structure.scene_changed", changed)
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


def _content(client: TestClient, version: int, body: dict[str, object]) -> httpx.Response:
    """PUT a scene's full content with ``If-Match``."""
    return client.put("/api/v1/projects/1/scenes/1/content", json=body, headers={"If-Match": str(version)})


def test_content_write_diffs_blocks_in_one_version_bump(seeded: tuple[TestClient, AsyncSession, AsyncMock]) -> None:
    """Kept ids update in place, new blocks are created, missing ones deleted, positions renumbered."""
    client, session, changed = seeded
    body = {
        "heading": "INT. LIBRARY - DAY",
        "blocks": [
            {"id": 3, "text": "C"},
            {"element_type": "character", "text": "EDWARD"},
            {"id": 1, "text": "A, rewritten."},
            {"element_type": "dialogue", "text": "Hello."},
        ],
    }
    response = _content(client, 1, body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["version"] == 2 and len(result["created_ids"]) == 2
    assert result["block_ids"] == [3, result["created_ids"][0], 1, result["created_ids"][1]]
    blocks = run_async(blocks_for_scene(session, 1))
    assert [block.id for block in blocks] == result["block_ids"]
    assert [block.text for block in blocks] == ["C", "EDWARD", "A, rewritten.", "Hello."]
    assert [block.position for block in blocks] == [0, 1, 2, 3]
    assert blocks[1].element_type == "character"
    assert run_async(session.get(Block, 2)) is None
    scene = run_async(session.get(Scene, 1))
    assert scene is not None and scene.heading == "INT. LIBRARY - DAY" and scene.version == 2
    changed.assert_awaited_once()
    assert changed.await_args.kwargs == {"reason": "scene.content"}


def test_content_write_moves_authorship_only_for_edited_blocks(seeded: tuple[TestClient, AsyncSession, AsyncMock]) -> None:
    """An edited block becomes human-authored; an untouched agent block keeps its origin."""
    client, session, _changed = seeded
    for block in run_async(blocks_for_scene(session, 1)):
        block.origin = "proposal:7"
        session.add(block)
    run_async(session.commit())
    body = {"blocks": [{"id": 1, "text": "A"}, {"id": 2, "text": "B, mine now."}, {"id": 3, "element_type": "transition"}, {"text": "D"}]}
    assert _content(client, 1, body).status_code == 200
    blocks = run_async(blocks_for_scene(session, 1))
    assert [block.origin for block in blocks] == ["proposal:7", "human", "human", "human"]
    assert blocks[2].text == "C"  # fields left out of the post keep their stored value


def test_content_write_is_versioned_and_validated(seeded: tuple[TestClient, AsyncSession, AsyncMock]) -> None:
    """A stale or missing version and foreign or repeated ids are rejected without writing."""
    client, session, changed = seeded
    body = {"blocks": [{"text": "Only this."}]}
    assert client.put("/api/v1/projects/1/scenes/1/content", json=body).status_code == 428
    assert _content(client, 9, body).status_code == 409
    assert _content(client, 1, {"blocks": [{"id": 99, "text": "x"}]}).status_code == 422
    assert _content(client, 1, {"blocks": [{"id": 1}, {"id": 1}]}).status_code == 422
    assert _content(client, 1, {"blocks": [{"element_type": "song"}]}).status_code == 422
    assert client.put("/api/v1/projects/2/scenes/1/content", json=body, headers={"If-Match": "1"}).status_code == 404
    assert _texts(session) == ["A", "B", "C"]
    changed.assert_not_awaited()


def test_content_write_without_changes_keeps_the_version(seeded: tuple[TestClient, AsyncSession, AsyncMock]) -> None:
    """Re-posting the stored content is a no-op: no version bump, no re-index."""
    client, _session, changed = seeded
    response = _content(client, 1, {"heading": "INT. HOUSE", "blocks": [{"id": 1, "text": "A"}, {"id": 2, "text": "B"}, {"id": 3, "text": "C"}]})
    assert response.json() == {"scene_id": 1, "version": 1, "block_ids": [1, 2, 3], "created_ids": []}
    changed.assert_not_awaited()


def test_content_write_keeps_translations_on_surviving_blocks(seeded: tuple[TestClient, AsyncSession, AsyncMock]) -> None:
    """Dialogue translations stay linked to a block that keeps its id, however its text changes."""
    client, session, _changed = seeded
    session.add(DialogueTranslation(block_id=2, language="es", text="Be."))
    run_async(session.commit())
    assert _content(client, 1, {"blocks": [{"id": 2, "text": "B, longer."}, {"text": "New."}]}).status_code == 200
    translations = run_async(session.exec(select(DialogueTranslation))).all()
    assert [(item.block_id, item.text) for item in translations] == [(2, "Be.")]
