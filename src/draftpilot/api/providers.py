"""Server-side provider profile endpoints with write-only credentials."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, SecretStr
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.config import settings
from draftpilot.core.db import async_get_db
from draftpilot.core.security import encrypt_secret
from draftpilot.crud import provider_profiles as profiles_crud
from draftpilot.models import ProviderProfile, ProviderProfileRead

router = APIRouter(prefix="/settings/providers", tags=["providers"])


class ProviderWrite(BaseModel):
    """Accept provider metadata and an optional write-only API key."""

    name: str = Field(min_length=1, max_length=100)
    provider: str = Field(min_length=1, max_length=50)
    model: str = Field(min_length=1, max_length=200)
    base_url: str | None = Field(default=None, max_length=1000)
    enabled: bool = True
    api_key: SecretStr | None = None


class ProviderUpdate(BaseModel):
    """Accept partial provider metadata without returning secrets."""

    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    enabled: bool | None = None
    api_key: SecretStr | None = None


def _read(profile: ProviderProfile) -> ProviderProfileRead:
    """Map a persisted profile to a redacted response."""
    return ProviderProfileRead(
        **profile.model_dump(exclude={"api_key_encrypted"}),
        has_api_key=profile.api_key_encrypted is not None,
    )


@router.get("", response_model=list[ProviderProfileRead])
async def list_providers(session: AsyncSession = Depends(async_get_db)) -> list[ProviderProfileRead]:
    """List provider metadata without exposing credentials."""
    return [_read(profile) for profile in await profiles_crud.list_all(session)]


@router.post("", response_model=ProviderProfileRead, status_code=status.HTTP_201_CREATED)
async def create_provider(data: ProviderWrite, session: AsyncSession = Depends(async_get_db)) -> ProviderProfileRead:
    """Create a provider profile and encrypt its credential before persistence."""
    if await profiles_crud.get_by_name(session, data.name) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Provider name already exists")
    profile = ProviderProfile(
        name=data.name,
        provider=data.provider,
        model=data.model,
        base_url=data.base_url,
        enabled=data.enabled,
        api_key_encrypted=(
            encrypt_secret(data.api_key.get_secret_value(), settings.secrets.master_key)
            if data.api_key is not None
            else None
        ),
    )
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return _read(profile)


@router.patch("/{profile_id}", response_model=ProviderProfileRead)
async def update_provider(
    profile_id: int, data: ProviderUpdate, session: AsyncSession = Depends(async_get_db)
) -> ProviderProfileRead:
    """Update provider metadata and rotate a credential without returning it."""
    profile = await profiles_crud.get(session, profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    changes = data.model_dump(exclude_unset=True, exclude={"api_key"})
    for key, value in changes.items():
        setattr(profile, key, value)
    if data.api_key is not None:
        profile.api_key_encrypted = encrypt_secret(data.api_key.get_secret_value(), settings.secrets.master_key)
    profile.updated_at = datetime.now(timezone.utc)
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return _read(profile)
