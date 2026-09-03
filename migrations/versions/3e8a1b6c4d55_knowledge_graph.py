"""Add project-scoped knowledge graph nodes and edges."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3e8a1b6c4d55"
down_revision: str | None = "2d7e9f1a3b44"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create knowledge graph node and edge tables."""
    op.create_table(
        "knowledge_node",
        sa.Column("kind", sa.String(length=60), nullable=False),
        sa.Column("label", sa.String(length=300), nullable=False),
        sa.Column("description", sa.String(length=4000), nullable=True),
        sa.Column("node_metadata", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_knowledge_node_project_id"), "knowledge_node", ["project_id"])
    op.create_table(
        "knowledge_edge",
        sa.Column("relation", sa.String(length=100), nullable=False),
        sa.Column("edge_metadata", sa.JSON(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("source_node_id", sa.Integer(), nullable=False),
        sa.Column("target_node_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(["source_node_id"], ["knowledge_node.id"]),
        sa.ForeignKeyConstraint(["target_node_id"], ["knowledge_node.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_knowledge_edge_project_id"), "knowledge_edge", ["project_id"])
    op.create_index(op.f("ix_knowledge_edge_source_node_id"), "knowledge_edge", ["source_node_id"])
    op.create_index(op.f("ix_knowledge_edge_target_node_id"), "knowledge_edge", ["target_node_id"])


def downgrade() -> None:
    """Remove knowledge graph tables."""
    op.drop_index(op.f("ix_knowledge_edge_target_node_id"), table_name="knowledge_edge")
    op.drop_index(op.f("ix_knowledge_edge_source_node_id"), table_name="knowledge_edge")
    op.drop_index(op.f("ix_knowledge_edge_project_id"), table_name="knowledge_edge")
    op.drop_table("knowledge_edge")
    op.drop_index(op.f("ix_knowledge_node_project_id"), table_name="knowledge_node")
    op.drop_table("knowledge_node")
