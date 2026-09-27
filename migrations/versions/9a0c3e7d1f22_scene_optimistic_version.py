"""Add optimistic-concurrency versions to screenplay scenes."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9a0c3e7d1f22"
down_revision: str | None = "8f4c1d2a7b90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add a version counter to existing scenes."""
    op.add_column("scene", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.alter_column("scene", "version", server_default=None)


def downgrade() -> None:
    """Remove scene optimistic-concurrency versions."""
    op.drop_column("scene", "version")
