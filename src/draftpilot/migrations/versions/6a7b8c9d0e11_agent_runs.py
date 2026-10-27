"""Add measured agent runs.

Revision ID: 6a7b8c9d0e11
Revises: 5f6a7b8c9d00
Create Date: 2026-09-27 10:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "6a7b8c9d0e11"
down_revision: str | None = "5f6a7b8c9d00"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the agent_run table and its lookup indexes."""
    op.create_table(
        "agent_run",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("workflow_run_id", sa.Integer(), nullable=True),
        sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(length=40), nullable=False),
        sa.Column("role", sqlmodel.sql.sqltypes.AutoString(length=60), nullable=False),
        sa.Column("provider", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column("model", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column("requests", sa.Integer(), nullable=False),
        sa.Column("tool_calls", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("trace_id", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=True),
        sa.Column("tools_used", sa.JSON(), nullable=False),
        sa.Column("error", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_run.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("project_id", "workflow_run_id", "kind", "role", "status", "trace_id"):
        op.create_index(f"ix_agent_run_{column}", "agent_run", [column])


def downgrade() -> None:
    """Drop the agent_run table."""
    for column in ("trace_id", "status", "role", "kind", "workflow_run_id", "project_id"):
        op.drop_index(f"ix_agent_run_{column}", table_name="agent_run")
    op.drop_table("agent_run")
