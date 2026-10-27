"""Add redacted Monty execution audit records."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "1b2c3d4e5f66"
down_revision: str | Sequence[str] | None = "0a1b2c3d4e55"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the project-scoped Monty audit table."""
    op.create_table(
        "monty_execution",
        sa.Column("run_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("code_sha256", sa.String(length=64), nullable=False),
        sa.Column("input_count", sa.Integer(), nullable=False),
        sa.Column("output_chars", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("error", sa.String(length=1000), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_run.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_monty_execution_project_id"), "monty_execution", ["project_id"])
    op.create_index(op.f("ix_monty_execution_run_id"), "monty_execution", ["run_id"])


def downgrade() -> None:
    """Remove Monty execution audit records."""
    op.drop_index(op.f("ix_monty_execution_run_id"), table_name="monty_execution")
    op.drop_index(op.f("ix_monty_execution_project_id"), table_name="monty_execution")
    op.drop_table("monty_execution")
