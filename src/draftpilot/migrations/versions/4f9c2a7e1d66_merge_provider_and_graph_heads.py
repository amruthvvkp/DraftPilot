"""Merge the provider and graph migration branches into one upgrade head."""

from collections.abc import Sequence

revision: str = "4f9c2a7e1d66"
down_revision: tuple[str, str] = ("3e8a1b6c4d55", "b28c3d4e5f66")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Merge migration branches without changing schema."""


def downgrade() -> None:
    """Leave branch downgrade ordering to the parent revisions."""
