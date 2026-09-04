"""Test project-scoped artifact dependency validation and invalidation."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from draftpilot.api.artifacts import router
from draftpilot.core.db import async_get_db
from draftpilot.crud import story_artifacts
from draftpilot.models import Project, StoryArtifact
from _async import run_async


class _Session:
    """Stand in for an isolated SQLModel session."""

    def __init__(self) -> None:
        """Initialize captured session operations."""
        self.added: list[object] = []
        self.commits = 0

    def add(self, value: object) -> None:
        """Capture a model scheduled for persistence."""
        self.added.append(value)

    async def commit(self) -> None:
        """Capture one transaction commit."""
        self.commits += 1

    async def refresh(self, _value: object) -> None:
        """Complete the fake refresh operation."""


def _client() -> tuple[TestClient, _Session]:
    """Build an artifact API client with an isolated session dependency."""
    app = FastAPI()
    session = _Session()

    async def dependency() -> AsyncGenerator[_Session, None]:
        """Yield the isolated session marker."""
        yield session

    app.dependency_overrides[async_get_db] = dependency
    app.include_router(router, prefix="/api/v1")
    return TestClient(app), session


def test_create_artifact_rejects_cross_project_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject dependencies that are not present in the requested project."""
    client, _session = _client()
    monkeypatch.setattr(
        "draftpilot.api.artifacts.projects_crud.get",
        AsyncMock(return_value=_project(9)),
    )
    monkeypatch.setattr(
        "draftpilot.api.artifacts.artifacts_crud.list_for_project",
        AsyncMock(return_value=_artifacts(StoryArtifact(id=5, project_id=9, kind="brief", title="Brief"))),
    )
    response = client.post(
        "/api/v1/projects/9/artifacts",
        json={"kind": "outline", "title": "Outline", "depends_on": [99]},
    )
    assert response.status_code == 422


def test_update_artifact_rejects_dependency_cycles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject an artifact update that would create a dependency cycle."""
    client, _session = _client()
    artifact = StoryArtifact(id=1, project_id=9, kind="brief", title="Brief", depends_on=[2])
    dependent = StoryArtifact(id=2, project_id=9, kind="outline", title="Outline", depends_on=[1])
    monkeypatch.setattr("draftpilot.api.artifacts.artifacts_crud.get", AsyncMock(return_value=artifact))
    monkeypatch.setattr(
        "draftpilot.api.artifacts.artifacts_crud.list_for_project",
        AsyncMock(return_value=_artifacts(artifact, dependent)),
    )
    response = client.patch(
        "/api/v1/projects/9/artifacts/1",
        headers={"If-Match": "1"},
        json={"depends_on": [2]},
    )
    assert response.status_code == 422


def test_mark_dependents_stale_propagates_transitively(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mark every downstream artifact stale when an upstream artifact changes."""
    artifacts = _artifacts(
        StoryArtifact(id=1, project_id=9, kind="brief", title="Brief"),
        StoryArtifact(id=2, project_id=9, kind="outline", title="Outline", depends_on=[1]),
        StoryArtifact(id=3, project_id=9, kind="timeline", title="Timeline", depends_on=[2]),
    )
    session = _Session()
    monkeypatch.setattr(story_artifacts, "list_for_project", AsyncMock(return_value=_artifacts(*artifacts)))
    stale_ids = run_async(story_artifacts.mark_dependents_stale(session, 9, [1]))
    assert stale_ids == [2, 3]
    assert all(artifact.stale for artifact in artifacts[1:])


def test_typed_story_operation_updates_artifact_and_preserves_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Apply a typed beat operation with optimistic versioning and durable metadata."""
    client, session = _client()
    artifact = StoryArtifact(id=1, project_id=9, kind="outline", title="Outline", version=2)
    monkeypatch.setattr("draftpilot.api.artifacts.artifacts_crud.get", AsyncMock(return_value=artifact))
    monkeypatch.setattr("draftpilot.api.artifacts.artifacts_crud.mark_dependents_stale", AsyncMock())
    monkeypatch.setattr("draftpilot.api.artifacts._enqueue_index", AsyncMock())
    response = client.post(
        "/api/v1/projects/9/artifacts/1/operations",
        headers={"If-Match": "2"},
        json={
            "operation": "add_beat",
            "payload": {
                "title": "The door opens",
                "summary": "Mira discovers the hidden room.",
                "sequence": 1,
                "causal_predecessor_ids": [],
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["version"] == 3
    assert response.json()["artifact_metadata"]["beats"][0]["title"] == "The door opens"
    assert response.json()["artifact_metadata"]["operations"][0]["operation"] == "add_beat"
    assert session.commits == 1


def test_typed_story_operation_rejects_wrong_artifact_kind() -> None:
    """Reject an operation that does not match the artifact's semantic kind."""
    from draftpilot.core.story_operations import validate_story_operation

    with pytest.raises(ValueError, match="not valid"):
        validate_story_operation("canon", "add_beat", {"title": "Beat", "summary": "Text", "sequence": 1})


def _project(project_id: int) -> Project:
    """Return a project fixture for the requested identifier."""
    return Project(id=project_id, title="Story")


def _artifacts(*artifacts: StoryArtifact) -> list[StoryArtifact]:
    """Return artifact fixtures as a fresh list."""
    return list(artifacts)
