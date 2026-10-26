"""Add writer-decided MCP approval requests.

Revision ID: 4e5f6a7b8c99
Revises: 3d4e5f6a7b88
Create Date: 2026-09-27 09:05:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "4e5f6a7b8c99"
down_revision: str | None = "3d4e5f6a7b88"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the MCP approval request table."""
    op.create_table(
        "mcp_approval_request",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("client_id", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("capability", sqlmodel.sql.sqltypes.AutoString(length=120), nullable=False),
        sa.Column("action", sqlmodel.sql.sqltypes.AutoString(length=30), nullable=False),
        sa.Column("arguments_digest", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mcp_approval_request_client_id", "mcp_approval_request", ["client_id"])
    op.create_index("ix_mcp_approval_request_project_id", "mcp_approval_request", ["project_id"])
    op.create_index("ix_mcp_approval_request_status", "mcp_approval_request", ["status"])


def downgrade() -> None:
    """Drop the MCP approval request table."""
    op.drop_index("ix_mcp_approval_request_status", table_name="mcp_approval_request")
    op.drop_index("ix_mcp_approval_request_project_id", table_name="mcp_approval_request")
    op.drop_index("ix_mcp_approval_request_client_id", table_name="mcp_approval_request")
    op.drop_table("mcp_approval_request")
