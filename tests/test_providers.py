"""Test provider endpoint selection without making model calls."""

from typing import Self

import pytest
from _async import run_async
from cryptography.fernet import Fernet
from fastapi import HTTPException
from pydantic import SecretStr

from draftpilot.api.providers import _validate_profile_endpoint
from draftpilot.api.providers import test_provider as probe_provider
from draftpilot.core.config import LLMSettings, settings
from draftpilot.core.providers import (
    create_chat_model,
    provider_base_url,
    settings_from_profile,
    validate_provider_url,
)
from draftpilot.core.security import encrypt_secret
from draftpilot.models import ProviderProfile


def test_provider_defaults_cover_local_and_gateway_endpoints() -> None:
    """Resolve documented provider defaults while allowing explicit overrides."""
    assert provider_base_url(LLMSettings(provider="ollama")) == "http://localhost:11434/v1"
    assert provider_base_url(LLMSettings(provider="LM Studio")) == "http://localhost:1234/v1"
    assert provider_base_url(LLMSettings(provider="lm-studio")) == "http://localhost:1234/v1"
    assert provider_base_url(
        LLMSettings(provider="gateway", base_url="http://gateway:8080/v1/", api_key=SecretStr("x"))
    ) == "http://gateway:8080/v1"


def test_enabled_profile_is_decrypted_only_into_private_runtime_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolve an encrypted profile without exposing its credential in response models."""
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings.secrets, "master_key", SecretStr(key))
    profile = ProviderProfile(
        id=4,
        name="Local model",
        provider="ollama",
        model="llama3.2",
        api_key_encrypted=encrypt_secret("private-key", SecretStr(key)),
    )
    runtime = settings_from_profile(profile)
    assert runtime.enabled is True
    assert runtime.api_key.get_secret_value() == "private-key"
    assert profile.api_key_encrypted != runtime.api_key.get_secret_value()


def test_disabled_profile_cannot_be_selected() -> None:
    """Reject disabled profiles before model construction."""
    with pytest.raises(ValueError, match="disabled"):
        settings_from_profile(ProviderProfile(name="Disabled", provider="ollama", model="x", enabled=False))


def test_provider_url_rejects_metadata_endpoint() -> None:
    """Reject cloud metadata URLs before any provider request is made."""
    with pytest.raises(ValueError, match="metadata"):
        validate_provider_url("http://169.254.169.254/latest/meta-data")


def test_provider_url_rejects_private_ip_literal() -> None:
    """Reject private provider endpoints before an outbound model request."""
    with pytest.raises(ValueError, match="Private"):
        validate_provider_url("http://10.0.0.8:11434/v1")
    assert validate_provider_url("http://127.0.0.1:11434/v1") == "http://127.0.0.1:11434/v1"


def test_provider_url_rejects_private_dns_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reject provider hostnames resolving into private network space."""
    monkeypatch.setattr(
        "draftpilot.core.providers.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(0, 0, 0, "", ("10.0.0.8", 443))],
    )
    with pytest.raises(ValueError, match="Private"):
        validate_provider_url("https://provider.example/v1")


def test_provider_profile_endpoint_validation_runs_before_persistence() -> None:
    """Reject an unsafe profile endpoint at the settings boundary."""
    with pytest.raises(HTTPException) as error:
        _validate_profile_endpoint("gateway", "http://10.0.0.8:8080/v1")
    assert error.value.status_code == 422
    assert "Private" in str(error.value.detail)


def test_model_construction_enforces_provider_url_validation() -> None:
    """Reject an unsafe explicit endpoint before constructing a provider model."""
    with pytest.raises(ValueError, match="Private"):
        create_chat_model(LLMSettings(provider="ollama", base_url="http://10.0.0.8:11434/v1"))


def test_provider_probe_returns_safe_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Probe an OpenAI-compatible endpoint without returning provider content."""
    import httpx

    class Client:
        """Provide a deterministic HTTP client fixture."""

        def __init__(self, **_kwargs: object) -> None:
            """Accept production client options for the fixture."""

        async def __aenter__(self) -> Self:
            """Enter the HTTP client fixture."""
            return self

        async def __aexit__(self, *_args: object) -> None:
            """Close the HTTP client fixture."""

        async def post(self, *_args: object, **_kwargs: object) -> httpx.Response:
            """Return a successful provider response."""
            return httpx.Response(200, request=httpx.Request("POST", "http://provider.test"))

    async def get(_session: object, _profile_id: int) -> ProviderProfile:
        """Return an isolated provider profile."""
        return ProviderProfile(name="Local", provider="ollama", model="test", base_url="http://provider.test/v1")

    monkeypatch.setattr("draftpilot.api.providers.profiles_crud.get", get)
    monkeypatch.setattr("draftpilot.api.providers.httpx.AsyncClient", Client)
    monkeypatch.setattr(
        "draftpilot.core.providers.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(0, 0, 0, "", ("93.184.216.34", 443))],
    )
    response = run_async(probe_provider(3, object()))
    assert response.ok is True
    assert "provider.test" not in response.model_dump_json()
