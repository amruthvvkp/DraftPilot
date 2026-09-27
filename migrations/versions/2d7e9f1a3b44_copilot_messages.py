"""Add durable, context-aware Copilot conversation messages."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2d7e9f1a3b44"
down_revision: str | None = "f26b7c8d9e00"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the Copilot message table."""
    op.create_table(
        "copilot_message",
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.String(length=12000), nullable=False),
        sa.Column("page", sa.String(length=100), nullable=False),
        sa.Column("artifact", sa.String(length=200), nullable=True),
        sa.Column("selection", sa.String(length=2000), nullable=True),
        sa.Column("instruction_layers", sa.JSON(), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=False),
        sa.Column("active_tools", sa.JSON(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_copilot_message_project_id"), "copilot_message", ["project_id"])


def downgrade() -> None:
    """Remove the Copilot message table."""
    op.drop_index(op.f("ix_copilot_message_project_id"), table_name="copilot_message")
    op.drop_table("copilot_message")
