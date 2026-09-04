"""SQLModel records for bounded Monty executions."""

from datetime import datetime

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel

from draftpilot.models.base import _utcnow


class MontyExecutionBase(SQLModel):
    """Share non-sensitive Monty execution audit fields."""

    run_id: int | None = Field(default=None, foreign_key="workflow_run.id", index=True)
    status: str = Field(default="completed", max_length=30)
    code_sha256: str = Field(max_length=64)
    input_count: int = Field(default=0, ge=0)
    output_chars: int = Field(default=0, ge=0)
    duration_ms: int = Field(default=0, ge=0)
    error: str | None = Field(default=None, max_length=1000)


class MontyExecution(MontyExecutionBase, table=True):  # type: ignore[call-arg]
    """Persist a redacted audit record for one Monty execution."""

    __tablename__ = "monty_execution"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    created_at: datetime = Field(
        default_factory=_utcnow,  # type: ignore[call-overload]
        sa_type=DateTime(timezone=True),
        nullable=False,
    )


class MontyExecutionCreate(MontyExecutionBase):
    """Describe a project-scoped Monty audit record."""

    project_id: int


class MontyExecutionRead(MontyExecutionBase):
    """Return a redacted Monty audit record."""

    id: int
    project_id: int
    created_at: datetime
