"""Create encrypted provider profile storage."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b28c3d4e5f66"
down_revision: str | None = "a17c2d3e4f55"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the provider profile table."""
    op.create_table(
        "provider_profile",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("base_url", sa.String(length=1000), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("api_key_encrypted", sa.String(length=2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_provider_profile_name", "provider_profile", ["name"])


def downgrade() -> None:
    """Remove provider profile storage."""
    op.drop_index("ix_provider_profile_name", table_name="provider_profile")
    op.drop_table("provider_profile")
