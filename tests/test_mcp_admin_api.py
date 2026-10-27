"""Test authentication for MCP grant administration."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from draftpilot.api.mcp_access import router
from draftpilot.core.db import async_get_db
from draftpilot.models import MCPClient, MCPGrant, Project


class _Session:
    """Stand in for an isolated database session."""

    def __init__(self, grant: MCPGrant | None = None) -> None:
        """Store the grant returned by the isolated session."""
        self.grant = grant
        self.deleted: MCPGrant | None = None
        self.commits = 0

    async def get(self, _model: object, _identifier: int) -> MCPGrant | None:
        """Return the requested isolated grant."""
        return self.grant

    async def delete(self, grant: MCPGrant) -> None:
        """Capture the revoked grant."""
        self.deleted = grant

    async def commit(self) -> None:
        """Capture the revocation transaction."""
        self.commits += 1


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


def test_mcp_grant_revocation_is_project_scoped() -> None:
    """Revoke a grant only when its project matches the requested scope."""
    session = _Session(MCPGrant(id=4, client_id=3, project_id=7, capability="context.read"))
    app = FastAPI()

    async def dependency():
        """Yield the isolated session marker."""
        yield session

    app.dependency_overrides[async_get_db] = dependency
    app.include_router(router, prefix="/api/v1")
    client = TestClient(app)
    response = client.delete(
        "/api/v1/mcp/projects/7/grants/4",
        headers={"Authorization": "Bearer draftpilot-local-admin-token"},
    )
    assert response.status_code == 204
    assert session.deleted is session.grant
    assert session.commits == 1

    foreign = _Session(MCPGrant(id=4, client_id=3, project_id=8, capability="context.read"))
    async def foreign_dependency() -> AsyncGenerator[_Session]:
        """Yield the foreign-project grant fixture."""
        yield foreign

    app.dependency_overrides[async_get_db] = foreign_dependency
    assert client.delete(
        "/api/v1/mcp/projects/7/grants/4",
        headers={"Authorization": "Bearer draftpilot-local-admin-token"},
    ).status_code == 404
