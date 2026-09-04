"""Durable workflow-run model for reconnectable background execution."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime
from sqlmodel import Field, SQLModel

from draftpilot.models.base import _utcnow


class WorkflowRunBase(SQLModel):
    """Shared fields for persisted workflow runs."""

    kind: str = Field(default="screenplay_analysis", max_length=80)
    status: str = Field(default="queued", max_length=30)
    input: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    result: dict[str, Any] | None = Field(default=None, sa_type=JSON)
    error: str | None = Field(default=None, max_length=1000)
    agent_role: str = Field(default="story_architect", max_length=60)
    permission_mode: str = Field(default="chat_only", max_length=30)
    attempt_count: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, ge=1, le=10)


class WorkflowRun(WorkflowRunBase, table=True):  # type: ignore[call-arg]
    """Persist a workflow lifecycle so execution can resume after disconnects."""

    __tablename__ = "workflow_run"

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


class WorkflowRunCreate(WorkflowRunBase):
    """Describe a new project-scoped workflow run."""

    project_id: int


class WorkflowRunRead(WorkflowRunBase):
    """Return workflow state to reconnecting clients."""

    id: int
    project_id: int
    created_at: datetime
    updated_at: datetime
