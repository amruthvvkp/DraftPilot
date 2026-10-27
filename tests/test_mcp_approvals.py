"""Test that MCP clients cannot approve their own writes."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from _async import run_async
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

import draftpilot.models  # noqa: F401  (registers every table)
from draftpilot.core.authorization import ApprovalRequiredError
from draftpilot.crud import mcp_access as access_crud
from draftpilot.models import (
    MCPApprovalRequest,
    MCPAuditEvent,
    MCPClient,
    MCPGrant,
    Project,
)

CAPABILITY = "story.operation"
ARGS = {"artifact_id": 3, "operation": "set_logline", "payload": {"logline": "A reel."}}


@asynccontextmanager
async def _session() -> AsyncIterator[AsyncSession]:
    """Yield a session on a fresh in-memory database with one granted client."""
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        project = Project(title="Big Fish")
        client = MCPClient(client_id="claude", name="Claude Code")
        session.add_all([project, client])
        await session.flush()
        session.add(MCPGrant(client_id=client.id or 0, project_id=project.id or 0, capability=CAPABILITY))
        await session.commit()
        yield session
    await engine.dispose()


async def _invoke(session: AsyncSession, approval_id: int | None, arguments: dict[str, object] = ARGS) -> None:
    """Invoke the approval-gated capability as the granted client."""
    await access_crud.authorize_invocation(
        session, "claude", 1, CAPABILITY, "apply", {"artifact_id": 3}, approval_id=approval_id, arguments=arguments
    )


def test_first_call_records_pending_request_without_running() -> None:
    """An approval-required call records a pending request and is refused."""

    async def scenario() -> None:
        """Exercise the first, unapproved call."""
        async with _session() as session:
            with pytest.raises(ApprovalRequiredError) as raised:
                await _invoke(session, None)
            request = await session.get(MCPApprovalRequest, raised.value.approval_id)
            assert request is not None and request.status == "pending"
            assert request.summary["payload"] == {"logline": "A reel."}
            audit = (await session.exec(select(MCPAuditEvent))).one()
            assert audit.allowed is False

    run_async(scenario())


def test_pending_or_rejected_requests_cannot_be_used() -> None:
    """A client cannot proceed on a request the writer has not approved."""

    async def scenario() -> None:
        """Retry with a pending, then a rejected, request id."""
        async with _session() as session:
            with pytest.raises(ApprovalRequiredError) as raised:
                await _invoke(session, None)
            approval_id = raised.value.approval_id
            with pytest.raises(PermissionError, match="pending"):
                await _invoke(session, approval_id)
            await access_crud.decide_approval(session, 1, approval_id, approve=False)
            with pytest.raises(PermissionError, match="rejected"):
                await _invoke(session, approval_id)

    run_async(scenario())


def test_approved_request_runs_once_and_only_for_the_same_arguments() -> None:
    """An approval is bound to the exact arguments and is consumed on use."""

    async def scenario() -> None:
        """Approve, then try to replay with changed and repeated calls."""
        async with _session() as session:
            with pytest.raises(ApprovalRequiredError) as raised:
                await _invoke(session, None)
            approval_id = raised.value.approval_id
            await access_crud.decide_approval(session, 1, approval_id, approve=True)
            tampered = {**ARGS, "payload": {"logline": "Something else."}}
            with pytest.raises(PermissionError, match="does not match"):
                await _invoke(session, approval_id, tampered)
            await _invoke(session, approval_id)
            with pytest.raises(PermissionError, match="consumed"):
                await _invoke(session, approval_id)

    run_async(scenario())


def test_expired_approval_is_refused() -> None:
    """An approval cannot be used after its time-to-live."""

    async def scenario() -> None:
        """Expire an approved request, then retry."""
        async with _session() as session:
            with pytest.raises(ApprovalRequiredError) as raised:
                await _invoke(session, None)
            approval_id = raised.value.approval_id
            await access_crud.decide_approval(session, 1, approval_id, approve=True)
            request = await session.get(MCPApprovalRequest, approval_id)
            assert request is not None
            request.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            session.add(request)
            await session.commit()
            with pytest.raises(PermissionError, match="expired"):
                await _invoke(session, approval_id)

    run_async(scenario())


def test_writer_cannot_decide_twice() -> None:
    """A decided request cannot be re-decided."""

    async def scenario() -> None:
        """Approve a request, then try to reject it."""
        async with _session() as session:
            with pytest.raises(ApprovalRequiredError) as raised:
                await _invoke(session, None)
            await access_crud.decide_approval(session, 1, raised.value.approval_id, approve=True)
            with pytest.raises(ValueError, match="already approved"):
                await access_crud.decide_approval(session, 1, raised.value.approval_id, approve=False)

    run_async(scenario())
