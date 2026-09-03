"""Project-scoped knowledge graph REST endpoints."""

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.db import async_get_db
from draftpilot.crud import knowledge_graph as graph_crud
from draftpilot.crud import projects as projects_crud
from draftpilot.models import KnowledgeEdge, KnowledgeEdgeRead, KnowledgeNodeBase, KnowledgeNodeCreate, KnowledgeNodeRead

router = APIRouter(prefix="/projects/{project_id}/knowledge-graph", tags=["knowledge-graph"])


class GraphRead(BaseModel):
    """Return the complete project-scoped graph payload."""

    nodes: list[KnowledgeNodeRead] = Field(default_factory=list)
    edges: list[dict[str, object]] = Field(default_factory=list)


class EdgeRequest(BaseModel):
    """Accept an edge after the server validates both node owners."""

    source_node_id: int
    target_node_id: int
    relation: str = Field(min_length=1, max_length=100)
    edge_metadata: dict[str, object] = Field(default_factory=dict)


class NodeRequest(KnowledgeNodeBase):
    """Accept a graph node while taking project scope from the URL."""


class NodeUpdate(BaseModel):
    """Describe an optimistic edit to one canonical graph node."""

    label: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    node_metadata: dict[str, object] | None = None


@router.get("", response_model=GraphRead)
async def get_graph(
    project_id: int, session: AsyncSession = Depends(async_get_db)
) -> GraphRead:
    """Return project nodes and edges without leaking cross-project records."""
    if await projects_crud.get(session, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    nodes = await graph_crud.list_nodes(session, project_id)
    edges = await graph_crud.list_edges(session, project_id)
    return GraphRead(
        nodes=[KnowledgeNodeRead.model_validate(node) for node in nodes],
        edges=[KnowledgeEdgeRead.model_validate(edge).model_dump(mode="json") for edge in edges],
    )


@router.post("/nodes", response_model=KnowledgeNodeRead, status_code=status.HTTP_201_CREATED)
async def create_node(
    project_id: int,
    data: NodeRequest,
    session: AsyncSession = Depends(async_get_db),
) -> KnowledgeNodeRead:
    """Create a node only inside the requested project."""
    if await projects_crud.get(session, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    node = await graph_crud.create_node(
        session, KnowledgeNodeCreate(project_id=project_id, **data.model_dump())
    )
    return KnowledgeNodeRead.model_validate(node)


@router.patch("/nodes/{node_id}", response_model=KnowledgeNodeRead)
async def update_node(
    project_id: int,
    node_id: int,
    data: NodeUpdate,
    session: AsyncSession = Depends(async_get_db),
    if_match: int | None = Header(default=None, alias="If-Match"),
) -> KnowledgeNodeRead:
    """Update a project node only when its version is current."""
    node = await graph_crud.get_node(session, node_id)
    if node is None or node.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Graph node not found")
    if if_match is None:
        raise HTTPException(status_code=status.HTTP_428_PRECONDITION_REQUIRED, detail="If-Match is required")
    if if_match != node.version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Graph node has changed")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(node, key, value)
    node.version += 1
    session.add(node)
    await session.commit()
    await session.refresh(node)
    return KnowledgeNodeRead.model_validate(node)


@router.post("/edges", response_model=KnowledgeEdgeRead, status_code=status.HTTP_201_CREATED)
async def create_edge(
    project_id: int,
    data: EdgeRequest,
    session: AsyncSession = Depends(async_get_db),
) -> KnowledgeEdgeRead:
    """Create an edge only when both endpoint nodes belong to the project."""
    source = await graph_crud.get_node(session, data.source_node_id)
    target = await graph_crud.get_node(session, data.target_node_id)
    if source is None or target is None or source.project_id != project_id or target.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Graph node not found")
    edge = await graph_crud.create_edge(
        session,
        KnowledgeEdge(
            project_id=project_id,
            source_node_id=data.source_node_id,
            target_node_id=data.target_node_id,
            relation=data.relation,
            edge_metadata=data.edge_metadata,
        ),
    )
    return KnowledgeEdgeRead.model_validate(edge)
