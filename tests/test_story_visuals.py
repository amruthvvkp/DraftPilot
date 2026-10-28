"""Test the visual tools' aggregate: narrative-order tension, runtime, milestones and the cast graph."""

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
from draftpilot.core.db import async_get_db
from draftpilot.crud import projects as projects_crud
from draftpilot.models import ProjectCreate

API = "/api/v1/projects/1"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[TestClient]:
    """Serve the project and story routers over a fresh database holding one project."""
    monkeypatch.setattr("draftpilot.core.temporal.start_best_effort", _noop)
    monkeypatch.setattr("draftpilot.core.events.publish", _noop)
    context = memory_session(f"sqlite+aiosqlite:///{tmp_path / 'visuals.db'}")
    session = run_async(context.__aenter__())
    run_async(projects_crud.create_with_references(session, ProjectCreate(title="Big Fish"), []))
    app = FastAPI()

    async def dependency() -> AsyncGenerator[AsyncSession]:
        """Yield the shared session."""
        yield session

    app.dependency_overrides[async_get_db] = dependency
    app.include_router(projects_router, prefix="/api/v1")
    app.include_router(story_router, prefix="/api/v1")
    yield TestClient(app)
    run_async(context.__aexit__(None, None, None))


async def _noop(*_args: object, **_kwargs: object) -> None:
    """Swallow side effects (Temporal, Redis) in tests."""


def test_visuals_aggregate_tension_runtime_milestones_and_cast(client: TestClient) -> None:
    """Scenes come in narrative order with the cast average; typed beats are milestones; shared moments weight edges."""
    act = client.get(f"{API}/workspace").json()["acts"][0]["id"]
    first = client.post(f"{API}/scenes", json={"heading": "EXT. RIVER - DAY", "act_id": act}).json()
    second = client.post(f"{API}/scenes", json={"heading": "INT. CIRCUS - NIGHT", "act_id": act}).json()
    edward = client.post(f"{API}/characters", json={"name": "Edward", "role": "lead"}).json()["id"]
    will = client.post(f"{API}/characters", json={"name": "Will"}).json()["id"]
    sandra = client.post(f"{API}/characters", json={"name": "Sandra"}).json()["id"]
    moment = client.post(f"{API}/moments", json={"title": "The river", "scene_id": second["id"]}).json()["id"]
    client.post(f"{API}/timeline-events", json={"character_id": edward, "title": "Wades in", "intensity": 4, "moment_id": moment})
    client.post(f"{API}/timeline-events", json={"character_id": will, "title": "Watches", "intensity": -2, "moment_id": moment})
    client.post(f"{API}/timeline-events", json={"character_id": sandra, "title": "Arrives", "intensity": 3, "scene_id": first["id"]})
    client.post(f"{API}/relationships", json={"source_character_id": will, "target_character_id": edward, "relation": "son"})
    client.post(f"{API}/beats", json={"title": "Plain", "act_id": act})
    client.post(f"{API}/beats", json={"title": "The call", "beat_type": "inciting_incident", "act_id": act, "scene_ids": [second["id"], first["id"]]})
    client.post(f"{API}/beats", json={"title": "Somewhere", "beat_type": "midpoint"})

    data = client.get(f"{API}/visuals").json()
    assert [(scene["heading"], scene["index"], scene["intensity"], scene["event_count"]) for scene in data["scenes"]] == [
        ("EXT. RIVER - DAY", 0, 3.0, 1),
        ("INT. CIRCUS - NIGHT", 1, 1.0, 2),
    ]
    assert data["scenes"][1]["start_seconds"] == data["scenes"][0]["runtime_seconds"] >= 30
    assert data["total_runtime_seconds"] == sum(scene["runtime_seconds"] for scene in data["scenes"])
    assert data["acts"][0]["id"] == act
    assert [(item["title"], item["scene_index"]) for item in data["milestones"]] == [("The call", 0), ("Somewhere", None)]
    edges = {(edge["source"], edge["target"]): edge for edge in data["edges"]}
    pair = tuple(sorted((edward, will)))
    assert (edges[pair]["shared_moments"], edges[pair]["shared_scenes"], edges[pair]["relations"]) == (1, 1, ["son"])
    assert len(edges) == 1
    assert {item["name"]: item["moment_count"] for item in data["characters"]} == {"Edward": 1, "Will": 1, "Sandra": 0}


def test_visuals_of_an_empty_or_missing_project(client: TestClient) -> None:
    """A fresh project has an act and nothing else; an unknown project is a 404."""
    data = client.get(f"{API}/visuals").json()
    assert (data["scenes"], data["milestones"], data["edges"], data["total_runtime_seconds"]) == ([], [], [], 0)
    assert client.get("/api/v1/projects/99/visuals").status_code == 404
