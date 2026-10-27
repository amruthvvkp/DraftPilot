"""CRUD operations for project knowledge graph nodes and edges."""

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.models import KnowledgeEdge, KnowledgeNode, KnowledgeNodeCreate


async def list_nodes(session: AsyncSession, project_id: int) -> list[KnowledgeNode]:
    """Return project nodes in stable label order."""
    result = await session.exec(
        select(KnowledgeNode).where(KnowledgeNode.project_id == project_id).order_by(col(KnowledgeNode.label))
    )
    return list(result.all())


async def list_edges(session: AsyncSession, project_id: int) -> list[KnowledgeEdge]:
    """Return only edges belonging to the requested project."""
    result = await session.exec(
        select(KnowledgeEdge).where(KnowledgeEdge.project_id == project_id).order_by(col(KnowledgeEdge.id))
    )
    return list(result.all())


async def get_node(session: AsyncSession, node_id: int) -> KnowledgeNode | None:
    """Return one graph node by identifier."""
    return await session.get(KnowledgeNode, node_id)


async def create_node(session: AsyncSession, data: KnowledgeNodeCreate) -> KnowledgeNode:
    """Persist one graph node."""
    node = KnowledgeNode.model_validate(data)
    session.add(node)
    await session.commit()
    await session.refresh(node)
    return node


async def create_edge(session: AsyncSession, edge: KnowledgeEdge) -> KnowledgeEdge:
    """Persist one validated graph edge."""
    session.add(edge)
    await session.commit()
    await session.refresh(edge)
    return edge


async def get_edge(session: AsyncSession, edge_id: int) -> KnowledgeEdge | None:
    """Return one graph edge by identifier."""
    return await session.get(KnowledgeEdge, edge_id)


async def delete_edge(session: AsyncSession, edge: KnowledgeEdge) -> None:
    """Delete one graph edge after its project scope is validated."""
    await session.delete(edge)
    await session.commit()
