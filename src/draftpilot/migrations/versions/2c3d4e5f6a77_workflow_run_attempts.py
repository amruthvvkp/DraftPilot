"""Add bounded retry state to durable workflow runs."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2c3d4e5f6a77"
down_revision: str | Sequence[str] | None = "1b2c3d4e5f66"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add persisted attempt counters with safe defaults for existing runs."""
    op.add_column("workflow_run", sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("workflow_run", sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"))
    op.alter_column("workflow_run", "attempt_count", server_default=None)
    op.alter_column("workflow_run", "max_attempts", server_default=None)


def downgrade() -> None:
    """Remove persisted workflow retry counters."""
    op.drop_column("workflow_run", "max_attempts")
    op.drop_column("workflow_run", "attempt_count")
