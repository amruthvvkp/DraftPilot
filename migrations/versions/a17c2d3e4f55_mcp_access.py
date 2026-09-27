"""Create durable MCP client, grant, and audit tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a17c2d3e4f55"
down_revision: str | None = "f26b7c8d9e00"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create scoped MCP access tables."""
    op.create_table(
        "mcp_client",
        sa.Column("client_id", sa.String(length=200), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id"),
    )
    op.create_index("ix_mcp_client_client_id", "mcp_client", ["client_id"])
    op.create_table(
        "mcp_grant",
        sa.Column("capability", sa.String(length=120), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["mcp_client.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mcp_grant_client_id", "mcp_grant", ["client_id"])
    op.create_index("ix_mcp_grant_project_id", "mcp_grant", ["project_id"])
    op.create_table(
        "mcp_audit_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.String(length=200), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("capability", sa.String(length=120), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("allowed", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(length=300), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mcp_audit_event_client_id", "mcp_audit_event", ["client_id"])
    op.create_index("ix_mcp_audit_event_project_id", "mcp_audit_event", ["project_id"])


def downgrade() -> None:
    """Remove MCP access tables."""
    op.drop_index("ix_mcp_audit_event_project_id", table_name="mcp_audit_event")
    op.drop_index("ix_mcp_audit_event_client_id", table_name="mcp_audit_event")
    op.drop_table("mcp_audit_event")
    op.drop_index("ix_mcp_grant_project_id", table_name="mcp_grant")
    op.drop_index("ix_mcp_grant_client_id", table_name="mcp_grant")
    op.drop_table("mcp_grant")
    op.drop_index("ix_mcp_client_client_id", table_name="mcp_client")
    op.drop_table("mcp_client")
