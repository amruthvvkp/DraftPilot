"""Add typed agent proposals with approval and rollback snapshots."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f26b7c8d9e00"
down_revision: str | None = "e15a6b7c8d99"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the agent proposal table."""
    op.create_table(
        "agent_proposal",
        sa.Column("target_kind", sa.String(length=30), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("operation", sa.JSON(), nullable=False),
        sa.Column("diff", sa.JSON(), nullable=False),
        sa.Column("before", sa.JSON(), nullable=False),
        sa.Column("base_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_run.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_proposal_project_id"), "agent_proposal", ["project_id"])
    op.create_index(op.f("ix_agent_proposal_run_id"), "agent_proposal", ["run_id"])


def downgrade() -> None:
    """Remove agent proposals."""
    op.drop_index(op.f("ix_agent_proposal_run_id"), table_name="agent_proposal")
    op.drop_index(op.f("ix_agent_proposal_project_id"), table_name="agent_proposal")
    op.drop_table("agent_proposal")
