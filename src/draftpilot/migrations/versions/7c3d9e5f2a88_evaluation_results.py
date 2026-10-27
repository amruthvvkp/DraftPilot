"""Add persisted project evaluation results."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7c3d9e5f2a88"
down_revision: str | None = "6b2c8d4e1f77"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the evaluation result table."""
    op.create_table(
        "evaluation_result",
        sa.Column("target_kind", sa.String(length=50), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("evaluator", sa.String(length=100), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evaluation_result_project_id", "evaluation_result", ["project_id"])


def downgrade() -> None:
    """Drop the evaluation result table."""
    op.drop_index("ix_evaluation_result_project_id", table_name="evaluation_result")
    op.drop_table("evaluation_result")
