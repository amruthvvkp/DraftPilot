"""Test the server-authoritative capability discovery endpoint."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from draftpilot.api.capabilities import router


def test_capabilities_endpoint_returns_page_scoped_bundle() -> None:
    """Return only capabilities appropriate for the requested workflow page."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    response = TestClient(app).get("/api/v1/capabilities?page=/projects/7/timeline")

    assert response.status_code == 200
    names = {item["name"] for item in response.json()}
    assert "timeline.propose" in names
    assert "outline.read" not in names


def test_capabilities_endpoint_returns_full_catalog_without_page() -> None:
    """Return the complete public catalog when no page is supplied."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    response = TestClient(app).get("/api/v1/capabilities")

    assert response.status_code == 200
    assert any(item["name"] == "backups.restore" for item in response.json())
