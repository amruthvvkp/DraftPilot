"""Test typed context-generation workflow discovery and scheduling."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from draftpilot.api.context_workflows import router
from draftpilot.core.db import async_get_db
from draftpilot.models import KnowledgeNode, Project, StoryArtifact, WorkflowRun


class _Session:
    """Stand in for an isolated database session."""


class _Pool:
    """Capture one queued context workflow."""

    def __init__(self) -> None:
        """Initialize captured jobs."""
        self.jobs: list[tuple[str, int | None]] = []

    async def enqueue_job(self, name: str, run_id: int | None) -> None:
        """Capture a durable worker job."""
        self.jobs.append((name, run_id))


def _client() -> TestClient:
    """Build a context-workflow client with an isolated session dependency."""
    app = FastAPI()

    async def dependency() -> AsyncGenerator[_Session, None]:
        """Yield the isolated session marker."""
        yield _Session()

    app.dependency_overrides[async_get_db] = dependency
    app.include_router(router, prefix="/api/v1")
    return TestClient(app)


def test_context_workflow_catalog_exposes_context_generation_contract() -> None:
    """List the reusable visual, research, and continuity workflows."""
    response = _client().get("/api/v1/projects/7/context/workflows")

    assert response.status_code == 200
    keys = {item["key"] for item in response.json()}
    assert {"reference_scene", "visual_language", "camera", "lighting", "color_palette", "film_director_style", "continuity"} <= keys


def test_context_workflow_rejects_incompatible_source_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject a source artifact outside the workflow's declared input scope."""
    monkeypatch.setattr(
        "draftpilot.api.context_workflows.projects_crud.get",
        AsyncMock(return_value=Project(id=7, title="Story")),
    )
    monkeypatch.setattr(
        "draftpilot.api.context_workflows.artifacts_crud.get",
        AsyncMock(return_value=StoryArtifact(id=3, project_id=7, kind="character", title="Mira")),
    )

    response = _client().post(
        "/api/v1/projects/7/context/workflows/runs",
        json={"workflow": "camera", "artifact_id": 3, "instruction": "Plan the opening coverage.", "max_attempts": 5},
    )

    assert response.status_code == 422


def test_context_workflow_persists_source_version_and_enqueues_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persist the source contract and enqueue a reconnectable context run."""
    pool = _Pool()
    captured: list[WorkflowRun] = []
    artifact = StoryArtifact(id=3, project_id=7, kind="outline", title="Outline", version=4)
    monkeypatch.setattr(
        "draftpilot.api.context_workflows.projects_crud.get",
        AsyncMock(return_value=Project(id=7, title="Story")),
    )
    monkeypatch.setattr("draftpilot.api.context_workflows.artifacts_crud.get", AsyncMock(return_value=artifact))

    async def create(_session: object, data: object) -> WorkflowRun:
        """Capture and return a durable run fixture."""
        run = WorkflowRun(id=44, **data.model_dump())
        captured.append(run)
        return run

    async def get_pool() -> _Pool:
        """Return the isolated queue fixture."""
        return pool

    monkeypatch.setattr("draftpilot.api.context_workflows.runs_crud.create", create)
    monkeypatch.setattr("draftpilot.api.context_workflows.get_arq_pool", get_pool)
    response = _client().post(
        "/api/v1/projects/7/context/workflows/runs",
        json={"workflow": "camera", "artifact_id": 3, "instruction": "Plan the opening coverage.", "max_attempts": 5},
    )

    assert response.status_code == 202
    assert captured[0].input["source_version"] == 4
    assert captured[0].permission_mode == "suggest"
    assert captured[0].max_attempts == 5
    assert pool.jobs == [("execute_workflow", 44)]


def test_context_suggestion_apply_is_explicit_provenance_linked_and_version_checked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Apply a completed suggestion only against the source version it reviewed."""
    run = WorkflowRun(
        id=44,
        project_id=7,
        kind="context_generation",
        status="succeeded",
        input={"artifact_id": 3},
        result={"suggestion": "Use a long lens.", "output_kind": "camera", "source_version": 4, "citations": []},
    )
    node = KnowledgeNode(id=51, project_id=7, kind="camera", label="Camera from run 44", description="Use a long lens.")
    updated: list[tuple[WorkflowRun, str]] = []

    monkeypatch.setattr("draftpilot.core.context_operations.runs_crud.get", AsyncMock(return_value=run))
    monkeypatch.setattr("draftpilot.core.context_operations.artifacts_crud.get", AsyncMock(return_value=StoryArtifact(id=3, project_id=7, kind="outline", title="Outline", version=4)))
    monkeypatch.setattr("draftpilot.core.context_operations.graph_crud.create_node", AsyncMock(return_value=node))

    async def update_status(_session: object, item: WorkflowRun, state: str, result: object = None, error: str = None) -> WorkflowRun:
        """Capture the explicit applied transition."""
        updated.append((item, state))
        return item

    monkeypatch.setattr("draftpilot.core.context_operations.runs_crud.update_status", update_status)
    response = _client().post(
        "/api/v1/projects/7/context/workflows/runs/44/apply",
        json={"expected_source_version": 4},
    )

    assert response.status_code == 200
    assert response.json()["id"] == 51
    assert updated == [(run, "applied")]
    assert run.result is not None and run.result["applied_node_id"] == 51


def test_context_suggestion_apply_rejects_a_changed_source_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject a suggestion when the reviewed source changed before approval."""
    run = WorkflowRun(
        id=44,
        project_id=7,
        kind="context_generation",
        status="succeeded",
        input={"artifact_id": 3},
        result={"suggestion": "Use a long lens.", "output_kind": "camera", "source_version": 4},
    )
    monkeypatch.setattr("draftpilot.core.context_operations.runs_crud.get", AsyncMock(return_value=run))
    monkeypatch.setattr("draftpilot.core.context_operations.artifacts_crud.get", AsyncMock(return_value=StoryArtifact(id=3, project_id=7, kind="outline", title="Outline", version=5)))

    response = _client().post(
        "/api/v1/projects/7/context/workflows/runs/44/apply",
        json={"expected_source_version": 4},
    )

    assert response.status_code == 409
