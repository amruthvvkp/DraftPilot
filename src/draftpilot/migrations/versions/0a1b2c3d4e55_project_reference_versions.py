"""Add optimistic-concurrency versions to project references."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0a1b2c3d4e55"
down_revision: str | Sequence[str] | None = ("f26b7c8d9e00", "7c3d9e5f2a88")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add a version counter to existing project references."""
    op.add_column("project_reference", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.alter_column("project_reference", "version", server_default=None)


def downgrade() -> None:
    """Remove project-reference optimistic-concurrency versions."""
    op.drop_column("project_reference", "version")
