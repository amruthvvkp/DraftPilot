"""Persisted, context-aware Copilot conversation messages."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime
from sqlmodel import Field, SQLModel

from draftpilot.models.base import _utcnow


class CopilotMessageBase(SQLModel):
    """Share fields for a context-aware Copilot message."""

    role: str = Field(default="user", max_length=20)
    content: str = Field(min_length=1, max_length=12000)
    page: str = Field(default="workspace", max_length=100)
    artifact: str | None = Field(default=None, max_length=200)
    selection: str | None = Field(default=None, max_length=2000)
    instruction_layers: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    citations: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSON)
    active_tools: list[str] = Field(default_factory=list, sa_type=JSON)


class CopilotMessage(CopilotMessageBase, table=True):  # type: ignore[call-arg]
    """Store one project-scoped Copilot conversation turn."""

    __tablename__ = "copilot_message"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    created_at: datetime = Field(default_factory=_utcnow, sa_type=DateTime(timezone=True))  # type: ignore[call-overload]


class CopilotMessageCreate(CopilotMessageBase):
    """Describe a new Copilot message before persistence."""

    project_id: int


class CopilotMessageRead(CopilotMessageBase):
    """Return a persisted Copilot message with its scope."""

    id: int
    project_id: int
    created_at: datetime
