"""Writer twin models: the single writer's profile and the memories the room keeps about them."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime
from sqlmodel import Field, SQLModel

from draftpilot.models.base import _utcnow


class WriterProfileBase(SQLModel):
    """Writer-authored identity, voice, and preferences shared with every room agent."""

    name: str = Field(default="", max_length=200)
    pen_name: str = Field(default="", max_length=200)
    bio: str = Field(default="", max_length=4000)
    default_format: str = Field(default="feature", max_length=50)
    default_language: str = Field(default="English", max_length=50)
    # How the writer writes: voice, rhythm, dialogue habits, what they are going for.
    style_notes: str = Field(default="", max_length=8000)
    # Structured preferences, e.g. {"tone": [...], "avoid": [...], "formatting": [...]}.
    preferences: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)


class WriterProfile(WriterProfileBase, table=True):  # type: ignore[call-arg]
    """Persist the installation's writer profile (single-user studio: one row)."""

    __tablename__ = "writer_profile"

    id: int | None = Field(default=None, primary_key=True)
    updated_at: datetime = Field(default_factory=_utcnow, sa_type=DateTime(timezone=True))  # type: ignore[call-overload]


class WriterProfileRead(WriterProfileBase):
    """Return the writer profile."""

    updated_at: datetime | None = None


class WriterMemoryBase(SQLModel):
    """One thing the room should remember about how this writer works."""

    kind: str = Field(default="preference", max_length=30)  # preference | style | taboo | fact | feedback
    text: str = Field(min_length=1, max_length=2000)
    source: str = Field(default="writer", max_length=40)  # writer | learned | agent:<role>
    pinned: bool = False
    project_id: int | None = Field(default=None, foreign_key="project.id", index=True)


class WriterMemory(WriterMemoryBase, table=True):  # type: ignore[call-arg]
    """Persist one writer memory (global, or scoped to a project)."""

    __tablename__ = "writer_memory"

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=_utcnow, sa_type=DateTime(timezone=True))  # type: ignore[call-overload]


class WriterMemoryRead(WriterMemoryBase):
    """Return a writer memory."""

    id: int
    created_at: datetime
