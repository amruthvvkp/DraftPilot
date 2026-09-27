"""Test the isolated retrieval service over its HTTP contract."""

from fastapi.testclient import TestClient

from draftpilot.rag_service import app

HEADERS = {"Authorization": "Bearer draftpilot-local-token"}


def test_rag_requires_auth_and_returns_project_scoped_citations() -> None:
    """Require the service token, chunk on upsert, and isolate search results by project."""
    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"
        assert client.post("/projects/1/search", json={"query": "hero"}).status_code == 401
        indexed = client.post(
            "/projects/1/documents",
            json={"source_id": "brief", "source_kind": "brief", "text": "A hero returns.", "content_version": 3},
            headers=HEADERS,
        )
        assert indexed.status_code == 200 and indexed.json() == {"chunks": 1}
        client.post(
            "/projects/2/documents",
            json={"source_id": "brief", "source_kind": "brief", "text": "A hero waits.", "content_version": 1},
            headers=HEADERS,
        )
        response = client.post("/projects/1/search", json={"query": "hero"}, headers=HEADERS)
        assert response.status_code == 200
        citation = response.json()["results"][0]["citation"]
        assert (citation["project_id"], citation["source_id"], citation["content_version"]) == (1, "brief", 3)
        assert client.get("/projects/1/stats", headers=HEADERS).json()["documents"] >= 1
        assert client.delete("/projects/1/documents/brief", headers=HEADERS).status_code == 204
        assert client.post("/projects/1/search", json={"query": "hero"}, headers=HEADERS).json()["results"] == []
