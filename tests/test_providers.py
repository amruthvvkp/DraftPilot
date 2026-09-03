"""Test provider endpoint selection without making model calls."""

from pydantic import SecretStr

from draftpilot.core.config import LLMSettings
from draftpilot.core.providers import provider_base_url


def test_provider_defaults_cover_local_and_gateway_endpoints() -> None:
    """Resolve documented provider defaults while allowing explicit overrides."""
    assert provider_base_url(LLMSettings(provider="ollama")) == "http://localhost:11434/v1"
    assert provider_base_url(LLMSettings(provider="LM Studio")) == "http://localhost:1234/v1"
    assert provider_base_url(LLMSettings(provider="lm-studio")) == "http://localhost:1234/v1"
    assert provider_base_url(
        LLMSettings(provider="gateway", base_url="http://gateway:8080/v1/", api_key=SecretStr("x"))
    ) == "http://gateway:8080/v1"
