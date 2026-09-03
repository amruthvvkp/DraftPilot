"""Test project-scoped knowledge graph ownership and persistence."""

from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from draftpilot.api.knowledge_graph import router
from draftpilot.core.db import async_get_db
from draftpilot.models import KnowledgeNode, KnowledgeNodeCreate, Project


class _Session:
    """Stand in for a database session in graph tests."""


def test_graph_rejects_cross_project_edge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prevent an edge from connecting nodes owned by different projects."""
    app = FastAPI()

    async def session() -> AsyncGenerator[_Session, None]:
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
