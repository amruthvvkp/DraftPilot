"""Add versioned editable story-development artifacts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e15a6b7c8d99"
down_revision: str | None = "d04f5a6b7c88"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the story artifact table."""
    op.create_table(
        "story_artifact",
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("stale", sa.Boolean(), nullable=False),
        sa.Column("depends_on", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_story_artifact_project_id"), "story_artifact", ["project_id"])


def downgrade() -> None:
    """Remove story artifacts."""
    op.drop_index(op.f("ix_story_artifact_project_id"), table_name="story_artifact")
    op.drop_table("story_artifact")
