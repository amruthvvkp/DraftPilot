"""Test project-scoped knowledge graph ownership and persistence."""

from collections.abc import AsyncGenerator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from draftpilot.api.knowledge_graph import router
from draftpilot.core.db import async_get_db
from draftpilot.models import KnowledgeEdge, KnowledgeNode, KnowledgeNodeCreate, Project


class _Session:
    """Stand in for a database session in graph tests."""


def test_graph_rejects_cross_project_edge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prevent an edge from connecting nodes owned by different projects."""
    app = FastAPI()

    async def session() -> AsyncGenerator[_Session]:
        """Yield an isolated database marker."""
        yield _Session()

    app.dependency_overrides[async_get_db] = session
    app.include_router(router, prefix="/api/v1")
    project = Project(id=5, title="Graph story")
    source = KnowledgeNode(id=1, project_id=5, kind="character", label="Mira")
    foreign = KnowledgeNode(id=2, project_id=99, kind="character", label="Other")

    async def get_project(_session: _Session, _project_id: int) -> Project:
        """Return the project fixture."""
        return project

    async def get_node(_session: _Session, node_id: int) -> KnowledgeNode:
        """Return nodes with intentionally different owners."""
        return source if node_id == 1 else foreign

    async def create_node(_session: _Session, data: KnowledgeNodeCreate) -> KnowledgeNode:
        """Return a validated node fixture."""
        return KnowledgeNode(id=1, project_id=data.project_id, kind=data.kind, label=data.label)

    monkeypatch.setattr("draftpilot.api.knowledge_graph.projects_crud.get", get_project)
    monkeypatch.setattr("draftpilot.api.knowledge_graph.graph_crud.get_node", get_node)
    monkeypatch.setattr("draftpilot.api.knowledge_graph.graph_crud.create_node", create_node)
    node_response = TestClient(app).post(
        "/api/v1/projects/5/knowledge-graph/nodes",
        json={"kind": "character", "label": "Mira"},
    )
    assert node_response.status_code == 201
    edge_response = TestClient(app).post(
        "/api/v1/projects/5/knowledge-graph/edges",
        json={"source_node_id": 1, "target_node_id": 2, "relation": "knows"},
    )
    assert edge_response.status_code == 404


def test_graph_node_update_rejects_stale_version(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reject an outdated canonical-node edit before persistence."""
    app = FastAPI()

    async def session() -> AsyncGenerator[_Session]:
        """Yield an isolated session marker."""
        yield _Session()

    app.dependency_overrides[async_get_db] = session
    app.include_router(router, prefix="/api/v1")
    node = KnowledgeNode(id=1, project_id=5, kind="character", label="Mira", version=3)

    async def get_node(_session: _Session, _node_id: int) -> KnowledgeNode:
        """Return the current node version."""
        return node

    monkeypatch.setattr("draftpilot.api.knowledge_graph.graph_crud.get_node", get_node)
    response = TestClient(app).patch(
        "/api/v1/projects/5/knowledge-graph/nodes/1",
        headers={"If-Match": "2"},
        json={"label": "Mira revised"},
    )
    assert response.status_code == 409


def test_graph_mutations_enqueue_project_scoped_rag_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refresh RAG after committed node and edge mutations."""
    app = FastAPI()

    async def session() -> AsyncGenerator[_Session]:
        """Yield an isolated database marker."""
        yield _Session()

    app.dependency_overrides[async_get_db] = session
    app.include_router(router, prefix="/api/v1")
    project = Project(id=5, title="Graph story")
    node = KnowledgeNode(id=1, project_id=5, kind="film", label="Reference", version=2)
    edge = KnowledgeEdge(id=8, project_id=5, source_node_id=1, target_node_id=1, relation="echoes")
    indexed: list[tuple[str, str, int]] = []

    async def get_project(_session: _Session, _project_id: int) -> Project:
        """Return the project fixture."""
        return project

    async def create_node(_session: _Session, _data: KnowledgeNodeCreate) -> KnowledgeNode:
        """Return the committed node fixture."""
        return node

    async def get_node(_session: _Session, _node_id: int) -> KnowledgeNode:
        """Return the authorized node fixture for both edge endpoints."""
        return node

    async def create_edge(_session: _Session, _edge: KnowledgeEdge) -> KnowledgeEdge:
        """Return the committed edge fixture."""
        return edge

    async def enqueue(project_id: int, source_id: str, _kind: str, _text: str, version: int) -> None:
        """Capture the RAG refresh request."""
        indexed.append((source_id, str(project_id), version))

    monkeypatch.setattr("draftpilot.api.knowledge_graph.projects_crud.get", get_project)
    monkeypatch.setattr("draftpilot.api.knowledge_graph.graph_crud.create_node", create_node)
    monkeypatch.setattr("draftpilot.api.knowledge_graph.graph_crud.get_node", get_node)
    monkeypatch.setattr("draftpilot.api.knowledge_graph.graph_crud.create_edge", create_edge)
    monkeypatch.setattr("draftpilot.api.knowledge_graph._enqueue_index", enqueue)

    client = TestClient(app)
    assert client.post(
        "/api/v1/projects/5/knowledge-graph/nodes",
        json={"kind": "film", "label": "Reference"},
    ).status_code == 201
    assert client.post(
        "/api/v1/projects/5/knowledge-graph/edges",
        json={"source_node_id": 1, "target_node_id": 1, "relation": "echoes"},
    ).status_code == 201
    assert indexed == [("knowledge_node:1", "5", 2), ("knowledge_edge:8", "5", 1)]


def test_graph_edge_delete_is_project_scoped_and_refreshes_rag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete an owned graph edge and remove its indexed representation."""
    app = FastAPI()

    async def session() -> AsyncGenerator[_Session]:
        """Yield an isolated session marker."""
        yield _Session()

    app.dependency_overrides[async_get_db] = session
    app.include_router(router, prefix="/api/v1")
    edge = KnowledgeEdge(id=8, project_id=5, source_node_id=1, target_node_id=2, relation="inspires")
    deleted: list[int] = []
    indexed: list[tuple[int, str]] = []

    async def get_edge(_session: _Session, _edge_id: int) -> KnowledgeEdge:
        """Return the owned edge fixture."""
        return edge

    async def delete_edge(_session: _Session, value: KnowledgeEdge) -> None:
        """Capture deletion of the owned edge."""
        deleted.append(value.id or 0)

    async def enqueue(project_id: int, source_id: str) -> None:
        """Capture the RAG deletion request."""
        indexed.append((project_id, source_id))

    monkeypatch.setattr("draftpilot.api.knowledge_graph.graph_crud.get_edge", get_edge)
    monkeypatch.setattr("draftpilot.api.knowledge_graph.graph_crud.delete_edge", delete_edge)
    monkeypatch.setattr("draftpilot.api.knowledge_graph._enqueue_delete", enqueue)
    response = TestClient(app).delete("/api/v1/projects/5/knowledge-graph/edges/8")
    assert response.status_code == 204
    assert deleted == [8]
    assert indexed == [(5, "knowledge_edge:8")]
