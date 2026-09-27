"""Versioned editable story-development artifact model."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, DateTime
from sqlmodel import Field, SQLModel

from draftpilot.models.base import _utcnow


class StoryArtifactBase(SQLModel):
    """Shared fields for editable creative artifacts."""

    kind: str = Field(max_length=40)
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(default="")
    version: int = Field(default=1, ge=1)
    stale: bool = False
    depends_on: list[int] = Field(default_factory=list, sa_type=JSON)
    artifact_metadata: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column("metadata", JSON, nullable=False)
    )


class StoryArtifact(StoryArtifactBase, table=True):  # type: ignore[call-arg]
    """Persist an independently editable story artifact and its dependencies."""

    __tablename__ = "story_artifact"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
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


class StoryArtifactRead(StoryArtifactBase):
    """Return an artifact with project scope and timestamps."""

    id: int
    project_id: int
    created_at: datetime
    updated_at: datetime
