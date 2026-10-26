"""Test the typed story domain end to end over REST: storyline, cast, timelines, outline, structure, proposals, backup."""

from collections.abc import AsyncGenerator, Iterator
from pathlib import Path

import pytest
from _async import run_async
from _db import memory_session
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.api.projects import router as projects_router
from draftpilot.api.story import router as story_router
from draftpilot.core import proposals
from draftpilot.core.db import async_get_db
from draftpilot.core.project_backup import project_payload, restore_payload
from draftpilot.core.story import entities
from draftpilot.core.story.proposals import propose_story_change
from draftpilot.crud import projects as projects_crud
from draftpilot.models import ProjectCreate


@pytest.fixture
def studio(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[tuple[TestClient, AsyncSession]]:
    """Serve the project and story routers over a fresh database holding two projects."""
    monkeypatch.setattr("draftpilot.core.temporal.start_best_effort", _noop)
    monkeypatch.setattr("draftpilot.core.events.publish", _noop)
    context = memory_session(f"sqlite+aiosqlite:///{tmp_path / 'story.db'}")
    session = run_async(context.__aenter__())
    run_async(projects_crud.create_with_references(session, ProjectCreate(title="Big Fish"), []))
    run_async(projects_crud.create_with_references(session, ProjectCreate(title="Other"), []))
    app = FastAPI()

    async def dependency() -> AsyncGenerator[AsyncSession]:
        """Yield the shared session."""
        yield session

    app.dependency_overrides[async_get_db] = dependency
    app.include_router(projects_router, prefix="/api/v1")
    app.include_router(story_router, prefix="/api/v1")
    yield TestClient(app), session
    run_async(context.__aexit__(None, None, None))


async def _noop(*_args: object, **_kwargs: object) -> None:
    """Swallow side effects (Temporal, Redis) in tests."""


def test_manual_flow_from_storyline_to_first_scene(studio: tuple[TestClient, AsyncSession]) -> None:
    """A writer can build storyline, cast, timeline, outline and the first scene with no agent."""
    client, _session = studio
    api = "/api/v1/projects/1"
    project = client.get(f"{api}/storyline").json()
    patched = client.patch(api, json={"logline": "A son chases the truth of his father's tall tales.", "premise": "Stories outlive us."}, headers={"If-Match": str(project["version"])})
    assert patched.status_code == 200 and patched.json()["premise"] == "Stories outlive us."
    assert client.patch(api, json={"theme": "x"}, headers={"If-Match": "1"}).status_code == 409
    edward = client.post(f"{api}/characters", json={"name": "Edward Bloom", "role": "protagonist", "want": "To be a legend", "need": "To be known"})
    will = client.post(f"{api}/characters", json={"name": "Will Bloom"})
    assert edward.status_code == will.status_code == 201
    edward_id, will_id = edward.json()["id"], will.json()["id"]
    assert edward.json()["writer_edited"] and edward.json()["source"] == "writer"
    stale = client.patch(f"{api}/characters/{edward_id}", json={"flaw": "Vanity"}, headers={"If-Match": "9"})
    assert stale.status_code == 409
    assert client.patch(f"{api}/characters/{edward_id}", json={"flaw": "Vanity"}).status_code == 428
    assert client.patch(f"{api}/characters/{edward_id}", json={"flaw": "Vanity"}, headers={"If-Match": "1"}).json()["version"] == 2
    relation = client.post(f"{api}/relationships", json={"source_character_id": edward_id, "target_character_id": will_id, "relation": "father of"})
    assert relation.status_code == 201
    assert client.post(f"{api}/relationships", json={"source_character_id": edward_id, "target_character_id": edward_id, "relation": "x"}).status_code == 422
    for position, title in enumerate(["Meets the witch", "Leaves Ashton", "Dies by the river"]):
        assert client.post(f"{api}/timeline-events", json={"character_id": edward_id, "position": position, "title": title}).status_code == 201
    assert [item["title"] for item in client.get(f"{api}/characters/{edward_id}/timeline").json()] == ["Meets the witch", "Leaves Ashton", "Dies by the river"]
    act_two = client.post(f"{api}/acts", json={"title": "Act Two"})
    assert act_two.status_code == 201
    beat = client.post(f"{api}/beats", json={"title": "Will returns home", "act_id": act_two.json()["id"], "character_ids": [will_id]})
    assert beat.status_code == 201
    scene = client.post(f"{api}/scenes", json={"heading": "INT. BLOOM HOUSE - NIGHT"})
    assert scene.status_code == 201, scene.text
    scene_id = scene.json()["id"]
    block = client.post(f"{api}/scenes/{scene_id}/blocks", json={"element_type": "action", "text": "Rain."}, headers={"If-Match": "1"})
    assert block.status_code == 201
    linked = client.patch(f"{api}/beats/{beat.json()['id']}", json={"scene_ids": [scene_id]}, headers={"If-Match": "1"})
    assert linked.json()["scene_ids"] == [scene_id]
    moved = client.post(f"{api}/scenes/{scene_id}/move", json={"position": 0, "act_id": act_two.json()["id"]}, headers={"If-Match": "2"})
    assert moved.status_code == 200 and moved.json()["act_id"] == act_two.json()["id"]
    assert client.delete(f"{api}/acts/{act_two.json()['id']}").status_code == 409  # has scenes
    assert client.delete(f"{api}/scenes/{scene_id}", headers={"If-Match": "3"}).status_code == 204
    assert client.get(f"{api}/beats").json()[0]["scene_ids"] == []
    assert client.delete(f"{api}/characters/{edward_id}", headers={"If-Match": "2"}).status_code == 204
    assert client.get(f"{api}/timeline-events").json() == [] and client.get(f"{api}/relationships").json() == []
    assert client.get(f"{api}/beats").json()[0]["character_ids"] == [will_id]


def test_story_entities_never_cross_projects(studio: tuple[TestClient, AsyncSession]) -> None:
    """References and reads stay inside one project."""
    client, _session = studio
    mira = client.post("/api/v1/projects/2/characters", json={"name": "Mira"}).json()
    assert client.get(f"/api/v1/projects/1/characters/{mira['id']}").status_code == 404
    response = client.post("/api/v1/projects/1/timeline-events", json={"character_id": mira["id"], "title": "Steals"})
    assert response.status_code == 404
    assert client.post("/api/v1/projects/1/scenes", json={"heading": "X", "act_id": 2}).status_code == 404


def test_story_proposals_apply_as_the_writer_and_roll_back(studio: tuple[TestClient, AsyncSession]) -> None:
    """Agent story changes wait for the writer, and approved ones are reversible."""
    _client, session = studio

    async def scenario() -> None:
        """Propose a character, an update, a storyline edit; approve and roll back."""
        created = await propose_story_change(session, 1, "character", "create", {"name": "Karl", "role": "supporting"}, summary="The giant")
        assert await entities.list_entities(session, 1, "character") == []
        approved = await proposals.approve(session, 1, created.id or 0)
        karl = await entities.get_entity(session, 1, "character", approved.diff["created_id"])
        assert karl.source == "agent"
        update = await propose_story_change(session, 1, "character", "update", {"want": "A friend"}, entity_id=karl.id)
        await proposals.approve(session, 1, update.id or 0)
        assert (await entities.get_entity(session, 1, "character", karl.id or 0)).want == "A friend"
        assert (await proposals.rollback(session, 1, update.id or 0)).status == "rolled_back"
        assert (await entities.get_entity(session, 1, "character", karl.id or 0)).want == ""
        storyline = await propose_story_change(session, 1, "storyline", "update", {"tone": "Wistful"})
        await proposals.approve(session, 1, storyline.id or 0)
        assert (await projects_crud.get(session, 1)).tone == "Wistful"  # type: ignore[union-attr]
        rejected = await propose_story_change(session, 1, "location", "create", {"name": "Spectre"})
        assert (await proposals.reject(session, 1, rejected.id or 0)).status == "rejected"
        assert await entities.list_entities(session, 1, "location") == []
        # Writer edits after approval block the rollback instead of clobbering them.
        await entities.update_entity(session, 1, "character", karl.id or 0, {"voice": "Booming"}, expected_version=None, require_version=False)
        with pytest.raises(Exception, match="changed"):
            await proposals.rollback(session, 1, created.id or 0)

    run_async(scenario())


def test_backup_round_trip_keeps_cast_timeline_and_outline_links(studio: tuple[TestClient, AsyncSession]) -> None:
    """Restoring a backup recreates story entities with remapped references."""
    client, session = studio
    api = "/api/v1/projects/1"
    scene_id = client.post(f"{api}/scenes", json={"heading": "EXT. RIVER - DAY"}).json()["id"]
    edward = client.post(f"{api}/characters", json={"name": "Edward"}).json()["id"]
    will = client.post(f"{api}/characters", json={"name": "Will"}).json()["id"]
    client.post(f"{api}/relationships", json={"source_character_id": edward, "target_character_id": will, "relation": "father of"})
    client.post(f"{api}/timeline-events", json={"character_id": will, "title": "Jumps in", "scene_id": scene_id})
    client.post(f"{api}/beats", json={"title": "The river", "scene_ids": [scene_id], "character_ids": [edward, will]})

    async def scenario() -> None:
        """Serialise, restore, and compare."""
        restored = await restore_payload(session, await project_payload(session, 1))
        new_id = restored.id or 0
        cast = {row.name: row.id for row in await entities.list_entities(session, new_id, "character")}
        assert set(cast) == {"Edward", "Will"} and cast["Edward"] != edward
        (relation,) = await entities.list_entities(session, new_id, "relationship")
        assert (relation.source_character_id, relation.target_character_id) == (cast["Edward"], cast["Will"])
        (event,) = await entities.list_entities(session, new_id, "timeline_event")
        (beat,) = await entities.list_entities(session, new_id, "beat")
        assert event.character_id == cast["Will"] and event.scene_id == beat.scene_ids[0] != scene_id
        assert beat.character_ids == [cast["Edward"], cast["Will"]]

    run_async(scenario())
