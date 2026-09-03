"""Test authentication for MCP grant administration."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from draftpilot.api.mcp_access import router


def test_mcp_client_registration_requires_admin_bearer() -> None:
    """Reject unauthenticated attempts to register an external client."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    response = TestClient(app).post(
        "/api/v1/mcp/clients",
        json={"client_id": "writer-tool", "name": "Writer Tool"},
    )
    assert response.status_code == 401
