"""Add source-preserving dialogue translation variants."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a81f3b2c4d55"
down_revision: str | None = "9a0c3e7d1f22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create linked translation variants for dialogue blocks."""
    op.create_table(
        "dialogue_translation",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("language", sa.String(length=50), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("block_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["block_id"], ["block.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("block_id", "language", name="uq_dialogue_translation_block_language"),
    )
    op.create_index(op.f("ix_dialogue_translation_block_id"), "dialogue_translation", ["block_id"])


def downgrade() -> None:
    """Remove linked dialogue translation variants."""
    op.drop_index(op.f("ix_dialogue_translation_block_id"), table_name="dialogue_translation")
    op.drop_table("dialogue_translation")
