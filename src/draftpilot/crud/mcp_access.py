"""CRUD helpers for MCP registrations and grants."""

from datetime import UTC, datetime, timedelta

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.authorization import (
    ApprovalRequiredError,
    CapabilityGrant,
    CapabilityRequest,
    arguments_digest,
    authorize,
    redact_audit_payload,
    requires_approval,
)
from draftpilot.core.config import settings
from draftpilot.models import MCPApprovalRequest, MCPAuditEvent, MCPClient, MCPGrant


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


def _approval_summary(arguments: dict[str, object]) -> dict[str, object]:
    """Return a bounded, token-redacted view of call arguments for the writer's review."""
    redacted = redact_audit_payload(arguments, {"token", "api_key", "secret"})
    return {
        key: value[:2_000] if isinstance(value, str) else value for key, value in redacted.items()
    }


async def _consume_approval(
    session: AsyncSession,
    approval_id: int,
    client_id: str,
    project_id: int,
    capability: str,
    action: str,
    digest: str,
) -> None:
    """Verify a writer-approved request matches this exact call, then consume it."""
    request = await session.get(MCPApprovalRequest, approval_id)
    if (
        request is None
        or request.client_id != client_id
        or request.project_id != project_id
        or request.capability != capability
        or request.action != action
        or request.arguments_digest != digest
    ):
        raise PermissionError(f"Approval request {approval_id} does not match this call")
    if request.status == "pending":
        raise PermissionError(f"Approval request {approval_id} is still pending writer review")
    if request.status != "approved":
        raise PermissionError(f"Approval request {approval_id} is {request.status}")
    if _aware(request.expires_at) <= datetime.now(UTC):
        request.status = "expired"
        session.add(request)
        raise PermissionError(f"Approval request {approval_id} has expired")
    request.status = "consumed"
    session.add(request)


def _aware(value: datetime) -> datetime:
    """Treat naive timestamps from the database as UTC."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


async def authorize_invocation(
    session: AsyncSession,
    client_id: str,
    project_id: int,
    capability: str,
    action: str,
    payload: dict[str, object],
    approval_id: int | None = None,
    arguments: dict[str, object] | None = None,
) -> None:
    """Authorize one invocation, enforce writer approval, and persist a redacted audit event.

    ``payload`` is the audit summary. ``arguments`` (defaulting to ``payload``) is the complete
    call input that an approval is bound to, so an approved request cannot be replayed with
    different content.
    """
    grants = [
        CapabilityGrant(
            client_id=client_id,
            project_id=project_id,
            capability=grant.capability,
            expires_at=grant.expires_at,
        )
        for grant in await list_grants(session, project_id, client_id)
    ]
    call_arguments = arguments if arguments is not None else payload
    error: PermissionError | None = None
    try:
        # Grant check only; writer approval is verified below against a recorded request.
        authorize(
            CapabilityRequest(
                client_id=client_id, project_id=project_id, capability=capability, approved=True
            ),
            grants,
        )
        if requires_approval(capability):
            digest = arguments_digest(capability, action, call_arguments)
            if approval_id is None:
                pending = MCPApprovalRequest(
                    client_id=client_id,
                    project_id=project_id,
                    capability=capability,
                    action=action,
                    arguments_digest=digest,
                    summary=_approval_summary(call_arguments),
                    expires_at=datetime.now(UTC) + timedelta(seconds=settings.mcp.approval_ttl_seconds),
                )
                session.add(pending)
                await session.flush()
                raise ApprovalRequiredError(pending.id or 0)
            await _consume_approval(
                session, approval_id, client_id, project_id, capability, action, digest
            )
    except PermissionError as exc:
        error = exc
    session.add(
        MCPAuditEvent(
            client_id=client_id,
            project_id=project_id,
            capability=capability,
            action=action,
            allowed=error is None,
            reason=str(error)[:300] if error else None,
            payload=redact_audit_payload(payload, {"token", "content", "text"}),
        )
    )
    await session.commit()
    if error is not None:
        raise error


async def list_approvals(
    session: AsyncSession, project_id: int, status: str | None = None
) -> list[MCPApprovalRequest]:
    """Return a project's MCP approval requests, newest first."""
    query = select(MCPApprovalRequest).where(MCPApprovalRequest.project_id == project_id)
    if status is not None:
        query = query.where(MCPApprovalRequest.status == status)
    result = await session.exec(query.order_by(col(MCPApprovalRequest.id).desc()))
    return list(result.all())


async def decide_approval(
    session: AsyncSession, project_id: int, approval_id: int, approve: bool
) -> MCPApprovalRequest:
    """Record the writer's decision on one pending MCP approval request."""
    request = await session.get(MCPApprovalRequest, approval_id)
    if request is None or request.project_id != project_id:
        raise LookupError("Approval request not found")
    if request.status != "pending":
        raise ValueError(f"Approval request is already {request.status}")
    now = datetime.now(UTC)
    if _aware(request.expires_at) <= now:
        request.status = "expired"
    else:
        request.status = "approved" if approve else "rejected"
    request.decided_at = now
    session.add(request)
    await session.commit()
    await session.refresh(request)
    return request
