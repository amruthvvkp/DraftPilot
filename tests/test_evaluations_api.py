"""Test project-scoped evaluation result endpoints."""

from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.testclient import TestClient

from draftpilot.api.evaluations import router
from draftpilot.core.db import async_get_db
from draftpilot.models import EvaluationResult, Project, Screenplay, WorkflowRun


class _Session:
    """Stand in for an async SQLModel session in API tests."""


def test_create_and_list_evaluations_are_project_scoped(monkeypatch: object) -> None:
    """Persist and return typed findings without crossing project boundaries."""
    app = FastAPI()

    async def session() -> AsyncGenerator[_Session]:
        """Yield an isolated session marker."""
        yield _Session()

    app.dependency_overrides[async_get_db] = session
    app.include_router(router, prefix="/api/v1")
    project = Project(id=9, title="Story")
    evaluation = EvaluationResult(
        id=4,
        project_id=9,
        evaluator="continuity_supervisor",
        score=0.8,
        summary="One unresolved prop handoff.",
        findings={"continuity": ["Lantern appears before it is acquired."]},
    )

    async def get_project(_session: _Session, project_id: int) -> Project | None:
        """Return only the requested project fixture."""
        return project if project_id == 9 else None

    async def create(_session: _Session, _result: EvaluationResult) -> EvaluationResult:
        """Return the persisted evaluation fixture."""
        return evaluation

    async def list_for_project(_session: _Session, project_id: int) -> list[EvaluationResult]:
        """Return evaluations for the requested project."""
        return [evaluation] if project_id == 9 else []

    monkeypatch.setattr("draftpilot.api.evaluations.projects_crud.get", get_project)
    monkeypatch.setattr("draftpilot.api.evaluations.evaluations_crud.create", create)
    monkeypatch.setattr("draftpilot.api.evaluations.evaluations_crud.list_for_project", list_for_project)
    client = TestClient(app)
    created = client.post(
        "/api/v1/projects/9/evaluations",
        json={
            "target_kind": "screenplay",
            "evaluator": "continuity_supervisor",
            "score": 0.8,
            "summary": "One unresolved prop handoff.",
            "findings": {"continuity": ["Lantern appears before it is acquired."]},
        },
    )
    assert created.status_code == 201
    assert created.json()["project_id"] == 9
    assert created.json()["findings"]["continuity"]

    listed = client.get("/api/v1/projects/9/evaluations")
    assert listed.status_code == 200
    assert listed.json()[0]["evaluator"] == "continuity_supervisor"
    assert client.get("/api/v1/projects/10/evaluations").status_code == 404


def test_start_evaluation_validates_screenplay_and_enqueues_run(monkeypatch: object) -> None:
    """Create a reconnectable evaluation run only for the project screenplay."""
    app = FastAPI()

    async def session() -> AsyncGenerator[_Session]:
        """Yield an isolated session marker."""
        yield _Session()

    app.dependency_overrides[async_get_db] = session
    app.include_router(router, prefix="/api/v1")
    captured: list[object] = []

    async def get_project(_session: _Session, _project_id: int) -> Project:
        """Return the project fixture."""
        return Project(id=9, title="Story")

    async def get_screenplay(_session: _Session, _screenplay_id: int) -> Screenplay:
        """Return the owning screenplay fixture."""
        return Screenplay(id=2, project_id=9, title="Story")

    async def create_run(_session: _Session, data: object) -> WorkflowRun:
        """Capture and return the queued evaluation run."""
        captured.append(data)
        return WorkflowRun(id=8, project_id=9, kind="evaluation")

    class Pool:
        """Capture queue submission without Redis."""

        async def enqueue_job(self, name: str, run_id: int | None) -> None:
            """Verify the durable run is queued by id."""
            assert (name, run_id) == ("execute_workflow", 8)

    async def get_pool() -> Pool:
        """Return the queue fixture."""
        return Pool()

    monkeypatch.setattr("draftpilot.api.evaluations.projects_crud.get", get_project)
    monkeypatch.setattr("draftpilot.api.evaluations.screenplays_crud.get", get_screenplay)
    monkeypatch.setattr("draftpilot.api.evaluations.runs_crud.create", create_run)
    monkeypatch.setattr("draftpilot.api.evaluations.get_arq_pool", get_pool)
    response = TestClient(app).post(
        "/api/v1/projects/9/evaluations/runs",
        json={"screenplay_id": 2, "evaluator": "continuity_supervisor", "max_attempts": 4},
    )
    assert response.status_code == 202
    assert response.json()["kind"] == "evaluation"
    assert captured[0].input["evaluator"] == "continuity_supervisor"  # type: ignore[union-attr]
    assert captured[0].max_attempts == 4  # type: ignore[union-attr]
