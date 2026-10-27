"""Test the journey map data over REST: event fields, shared moments, narrative variants, proposals, backup."""

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
from draftpilot.core.errors import Invalid
from draftpilot.core.project_backup import project_payload, restore_payload
from draftpilot.core.story import entities
from draftpilot.core.story.proposals import propose_story_change
from draftpilot.crud import projects as projects_crud
from draftpilot.models import ProjectCreate

API = "/api/v1/projects/1"


@pytest.fixture
def studio(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[tuple[TestClient, AsyncSession]]:
    """Serve the project and story routers over a fresh database holding two projects."""
    monkeypatch.setattr("draftpilot.core.temporal.start_best_effort", _noop)
    monkeypatch.setattr("draftpilot.core.events.publish", _noop)
    context = memory_session(f"sqlite+aiosqlite:///{tmp_path / 'journey.db'}")
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


def _cast(client: TestClient) -> tuple[int, int]:
    """Create Edward and Will; return their ids."""
    edward = client.post(f"{API}/characters", json={"name": "Edward"}).json()["id"]
    will = client.post(f"{API}/characters", json={"name": "Will"}).json()["id"]
    return edward, will


def test_timeline_events_carry_motivation_history_and_intensity(studio: tuple[TestClient, AsyncSession]) -> None:
    """New event fields default sensibly, stay within −5…+5 and update under If-Match."""
    client, _session = studio
    edward, _will = _cast(client)
    event = client.post(f"{API}/timeline-events", json={"character_id": edward, "title": "Meets the witch"}).json()
    assert (event["motivation"], event["history"], event["intensity"], event["chrono_index"], event["moment_id"]) == ("", "", 0, None, None)
    assert client.post(f"{API}/timeline-events", json={"character_id": edward, "title": "Too much", "intensity": 6}).status_code == 422
    patch = {"motivation": "To know how he dies", "history": "A boy in Ashton", "intensity": -3, "chrono_index": 1937.5}
    assert client.patch(f"{API}/timeline-events/{event['id']}", json=patch).status_code == 428
    assert client.patch(f"{API}/timeline-events/{event['id']}", json=patch, headers={"If-Match": "9"}).status_code == 409
    updated = client.patch(f"{API}/timeline-events/{event['id']}", json=patch, headers={"If-Match": str(event["version"])}).json()
    assert {key: updated[key] for key in patch} == patch and updated["version"] == event["version"] + 1
    assert client.patch(f"{API}/timeline-events/{event['id']}", json={"intensity": -6}, headers={"If-Match": str(updated["version"])}).status_code == 422


def test_shared_moments_link_events_and_version_like_every_entity(studio: tuple[TestClient, AsyncSession]) -> None:
    """A writer creates a moment, links each character's event, edits it under If-Match and deletes it."""
    client, session = studio
    edward, will = _cast(client)
    scene_id = client.post(f"{API}/scenes", json={"heading": "EXT. RIVER - DAY"}).json()["id"]
    beat_id = client.post(f"{API}/beats", json={"title": "The river"}).json()["id"]
    moment = client.post(
        f"{API}/moments", json={"title": "The river", "story_time": "1987", "chrono_index": 3, "scene_id": scene_id, "beat_id": beat_id}
    ).json()
    assert moment["version"] == 1 and moment["scene_id"] == scene_id
    client.post(f"{API}/moments", json={"title": "Unplaced idea"})
    client.post(f"{API}/moments", json={"title": "Earlier", "chrono_index": 1})
    assert [item["title"] for item in client.get(f"{API}/moments").json()] == ["Earlier", "The river", "Unplaced idea"]
    for character_id, objective in ((edward, "Become the fish"), (will, "Let him go")):
        response = client.post(f"{API}/timeline-events", json={"character_id": character_id, "title": "At the river", "objective": objective, "moment_id": moment["id"]})
        assert response.status_code == 201
    client.post(f"{API}/timeline-events", json={"character_id": will, "title": "Alone"})
    participants = client.get(f"{API}/timeline-events", params={"moment_id": moment["id"]}).json()
    assert sorted(item["objective"] for item in participants) == ["Become the fish", "Let him go"]
    # A moment, scene or beat from another project is refused.
    other = client.post("/api/v1/projects/2/moments", json={"title": "Elsewhere"}).json()
    assert client.post(f"{API}/timeline-events", json={"character_id": will, "title": "X", "moment_id": other["id"]}).status_code == 404
    assert client.patch(f"{API}/moments/{other['id']}", json={"title": "Y"}, headers={"If-Match": "1"}).status_code == 404
    assert client.patch(f"{API}/moments/{moment['id']}", json={"summary": "He swims"}).status_code == 428
    assert client.patch(f"{API}/moments/{moment['id']}", json={"summary": "He swims"}, headers={"If-Match": "2"}).status_code == 409
    edited = client.patch(f"{API}/moments/{moment['id']}", json={"summary": "He swims"}, headers={"If-Match": "1"}).json()
    assert edited["summary"] == "He swims" and edited["version"] == 2
    assert client.delete(f"{API}/moments/{moment['id']}", headers={"If-Match": "1"}).status_code == 409
    assert client.delete(f"{API}/moments/{moment['id']}", headers={"If-Match": "2"}).status_code == 204
    # The participants keep their own events, unlinked and re-versioned.
    events = client.get(f"{API}/timeline-events").json()
    assert len(events) == 3 and all(item["moment_id"] is None for item in events)
    assert sorted(item["version"] for item in events) == [1, 2, 2]
    assert len(run_async(entities.list_entities(session, 1, "moment"))) == 2


def test_narrative_variants_store_named_scene_orders(studio: tuple[TestClient, AsyncSession]) -> None:
    """A variant saves an ordered list of the project's own scenes, each once."""
    client, _session = studio
    first = client.post(f"{API}/scenes", json={"heading": "INT. HOUSE - DAY"}).json()["id"]
    second = client.post(f"{API}/scenes", json={"heading": "EXT. RIVER - DAY"}).json()["id"]
    variant = client.post(f"{API}/narrative-variants", json={"name": "River first", "scene_ids": [second, first]}).json()
    assert variant["scene_ids"] == [second, first] and variant["version"] == 1
    assert client.post(f"{API}/narrative-variants", json={"name": "Twice", "scene_ids": [first, first]}).status_code == 422
    assert client.post(f"{API}/narrative-variants", json={"name": "", "scene_ids": []}).status_code == 422
    foreign = client.post("/api/v1/projects/2/scenes", json={"heading": "INT. ELSEWHERE - DAY"}).json()["id"]
    assert client.post(f"{API}/narrative-variants", json={"name": "Foreign", "scene_ids": [foreign]}).status_code == 404
    url = f"{API}/narrative-variants/{variant['id']}"
    assert client.patch(url, json={"scene_ids": [first, first]}, headers={"If-Match": "1"}).status_code == 422
    renamed = client.patch(url, json={"name": "Script order", "scene_ids": [first, second]}, headers={"If-Match": "1"}).json()
    assert (renamed["name"], renamed["scene_ids"], renamed["version"]) == ("Script order", [first, second], 2)
    assert client.patch(url, json={"name": "Stale"}, headers={"If-Match": "1"}).status_code == 409
    assert [item["name"] for item in client.get(f"{API}/narrative-variants").json()] == ["Script order"]
    assert client.delete(url, headers={"If-Match": "2"}).status_code == 204
    assert client.get(f"{API}/narrative-variants").json() == []


def test_agents_propose_moments_and_event_fields_but_never_variants(studio: tuple[TestClient, AsyncSession]) -> None:
    """Moments and the new event fields go through reviewable proposals; variants stay the writer's."""
    client, session = studio
    edward, _will = _cast(client)
    event = client.post(f"{API}/timeline-events", json={"character_id": edward, "title": "Meets the witch"}).json()

    async def scenario() -> None:
        """Propose, approve and roll back; refuse a variant proposal."""
        created = await propose_story_change(session, 1, "moment", "create", {"title": "The witch's eye", "story_time": "1937"})
        assert await entities.list_entities(session, 1, "moment") == []
        approved = await proposals.approve(session, 1, created.id or 0)
        moment = await entities.get_entity(session, 1, "moment", approved.diff["created_id"])
        assert moment.title == "The witch's eye"
        fields = {"motivation": "To know his end", "intensity": 4, "moment_id": moment.id}
        update = await propose_story_change(session, 1, "timeline_event", "update", fields, entity_id=event["id"])
        assert update.before == {"motivation": "", "intensity": 0, "moment_id": None}
        await proposals.approve(session, 1, update.id or 0)
        row = await entities.get_entity(session, 1, "timeline_event", event["id"])
        assert (row.motivation, row.intensity, row.moment_id) == ("To know his end", 4, moment.id)
        await proposals.rollback(session, 1, update.id or 0)
        row = await entities.get_entity(session, 1, "timeline_event", event["id"])
        assert (row.motivation, row.intensity, row.moment_id) == ("", 0, None)
        with pytest.raises(Invalid, match="intensity"):
            await propose_story_change(session, 1, "timeline_event", "update", {"intensity": 9}, entity_id=event["id"])
        with pytest.raises(Invalid, match="cannot propose"):
            await propose_story_change(session, 1, "variant", "create", {"name": "Agent order", "scene_ids": []})

    run_async(scenario())


def test_backup_round_trip_keeps_moments_and_variants(studio: tuple[TestClient, AsyncSession]) -> None:
    """Restoring a backup recreates moments, their linked events and variants with remapped ids."""
    client, session = studio
    edward, will = _cast(client)
    first = client.post(f"{API}/scenes", json={"heading": "INT. HOUSE - DAY"}).json()["id"]
    second = client.post(f"{API}/scenes", json={"heading": "EXT. RIVER - DAY"}).json()["id"]
    beat = client.post(f"{API}/beats", json={"title": "The river", "scene_ids": [second]}).json()["id"]
    moment = client.post(f"{API}/moments", json={"title": "The river", "chrono_index": 2.5, "story_time": "1987", "scene_id": second, "beat_id": beat}).json()["id"]
    for character_id, intensity in ((edward, 5), (will, -2)):
        client.post(f"{API}/timeline-events", json={"character_id": character_id, "title": "At the river", "intensity": intensity, "motivation": "Love", "chrono_index": 2.5, "moment_id": moment})
    client.post(f"{API}/narrative-variants", json={"name": "River first", "scene_ids": [second, first]})

    async def scenario() -> None:
        """Serialise, restore, and compare."""
        payload = await project_payload(session, 1)
        assert [item["title"] for item in payload["story"]["moment"]] == ["The river"]
        assert [item["name"] for item in payload["story"]["variant"]] == ["River first"]
        restored = await restore_payload(session, payload)
        new_id = restored.id or 0
        (new_moment,) = await entities.list_entities(session, new_id, "moment")
        (new_beat,) = await entities.list_entities(session, new_id, "beat")
        assert new_moment.id != moment and (new_moment.chrono_index, new_moment.story_time) == (2.5, "1987")
        assert new_moment.beat_id == new_beat.id and new_moment.scene_id == new_beat.scene_ids[0] != second
        events = await entities.list_entities(session, new_id, "timeline_event", moment_id=new_moment.id)
        assert sorted(event.intensity for event in events) == [-2, 5]
        assert {event.motivation for event in events} == {"Love"} and {event.chrono_index for event in events} == {2.5}
        (variant,) = await entities.list_entities(session, new_id, "variant")
        assert variant.name == "River first" and len(variant.scene_ids) == 2 and variant.scene_ids[0] == new_moment.scene_id

    run_async(scenario())
