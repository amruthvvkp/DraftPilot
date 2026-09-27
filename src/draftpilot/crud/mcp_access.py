"""CRUD helpers for MCP registrations and grants."""

from datetime import UTC, datetime

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.authorization import (
    CapabilityGrant,
    CapabilityRequest,
    authorize,
    redact_audit_payload,
)
from draftpilot.models import MCPAuditEvent, MCPClient, MCPGrant


async def get_client(session: AsyncSession, client_id: str) -> MCPClient | None:
    """Return an enabled client registration by public client id."""
    result = await session.exec(select(MCPClient).where(MCPClient.client_id == client_id, MCPClient.enabled))
    return result.first()


async def list_grants(session: AsyncSession, project_id: int, client_id: str) -> list[MCPGrant]:
    """Return unexpired grants for one client and project."""
    result = await session.exec(
        select(MCPGrant).join(MCPClient).where(
            MCPGrant.project_id == project_id,
            MCPClient.client_id == client_id,
            MCPClient.enabled,
        ).order_by(col(MCPGrant.capability)
        )
    )
    now = datetime.now(UTC)
    return [grant for grant in result.all() if grant.expires_at is None or grant.expires_at > now]


async def authorize_invocation(
    session: AsyncSession,
    client_id: str,
    project_id: int,
    capability: str,
    action: str,
    payload: dict[str, object],
    approved: bool = False,
) -> None:
    """Authorize one invocation and persist a redacted audit event."""
    grants = [
        CapabilityGrant(
            client_id=client_id,
            project_id=project_id,
            capability=grant.capability,
            expires_at=grant.expires_at,
        )
        for grant in await list_grants(session, project_id, client_id)
    ]
    reason: str | None = None
    allowed = True
    try:
        authorize(
            CapabilityRequest(
                client_id=client_id,
                project_id=project_id,
                capability=capability,
                approved=approved,
            ),
            grants,
        )
    except PermissionError as exc:
        allowed = False
        reason = str(exc)
    session.add(
        MCPAuditEvent(
            client_id=client_id,
            project_id=project_id,
            capability=capability,
            action=action,
            allowed=allowed,
            reason=reason,
            payload=redact_audit_payload(payload, {"token", "content", "text"}),
        )
    )
    await session.commit()
    if not allowed:
        raise PermissionError(reason or "Capability denied")
