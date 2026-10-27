"""Persisted project evaluation results."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime
from sqlmodel import Field, SQLModel

from draftpilot.models.base import _utcnow


class EvaluationResultBase(SQLModel):
    """Define the portable result of one screenplay or story evaluation."""

    target_kind: str = Field(default="project", max_length=50)
    target_id: int | None = Field(default=None, ge=1)
    evaluator: str = Field(max_length=100)
    score: float | None = Field(default=None, ge=0, le=1)
    summary: str = Field(default="")
    findings: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)


class EvaluationResult(EvaluationResultBase, table=True):  # type: ignore[call-arg]
    """Store one immutable evaluation result for a project."""

    __tablename__ = "evaluation_result"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    created_at: datetime = Field(
        default_factory=_utcnow,  # type: ignore[call-overload]
        sa_type=DateTime(timezone=True),
        nullable=False,
    )


class EvaluationResultCreate(EvaluationResultBase):
    """Describe an evaluation result before assigning its project."""


class EvaluationResultRead(EvaluationResultBase):
    """Return an evaluation result with identity and project scope."""

    id: int
    project_id: int
    created_at: datetime
