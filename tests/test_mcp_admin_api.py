"""Test authentication for MCP grant administration."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from draftpilot.api.mcp_access import router
from draftpilot.core.db import async_get_db
from draftpilot.models import MCPClient, Project


class _Session:
    """Stand in for an isolated database session."""


def test_mcp_client_registration_requires_admin_bearer() -> None:
    """Reject unauthenticated attempts to register an external client."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    response = TestClient(app).post(
        "/api/v1/mcp/clients",
        json={"client_id": "writer-tool", "name": "Writer Tool"},
    )
    assert response.status_code == 401


def test_mcp_grant_rejects_capability_outside_server_catalog(monkeypatch) -> None:
    """Reject an unknown capability before persisting an external grant."""
    app = FastAPI()

    async def dependency():
        """Yield the isolated session marker."""
        yield _Session()

    app.dependency_overrides[async_get_db] = dependency
    app.include_router(router, prefix="/api/v1")
    monkeypatch.setattr("draftpilot.api.mcp_access.projects_crud.get", AsyncMock(return_value=Project(id=7, title="Story")))
    monkeypatch.setattr("draftpilot.api.mcp_access.access_crud.get_client", AsyncMock(return_value=MCPClient(id=3, client_id="writer", name="Writer")))
    response = TestClient(app).post(
        "/api/v1/mcp/projects/7/grants",
        headers={"Authorization": "Bearer draftpilot-local-admin-token"},
        json={"client_id": "writer", "capability": "database.raw_access"},
    )
    assert response.status_code == 422
