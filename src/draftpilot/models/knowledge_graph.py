"""Project-scoped knowledge graph node and edge models."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime
from sqlmodel import Field, SQLModel

from draftpilot.models.base import _utcnow


class KnowledgeNodeBase(SQLModel):
    """Share fields for one creative knowledge graph node."""

    kind: str = Field(max_length=60)
    label: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    node_metadata: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    version: int = Field(default=1, ge=1)


class KnowledgeNode(KnowledgeNodeBase, table=True):  # type: ignore[call-arg]
    """Store a versioned project knowledge graph node."""

    __tablename__ = "knowledge_node"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    created_at: datetime = Field(default_factory=_utcnow, sa_type=DateTime(timezone=True))  # type: ignore[call-overload]
    updated_at: datetime = Field(default_factory=_utcnow, sa_type=DateTime(timezone=True))  # type: ignore[call-overload]


class KnowledgeEdgeBase(SQLModel):
    """Share fields for one directed creative graph relationship."""

    relation: str = Field(min_length=1, max_length=100)
    edge_metadata: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)


class KnowledgeEdge(KnowledgeEdgeBase, table=True):  # type: ignore[call-arg]
    """Store one project-scoped relationship between graph nodes."""

    __tablename__ = "knowledge_edge"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    source_node_id: int = Field(foreign_key="knowledge_node.id", index=True)
    target_node_id: int = Field(foreign_key="knowledge_node.id", index=True)
    created_at: datetime = Field(default_factory=_utcnow, sa_type=DateTime(timezone=True))  # type: ignore[call-overload]


class KnowledgeNodeCreate(KnowledgeNodeBase):
    """Describe a node before persistence."""

    project_id: int


class KnowledgeNodeRead(KnowledgeNodeBase):
    """Return a persisted node with project scope and timestamps."""

    id: int
    project_id: int
    created_at: datetime
    updated_at: datetime


class KnowledgeEdgeCreate(KnowledgeEdgeBase):
    """Describe an edge before server-side node validation."""

    source_node_id: int
    target_node_id: int


class KnowledgeEdgeRead(KnowledgeEdgeBase):
    """Return a persisted graph edge."""

    id: int
    project_id: int
    source_node_id: int
    target_node_id: int
    created_at: datetime
