"""Test provider endpoint selection without making model calls."""

from cryptography.fernet import Fernet
from pydantic import SecretStr
import pytest

from draftpilot.core.config import LLMSettings, settings
from draftpilot.core.providers import provider_base_url, settings_from_profile
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
