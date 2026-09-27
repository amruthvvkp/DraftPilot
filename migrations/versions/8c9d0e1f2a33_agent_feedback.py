"""Add writer feedback on agent and room workflow runs.

Revision ID: 8c9d0e1f2a33
Revises: 7b8c9d0e1f22
Create Date: 2026-09-27 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "8c9d0e1f2a33"
down_revision: str | None = "7b8c9d0e1f22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create agent_feedback."""
    op.create_table(
        "agent_feedback",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("agent_run_id", sa.Integer(), nullable=True),
        sa.Column("workflow_run_id", sa.Integer(), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sqlmodel.sql.sqltypes.AutoString(length=2000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_run.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_run.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_feedback_project_id"), "agent_feedback", ["project_id"], unique=False)
    op.create_index(op.f("ix_agent_feedback_agent_run_id"), "agent_feedback", ["agent_run_id"], unique=False)
    op.create_index(op.f("ix_agent_feedback_workflow_run_id"), "agent_feedback", ["workflow_run_id"], unique=False)


def downgrade() -> None:
    """Drop agent_feedback."""
    op.drop_index(op.f("ix_agent_feedback_workflow_run_id"), table_name="agent_feedback")
    op.drop_index(op.f("ix_agent_feedback_agent_run_id"), table_name="agent_feedback")
    op.drop_index(op.f("ix_agent_feedback_project_id"), table_name="agent_feedback")
    op.drop_table("agent_feedback")
