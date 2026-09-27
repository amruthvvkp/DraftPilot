"""Persisted, reviewable screenplay timeline reorder proposal."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime
from sqlmodel import Field, SQLModel

from draftpilot.models.base import _utcnow


class TimelineProposalBase(SQLModel):
    """Shared fields for timeline proposals."""

    status: str = Field(default="proposed", max_length=30)
    original_scene_ids: list[int] = Field(default_factory=list, sa_type=JSON)
    proposed_scene_ids: list[int] = Field(default_factory=list, sa_type=JSON)
    timings: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSON)
    total_runtime_seconds: int = Field(default=0, ge=0)


class TimelineProposalRecord(TimelineProposalBase, table=True):  # type: ignore[call-arg]
    """Store a reorder proposal until a writer approves or rejects it."""

    __tablename__ = "timeline_proposal"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    screenplay_id: int = Field(foreign_key="screenplay.id", index=True)
    created_at: datetime = Field(
        default_factory=_utcnow,  # type: ignore[call-overload]
        sa_type=DateTime(timezone=True),
        nullable=False,
    )
    updated_at: datetime = Field(
        default_factory=_utcnow,  # type: ignore[call-overload]
        sa_type=DateTime(timezone=True),
        nullable=False,
    )


class TimelineProposalRead(TimelineProposalBase):
    """Return a timeline proposal with its scope and timestamps."""

    id: int
    project_id: int
    screenplay_id: int
    created_at: datetime
    updated_at: datetime
