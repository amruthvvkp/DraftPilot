"""Add block authorship origin and persisted screenplay title pages.

Revision ID: 5f6a7b8c9d00
Revises: 4e5f6a7b8c99
Create Date: 2026-09-27 09:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "5f6a7b8c9d00"
down_revision: str | None = "4e5f6a7b8c99"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add ``block.origin`` (existing blocks become "human") and ``screenplay.title_page``."""
    op.add_column(
        "block",
        sa.Column(
            "origin",
            sqlmodel.sql.sqltypes.AutoString(length=120),
            nullable=False,
            server_default="human",
        ),
    )
    op.add_column(
        "screenplay",
        sa.Column("title_page", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    """Drop the authorship and title-page columns."""
    op.drop_column("screenplay", "title_page")
    op.drop_column("block", "origin")
