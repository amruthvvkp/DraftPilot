"""Project-scoped MCP client and capability grant administration endpoints."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.capabilities import capability_catalog
from draftpilot.core.config import settings
from draftpilot.core.db import async_get_db
from draftpilot.crud import mcp_access as access_crud
from draftpilot.crud import projects as projects_crud
from draftpilot.models import MCPClient, MCPGrant, MCPGrantRead

router = APIRouter(prefix="/mcp", tags=["mcp-access"])
_admin_bearer = HTTPBearer(auto_error=False)


async def require_mcp_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(_admin_bearer),
) -> None:
    """Require the separate server-side bearer token for grant administration."""
    expected = settings.mcp.admin_token.get_secret_value()
    if credentials is None or credentials.scheme.casefold() != "bearer" or credentials.credentials != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="MCP administration authorization required")


class ClientCreateRequest(BaseModel):
    """Describe an external client to register."""

    client_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)


class ClientRead(BaseModel):
    """Return non-secret client registration metadata."""

    id: int
    client_id: str
    name: str
    enabled: bool


class GrantRequest(BaseModel):
    """Describe a capability grant for a project and client."""

    client_id: str
    capability: str = Field(min_length=1, max_length=120)
    expires_at: datetime | None = None


@router.post("/clients", response_model=ClientRead, status_code=status.HTTP_201_CREATED)
async def register_client(
    data: ClientCreateRequest,
    session: AsyncSession = Depends(async_get_db),
    _admin: None = Depends(require_mcp_admin),
) -> ClientRead:
    """Register a client without accepting or returning bearer secrets."""
    existing = await access_crud.get_client(session, data.client_id)
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Client already exists")
    client = MCPClient(client_id=data.client_id, name=data.name)
    session.add(client)
    await session.commit()
    await session.refresh(client)
    return ClientRead.model_validate(client)


@router.get("/projects/{project_id}/grants", response_model=list[MCPGrantRead])
async def list_project_grants(
    project_id: int,
    client_id: str,
    session: AsyncSession = Depends(async_get_db),
    _admin: None = Depends(require_mcp_admin),
) -> list[MCPGrantRead]:
    """List active grants for one client in one project."""
    if await projects_crud.get(session, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    grants = await access_crud.list_grants(session, project_id, client_id)
    return [MCPGrantRead.model_validate(grant) for grant in grants]


@router.post("/projects/{project_id}/grants", response_model=MCPGrantRead, status_code=status.HTTP_201_CREATED)
async def create_project_grant(
    project_id: int,
    data: GrantRequest,
    session: AsyncSession = Depends(async_get_db),
    _admin: None = Depends(require_mcp_admin),
) -> MCPGrantRead:
    """Create a project grant only for a registered client."""
    if await projects_crud.get(session, project_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if data.capability not in {capability.name for capability in capability_catalog()}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Unknown capability")
    client = await access_crud.get_client(session, data.client_id)
    if client is None or client.id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    grant = MCPGrant(client_id=client.id, project_id=project_id, capability=data.capability, expires_at=data.expires_at)
    session.add(grant)
    await session.commit()
    await session.refresh(grant)
    return MCPGrantRead.model_validate(grant)


@router.delete("/projects/{project_id}/grants/{grant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_project_grant(
    project_id: int,
    grant_id: int,
    session: AsyncSession = Depends(async_get_db),
    _admin: None = Depends(require_mcp_admin),
) -> None:
    """Revoke one project grant without crossing client or project boundaries."""
    grant = await session.get(MCPGrant, grant_id)
    if grant is None or grant.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grant not found")
    await session.delete(grant)
    await session.commit()
