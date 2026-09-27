"""Server-side provider profile endpoints with write-only credentials."""

import time
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, SecretStr
from sqlmodel.ext.asyncio.session import AsyncSession

from draftpilot.core.config import LLMSettings, settings
from draftpilot.core.db import async_get_db
from draftpilot.core.providers import (
    SUPPORTED_PROVIDERS,
    ModelOption,
    list_models,
    normalize_provider,
    provider_base_url,
    resolve_model_name,
    settings_from_profile,
    validate_provider_url,
)
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


class ProviderTestResponse(BaseModel):
    """Return a credential-safe provider connectivity result."""

    ok: bool
    message: str
    latency_ms: int | None = None


def _read(profile: ProviderProfile) -> ProviderProfileRead:
    """Map a persisted profile to a redacted response."""
    return ProviderProfileRead(
        **profile.model_dump(exclude={"api_key_encrypted"}),
        has_api_key=profile.api_key_encrypted is not None,
    )


def _validate_profile_endpoint(provider: str, base_url: str | None) -> None:
    """Validate the provider and the endpoint that a persisted profile would use."""
    if normalize_provider(provider) not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unsupported provider; choose one of {', '.join(sorted(SUPPORTED_PROVIDERS))}",
        )
    if normalize_provider(provider) in {"anthropic", "google"} and not base_url:
        return
    try:
        validate_provider_url(provider_base_url(LLMSettings(provider=provider, base_url=base_url)))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.get("", response_model=list[ProviderProfileRead])
async def list_providers(session: AsyncSession = Depends(async_get_db)) -> list[ProviderProfileRead]:
    """List provider metadata without exposing credentials."""
    return [_read(profile) for profile in await profiles_crud.list_all(session)]


@router.post("", response_model=ProviderProfileRead, status_code=status.HTTP_201_CREATED)
async def create_provider(data: ProviderWrite, session: AsyncSession = Depends(async_get_db)) -> ProviderProfileRead:
    """Create a provider profile and encrypt its credential before persistence."""
    _validate_profile_endpoint(data.provider, data.base_url)
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
    _validate_profile_endpoint(
        str(changes.get("provider", profile.provider)),
        changes.get("base_url", profile.base_url),
    )
    for key, value in changes.items():
        setattr(profile, key, value)
    if data.api_key is not None:
        profile.api_key_encrypted = encrypt_secret(data.api_key.get_secret_value(), settings.secrets.master_key)
    profile.updated_at = datetime.now(UTC)
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return _read(profile)


@router.post("/{profile_id}/test", response_model=ProviderTestResponse)
async def test_provider(
    profile_id: int, session: AsyncSession = Depends(async_get_db)
) -> ProviderTestResponse:
    """Probe a provider without returning its response or credential."""
    profile = await profiles_crud.get(session, profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    try:
        config = settings_from_profile(profile)
        base_url = validate_provider_url(provider_base_url(config))
        url = f"{base_url}/chat/completions"
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    started = time.perf_counter()
    try:
        model_name = await resolve_model_name(config)
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            response = await client.post(
                url,
                headers={"Authorization": f"Bearer {config.api_key.get_secret_value()}"},
                json={"model": model_name, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1},
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Provider rejected the test request") from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Provider could not be reached") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return ProviderTestResponse(ok=True, message="Provider responded", latency_ms=round((time.perf_counter() - started) * 1000))


async def _models(config: LLMSettings) -> list[ModelOption]:
    """List a provider's models, mapping connectivity failures to HTTP errors."""
    try:
        return await list_models(config)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Provider could not be reached") from exc


@router.get("/default/models", response_model=list[ModelOption])
async def list_default_models() -> list[ModelOption]:
    """List models from the installation default provider (local LM Studio by default)."""
    return await _models(settings.llm)


@router.get("/{profile_id}/models", response_model=list[ModelOption])
async def list_profile_models(
    profile_id: int, session: AsyncSession = Depends(async_get_db)
) -> list[ModelOption]:
    """List the models a saved provider profile can serve (LM Studio marks loaded ones)."""
    profile = await profiles_crud.get(session, profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    try:
        config = settings_from_profile(profile)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    return await _models(config)
