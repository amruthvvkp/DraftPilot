"""Add persisted, reviewable timeline reorder proposals."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d04f5a6b7c88"
down_revision: str | None = "c93e4d5f6a77"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the timeline proposal table."""
    op.create_table(
        "timeline_proposal",
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("original_scene_ids", sa.JSON(), nullable=False),
        sa.Column("proposed_scene_ids", sa.JSON(), nullable=False),
        sa.Column("timings", sa.JSON(), nullable=False),
        sa.Column("total_runtime_seconds", sa.Integer(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("screenplay_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(["screenplay_id"], ["screenplay.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_timeline_proposal_project_id"), "timeline_proposal", ["project_id"])
    op.create_index(op.f("ix_timeline_proposal_screenplay_id"), "timeline_proposal", ["screenplay_id"])


def downgrade() -> None:
    """Remove persisted timeline proposals."""
    op.drop_index(op.f("ix_timeline_proposal_screenplay_id"), table_name="timeline_proposal")
    op.drop_index(op.f("ix_timeline_proposal_project_id"), table_name="timeline_proposal")
    op.drop_table("timeline_proposal")
