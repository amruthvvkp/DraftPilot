"""Persist source digests for imported screenplay controls."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3d4e5f6a7b88"
down_revision: str | Sequence[str] | None = "2c3d4e5f6a77"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add an optional non-content source digest to screenplay records."""
    op.add_column("screenplay", sa.Column("source_sha256", sa.String(length=64), nullable=True))


def downgrade() -> None:
    """Remove imported screenplay source digests."""
    op.drop_column("screenplay", "source_sha256")
