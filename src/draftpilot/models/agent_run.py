"""AgentRun model — one measured execution of an in-app agent (chat turn, workflow step, ...)."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime
from sqlmodel import Field, SQLModel

from draftpilot.models.base import _utcnow


class AgentRun(SQLModel, table=True):  # type: ignore[call-arg]
    """Record which agent ran, on which model, what it cost, and how it ended."""

    __tablename__ = "agent_run"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    workflow_run_id: int | None = Field(default=None, foreign_key="workflow_run.id", index=True)
    kind: str = Field(default="chat", max_length=40, index=True)
    role: str = Field(max_length=60, index=True)
    provider: str = Field(default="", max_length=50)
    model: str = Field(default="", max_length=200)
    status: str = Field(default="running", max_length=20, index=True)
    requests: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    trace_id: str | None = Field(default=None, max_length=32, index=True)
    tools_used: list[str] = Field(default_factory=list, sa_type=JSON)
    error: str | None = Field(default=None, max_length=500)
    details: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    created_at: datetime = Field(default_factory=_utcnow, sa_type=DateTime(timezone=True))  # type: ignore[call-overload]


class AgentRunRead(SQLModel):
    """Return a measured agent run."""

    id: int
    project_id: int
    workflow_run_id: int | None
    kind: str
    role: str
    provider: str
    model: str
    status: str
    requests: int
    tool_calls: int
    input_tokens: int
    output_tokens: int
    duration_ms: int
    trace_id: str | None
    tools_used: list[str]
    error: str | None
    created_at: datetime
