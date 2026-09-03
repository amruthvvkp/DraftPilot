"""Persisted MCP clients, project grants, and redacted invocation audit records."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime
from sqlmodel import Field, SQLModel

from draftpilot.models.base import _utcnow


class MCPClientBase(SQLModel):
    """Shared fields for an external MCP client registration."""

    client_id: str = Field(max_length=200, unique=True, index=True)
    name: str = Field(max_length=200)
    enabled: bool = True


class MCPClient(MCPClientBase, table=True):  # type: ignore[call-arg]
    """Register an MCP client without storing its bearer token."""

    __tablename__ = "mcp_client"

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=_utcnow, sa_type=DateTime(timezone=True))  # type: ignore[call-overload]


class MCPGrantBase(SQLModel):
    """Shared fields for a project-scoped capability grant."""

    capability: str = Field(max_length=120)
    expires_at: datetime | None = Field(  # type: ignore[call-overload]
        default=None, sa_type=DateTime(timezone=True)
    )


class MCPGrant(MCPGrantBase, table=True):  # type: ignore[call-arg]
    """Grant one registered client one capability for one project."""

    __tablename__ = "mcp_grant"

    id: int | None = Field(default=None, primary_key=True)
    client_id: int = Field(foreign_key="mcp_client.id", index=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    created_at: datetime = Field(default_factory=_utcnow, sa_type=DateTime(timezone=True))  # type: ignore[call-overload]


class MCPAuditEvent(SQLModel, table=True):  # type: ignore[call-arg]
    """Record a bounded, redacted MCP capability invocation."""

    __tablename__ = "mcp_audit_event"

    id: int | None = Field(default=None, primary_key=True)
    client_id: str = Field(max_length=200, index=True)
    project_id: int | None = Field(default=None, foreign_key="project.id", index=True)
    capability: str = Field(max_length=120)
    action: str = Field(max_length=30)
    allowed: bool
    reason: str | None = Field(default=None, max_length=300)
    payload: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    created_at: datetime = Field(default_factory=_utcnow, sa_type=DateTime(timezone=True))  # type: ignore[call-overload]


class MCPGrantCreate(SQLModel):
    """Describe a grant to create for a registered client."""

    client_id: str
    project_id: int
    capability: str
    expires_at: datetime | None = None


class MCPGrantRead(MCPGrantBase):
    """Return a persisted grant with client and project scope."""

    id: int
    client_id: int
    project_id: int
