"""Test the project-scoped Monty audit endpoint."""

from collections.abc import AsyncGenerator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from draftpilot.api.monty import router
from draftpilot.core.db import async_get_db
from draftpilot.models import MontyExecution, Project


class _Session:
    """Stand in for the database session in endpoint tests."""


def test_list_monty_executions_returns_redacted_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return persisted audit fields without source code or inputs."""
    app = FastAPI()

    async def session() -> AsyncGenerator[_Session]:
        """Yield an isolated database marker."""
        yield _Session()

    app.dependency_overrides[async_get_db] = session
    app.include_router(router, prefix="/api/v1")
    record = MontyExecution(
        id=4,
        project_id=7,
        code_sha256="a" * 64,
        input_count=2,
        output_chars=8,
        duration_ms=12,
    )

    async def get(_session: _Session, project_id: int) -> Project | None:
        """Return the project fixture only for its expected identifier."""
        return Project(id=7, title="Story") if project_id == 7 else None

    async def list_for_project(_session: _Session, project_id: int) -> list[MontyExecution]:
        """Return the redacted audit fixture."""
        return [record] if project_id == 7 else []

    monkeypatch.setattr("draftpilot.api.monty.projects_crud.get", get)
    monkeypatch.setattr("draftpilot.api.monty.executions_crud.list_for_project", list_for_project)
    response = TestClient(app).get("/api/v1/projects/7/monty-executions")
    assert response.status_code == 200
    assert response.json()[0]["code_sha256"] == "a" * 64
    assert "code" not in response.json()[0]
    assert "inputs" not in response.json()[0]
