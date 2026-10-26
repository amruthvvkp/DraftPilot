"""Add durable project and scene instruction layers."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6b2c8d4e1f77"
down_revision: str | None = "5a1c7e9b3d66"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add versioned project and scene instruction columns."""
    op.add_column("project", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("project", sa.Column("project_instruction", sa.Text(), nullable=False, server_default=""))
    op.alter_column("project", "version", server_default=None)
    op.alter_column("project", "project_instruction", server_default=None)
    op.add_column("scene", sa.Column("scene_instruction", sa.Text(), nullable=False, server_default=""))
    op.alter_column("scene", "scene_instruction", server_default=None)


def downgrade() -> None:
    """Remove durable project and scene instruction columns."""
    op.drop_column("scene", "scene_instruction")
    op.drop_column("project", "project_instruction")
    op.drop_column("project", "version")
