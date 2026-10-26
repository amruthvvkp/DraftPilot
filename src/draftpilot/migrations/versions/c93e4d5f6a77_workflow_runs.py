"""Add durable project-scoped workflow runs."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c93e4d5f6a77"
down_revision: str | None = "a81f3b2c4d55"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the workflow-run lifecycle table."""
    op.create_table(
        "workflow_run",
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("input", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.String(length=1000), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workflow_run_project_id"), "workflow_run", ["project_id"])


def downgrade() -> None:
    """Remove durable workflow runs."""
    op.drop_index(op.f("ix_workflow_run_project_id"), table_name="workflow_run")
    op.drop_table("workflow_run")
