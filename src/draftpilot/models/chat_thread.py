"""Persisted chat threads: one AG-UI conversation with the writers' room."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer
from sqlmodel import Field, SQLModel

from draftpilot.models.base import _utcnow


class ChatThread(SQLModel, table=True):  # type: ignore[call-arg]
    """Store one chat thread (keyed by the AG-UI ``threadId``) with its full message history."""

    __tablename__ = "chat_thread"

    id: str = Field(primary_key=True, max_length=100)
    project_id: int = Field(sa_column=Column(Integer, ForeignKey("project.id", ondelete="CASCADE"), index=True, nullable=False))
    title: str = Field(default="New conversation", max_length=200)
    role: str = Field(default="showrunner", max_length=60)
    # Pydantic AI messages (``ModelMessagesTypeAdapter`` JSON), the server's source of truth.
    messages: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSON)
    created_at: datetime = Field(default_factory=_utcnow, sa_type=DateTime(timezone=True))  # type: ignore[call-overload]
    updated_at: datetime = Field(default_factory=_utcnow, sa_type=DateTime(timezone=True))  # type: ignore[call-overload]


class ChatThreadRead(SQLModel):
    """Summarise a chat thread for the thread list."""

    id: str
    project_id: int
    title: str
    role: str
    created_at: datetime
    updated_at: datetime
