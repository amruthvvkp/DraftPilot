"""Add the writer twin: profile and memories.

Revision ID: 7b8c9d0e1f22
Revises: 6a7b8c9d0e11
Create Date: 2026-09-27 11:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "7b8c9d0e1f22"
down_revision: str | None = "6a7b8c9d0e11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create writer_profile and writer_memory."""
    op.create_table(
        "writer_profile",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False),
        sa.Column("pen_name", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False),
        sa.Column("bio", sqlmodel.sql.sqltypes.AutoString(length=4000), nullable=False),
        sa.Column("default_format", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column("default_language", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column("style_notes", sqlmodel.sql.sqltypes.AutoString(length=8000), nullable=False),
        sa.Column("preferences", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "writer_memory",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(length=30), nullable=False),
        sa.Column("text", sqlmodel.sql.sqltypes.AutoString(length=2000), nullable=False),
        sa.Column("source", sqlmodel.sql.sqltypes.AutoString(length=40), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_writer_memory_project_id", "writer_memory", ["project_id"])


def downgrade() -> None:
    """Drop the writer twin tables."""
    op.drop_index("ix_writer_memory_project_id", table_name="writer_memory")
    op.drop_table("writer_memory")
    op.drop_table("writer_profile")
