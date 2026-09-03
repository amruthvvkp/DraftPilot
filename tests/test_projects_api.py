"""Test the versioned project REST boundary without a live database."""

from collections.abc import AsyncGenerator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from draftpilot.api.projects import router
from draftpilot.core.db import async_get_db
from draftpilot.models import (
    Act,
    Block,
    BlockType,
    DialogueTranslation,
    Project,
    Scene,
    Screenplay,
)


class _Session:
    """Stand in for an async SQLModel session in API tests."""


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Build an isolated API client with a mocked database dependency."""
    app = FastAPI()

    async def session() -> AsyncGenerator[_Session, None]:
        """Yield an in-memory session marker."""
        yield _Session()

    app.dependency_overrides[async_get_db] = session
    app.include_router(router, prefix="/api/v1")
    return TestClient(app)


def test_empty_project_list_is_json(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Return an empty project collection without touching Postgres."""
    async def list_all(_session: _Session) -> list[Project]:
        """Return no projects for the isolated test database."""
        return []

    monkeypatch.setattr("draftpilot.api.projects.projects_crud.list_all", list_all)
    response = client.get("/api/v1/projects")
    assert response.status_code == 200
    assert response.json() == []


def test_create_project_persists_typed_references(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pass typed references through the request and return them in the response."""
    project = Project(id=9, title="A multilingual story", primary_language="Hindi")

    async def create_with_references(_session: _Session, data: object, references: list[object]) -> Project:
        """Return the fixture project after receiving the normalized request."""
        assert getattr(data, "primary_language") == "Hindi"
        assert len(references) == 1
        assert getattr(references[0], "label") == "Pather Panchali"
        return project

    async def list_for_project(_session: _Session, _project_id: int) -> list[object]:
        """Return the reference created by the mocked persistence layer."""
        return []

    monkeypatch.setattr(
        "draftpilot.api.projects.projects_crud.create_with_references", create_with_references
    )
    monkeypatch.setattr(
        "draftpilot.api.projects.references_crud.list_for_project", list_for_project
    )
    response = client.post(
        "/api/v1/projects",
        json={
            "title": project.title,
            "primary_language": "Hindi",
            "genres": ["Drama"],
            "languages": ["Bengali"],
            "references": [{"kind": "film", "label": "Pather Panchali"}],
        },
    )
    assert response.status_code == 201
    assert response.json()["primary_language"] == "Hindi"


def test_create_project_rejects_missing_title(client: TestClient) -> None:
    """Reject an invalid project brief before any persistence call."""
    response = client.post("/api/v1/projects", json={"genres": [], "languages": []})
    assert response.status_code == 422


def test_scene_update_requires_matching_if_match(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject stale scene edits without calling the persistence layer."""
    scene = Scene(id=7, act_id=4, heading="INT. HOUSE - DAY", version=3)
    act = Act(id=4, screenplay_id=2, position=0)
    screenplay = Screenplay(id=2, project_id=9, title="Story")

    async def get_scene(_session: _Session, _scene_id: int) -> Scene:
        """Return the versioned scene fixture."""
        return scene

    async def get_act(_session: _Session, _act_id: int) -> Act:
        """Return the owning act fixture."""
        return act

    async def get_screenplay(_session: _Session, _screenplay_id: int) -> Screenplay:
        """Return the owning screenplay fixture."""
        return screenplay

    monkeypatch.setattr("draftpilot.api.projects.scenes_crud.get", get_scene)
    monkeypatch.setattr("draftpilot.api.projects.acts_crud.get", get_act)
    monkeypatch.setattr("draftpilot.api.projects.screenplays_crud.get", get_screenplay)
    response = client.patch(
        "/api/v1/projects/9/scenes/7",
        headers={"If-Match": "2"},
        json={"body": "A changed room."},
    )
    assert response.status_code == 409


def test_translation_update_is_scoped_and_preserves_source(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Save a translation against a dialogue block without replacing source text."""
    scene = Scene(id=7, act_id=4, heading="INT. HOUSE - DAY", version=3)
    act = Act(id=4, screenplay_id=2, position=0)
    screenplay = Screenplay(id=2, project_id=9, title="Story")
    block = Block(id=11, scene_id=7, element_type=BlockType.DIALOGUE, text="We should go.")

    async def get_scene(_session: _Session, _scene_id: int) -> Scene:
        """Return the versioned scene fixture."""
        return scene

    async def get_block(_session: _Session, _block_id: int) -> Block:
        """Return the source dialogue fixture."""
        return block

    async def get_act(_session: _Session, _act_id: int) -> Act:
        """Return the owning act fixture."""
        return act

    async def get_screenplay(_session: _Session, _screenplay_id: int) -> Screenplay:
        """Return the owning screenplay fixture."""
        return screenplay

    async def upsert(_session: _Session, data: object) -> DialogueTranslation:
        """Return a persisted translation fixture."""
        return DialogueTranslation(
            id=21,
            block_id=getattr(data, "block_id"),
            language=getattr(data, "language"),
            text=getattr(data, "text"),
            source_version=getattr(data, "source_version"),
            status=getattr(data, "status"),
        )

    monkeypatch.setattr("draftpilot.api.projects.scenes_crud.get", get_scene)
    monkeypatch.setattr("draftpilot.api.projects.blocks_crud.get", get_block)
    monkeypatch.setattr("draftpilot.api.projects.acts_crud.get", get_act)
    monkeypatch.setattr("draftpilot.api.projects.screenplays_crud.get", get_screenplay)
    monkeypatch.setattr("draftpilot.api.projects.translations_crud.upsert", upsert)
    response = client.put(
        "/api/v1/projects/9/scenes/7/blocks/11/translations/Hindi",
        headers={"If-Match": "3"},
        json={"text": "हमें जाना चाहिए।", "status": "approved"},
    )
    assert response.status_code == 200
    assert response.json()["text"] == "हमें जाना चाहिए।"
    assert response.json()["source_version"] == 3
    assert block.text == "We should go."
