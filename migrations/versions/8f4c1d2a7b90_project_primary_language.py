"""Add the screenplay source language to project metadata."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8f4c1d2a7b90"
down_revision: str | None = "5113cead7b29"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add a default source language for existing projects."""
    op.add_column(
        "project",
        sa.Column("primary_language", sa.String(length=50), nullable=False, server_default="English"),
    )
    op.alter_column("project", "primary_language", server_default=None)


def downgrade() -> None:
    """Remove the project screenplay source language."""
    op.drop_column("project", "primary_language")
