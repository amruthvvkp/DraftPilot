"""Test project-scoped typed-reference mutations."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from draftpilot.api.projects import router
from draftpilot.core.db import async_get_db
from draftpilot.models import ProjectReference


class _Session:
    """Provide the async session methods used by reference endpoints."""

    def add(self, _value: object) -> None:
        """Accept a staged reference."""

    async def commit(self) -> None:
        """Commit the staged reference."""

    async def refresh(self, _value: object) -> None:
        """Refresh the reference fixture."""

    async def delete(self, _value: object) -> None:
        """Accept a reference deletion."""


@pytest.fixture
def client() -> TestClient:
    """Build a reference API client with an isolated session marker."""
    app = FastAPI()
    session = _Session()

    async def dependency() -> AsyncGenerator[_Session]:
        """Yield the isolated session marker."""
        yield session

    app.dependency_overrides[async_get_db] = dependency
    app.include_router(router, prefix="/api/v1")
    return TestClient(app)


def test_reference_update_requires_current_version(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject a stale typed-reference edit without persistence."""
    reference = ProjectReference(id=4, project_id=7, kind="film", label="Old", version=2)
    monkeypatch.setattr("draftpilot.api.projects.references_crud.get", AsyncMock(return_value=reference))
    response = client.patch(
        "/api/v1/projects/7/references/4", headers={"If-Match": "1"}, json={"label": "New"}
    )
    assert response.status_code == 409


def test_reference_update_is_project_scoped_and_versioned(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Update a typed reference and advance its optimistic version."""
    reference = ProjectReference(id=4, project_id=7, kind="film", label="Old", version=2)
    monkeypatch.setattr("draftpilot.api.projects.references_crud.get", AsyncMock(return_value=reference))
    monkeypatch.setattr("draftpilot.api.projects._enqueue_rag_index", AsyncMock())
    response = client.patch(
        "/api/v1/projects/7/references/4", headers={"If-Match": "2"}, json={"label": "New"}
    )
    assert response.status_code == 200
    assert response.json()["version"] == 3
    assert reference.label == "New"


def test_reference_mutations_reject_other_projects(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Prevent cross-project reference reads and deletes."""
    reference = ProjectReference(id=4, project_id=8, kind="film", label="Private")
    monkeypatch.setattr("draftpilot.api.projects.references_crud.get", AsyncMock(return_value=reference))
    assert client.get("/api/v1/projects/7/references/4").status_code == 405
    assert client.delete("/api/v1/projects/7/references/4").status_code == 404
