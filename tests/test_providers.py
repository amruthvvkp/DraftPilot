"""Test provider endpoint selection without making model calls."""

from cryptography.fernet import Fernet
from pydantic import SecretStr
import pytest

from draftpilot.core.config import LLMSettings, settings
from draftpilot.api.providers import test_provider as probe_provider
from draftpilot.core.providers import provider_base_url, settings_from_profile, validate_provider_url
from draftpilot.core.security import encrypt_secret
from draftpilot.models import ProviderProfile
from _async import run_async


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


def test_provider_probe_returns_safe_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Probe an OpenAI-compatible endpoint without returning provider content."""
    import httpx

    class Client:
        """Provide a deterministic HTTP client fixture."""

        def __init__(self, **_kwargs: object) -> None:
            """Accept production client options for the fixture."""

        async def __aenter__(self) -> "Client":
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
    response = run_async(probe_provider(3, object()))
    assert response.ok is True
    assert "provider.test" not in response.model_dump_json()
