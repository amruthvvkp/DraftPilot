"""Persisted typed agent change proposal for approval and rollback."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime
from sqlmodel import Field, SQLModel

from draftpilot.models.base import _utcnow


class AgentProposalBase(SQLModel):
    """Shared fields for reviewable agent proposals."""

    target_kind: str = Field(max_length=30)
    target_id: int
    operation: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    diff: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    before: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    base_version: int = Field(ge=1)
    status: str = Field(default="proposed", max_length=30)


class AgentProposal(AgentProposalBase, table=True):  # type: ignore[call-arg]
    """Store an agent operation until a writer approves or rolls it back."""

    __tablename__ = "agent_proposal"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    run_id: int | None = Field(default=None, foreign_key="workflow_run.id", index=True)
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


class AgentProposalRead(AgentProposalBase):
    """Return a proposal with project and run scope."""

    id: int
    project_id: int
    run_id: int | None
    created_at: datetime
    updated_at: datetime
