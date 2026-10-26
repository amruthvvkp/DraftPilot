"""Add selected agent role and permission mode to workflow runs."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5a1c7e9b3d66"
down_revision: str | None = "4f9c2a7e1d66"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add non-null role and permission metadata with safe defaults."""
    op.add_column("workflow_run", sa.Column("agent_role", sa.String(length=60), nullable=False, server_default="story_architect"))
    op.add_column("workflow_run", sa.Column("permission_mode", sa.String(length=30), nullable=False, server_default="chat_only"))
    op.alter_column("workflow_run", "agent_role", server_default=None)
    op.alter_column("workflow_run", "permission_mode", server_default=None)


def downgrade() -> None:
    """Remove workflow agent metadata."""
    op.drop_column("workflow_run", "permission_mode")
    op.drop_column("workflow_run", "agent_role")
