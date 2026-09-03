"""Encrypted server-side LLM provider profile model."""

from datetime import datetime

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel

from draftpilot.models.base import _utcnow


class ProviderProfileBase(SQLModel):
    """Shared non-secret provider profile fields."""

    name: str = Field(min_length=1, max_length=100, index=True)
    provider: str = Field(min_length=1, max_length=50)
    model: str = Field(min_length=1, max_length=200)
    base_url: str | None = Field(default=None, max_length=1000)
    enabled: bool = True


class ProviderProfile(ProviderProfileBase, table=True):  # type: ignore[call-arg]
    """Persist an LLM profile with its credential encrypted at rest."""

    __tablename__ = "provider_profile"

    id: int | None = Field(default=None, primary_key=True)
    api_key_encrypted: str | None = Field(default=None, max_length=2000)
    created_at: datetime = Field(default_factory=_utcnow, sa_type=DateTime(timezone=True))  # type: ignore[call-overload]
    updated_at: datetime = Field(default_factory=_utcnow, sa_type=DateTime(timezone=True))  # type: ignore[call-overload]


class ProviderProfileCreate(ProviderProfileBase):
    """Describe a provider profile and its write-only credential."""

    api_key: str | None = None


class ProviderProfileUpdate(SQLModel):
    """Describe an optional provider profile update."""

    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    enabled: bool | None = None
    api_key: str | None = None


class ProviderProfileRead(ProviderProfileBase):
    """Return provider metadata without returning the credential."""

    id: int
    has_api_key: bool
    created_at: datetime
    updated_at: datetime
