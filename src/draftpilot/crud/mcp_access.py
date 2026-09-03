"""CRUD helpers for MCP registrations and grants."""

from datetime import datetime, timezone

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.models import MCPClient, MCPGrant


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
    now = datetime.now(timezone.utc)
    return [grant for grant in result.all() if grant.expires_at is None or grant.expires_at > now]
