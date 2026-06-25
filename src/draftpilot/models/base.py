"""Shared model mixins."""

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class TimestampMixin(SQLModel):
    """Adds timezone-aware created/updated timestamps to a table model.

    ``sa_type`` (not ``sa_column``) is used so SQLModel builds a fresh column
    per inheriting table — a shared ``Column`` instance cannot bind to multiple
    tables.
    """

    # sa_type accepts a TypeEngine instance at runtime; the stub types it as
    # type[Any], hence the ignores.
    created_at: datetime = Field(
        default_factory=_utcnow,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        nullable=False,
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        nullable=False,
    )
