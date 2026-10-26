"""Allow installation-wide MCP grants (a grant with no project covers every project).

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-26 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Make mcp_grant.project_id nullable."""
    op.alter_column("mcp_grant", "project_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    """Drop installation-wide grants and make project_id required again."""
    op.execute("DELETE FROM mcp_grant WHERE project_id IS NULL")
    op.alter_column("mcp_grant", "project_id", existing_type=sa.Integer(), nullable=False)
