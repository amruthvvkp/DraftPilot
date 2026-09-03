"""Test the versioned project REST boundary without a live database."""

from collections.abc import AsyncGenerator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from draftpilot.api.projects import router
from draftpilot.core.db import async_get_db
from draftpilot.models import Project


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
