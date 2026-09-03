"""Test the isolated project retrieval service."""

from fastapi.testclient import TestClient

from draftpilot.rag_service import app, index


def test_rag_requires_auth_and_returns_project_scoped_citations() -> None:
    """Require authentication and isolate search results by project."""
    index.delete(1, "brief")
    index.delete(2, "brief")
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}
    assert client.post("/projects/1/search", json={"query": "hero"}).status_code == 401
    headers = {"Authorization": "Bearer draftpilot-local-token"}
    assert client.post(
        "/projects/1/documents",
        json={"source_id": "brief", "source_kind": "brief", "text": "A hero returns.", "content_version": 3},
        headers=headers,
    ).status_code == 204
    assert client.post(
        "/projects/2/documents",
        json={"source_id": "brief", "source_kind": "brief", "text": "A hero waits.", "content_version": 1},
        headers=headers,
    ).status_code == 204
    response = client.post("/projects/1/search", json={"query": "hero"}, headers=headers)
    assert response.status_code == 200
    assert response.json()["results"][0]["citation"] == {
        "project_id": 1,
        "source_id": "brief",
        "source_kind": "brief",
        "content_version": 3,
    }
