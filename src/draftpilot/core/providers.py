"""Build PydanticAI models from server-side provider configuration."""

from typing import Any

from pydantic import SecretStr

from draftpilot.core.config import LLMSettings, settings
from draftpilot.core.security import decrypt_secret
from draftpilot.models import ProviderProfile

_DEFAULT_BASE_URLS = {
    "ollama": "http://localhost:11434/v1",
    "lm_studio": "http://localhost:1234/v1",
    "lm-studio": "http://localhost:1234/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}


def provider_base_url(config: LLMSettings) -> str | None:
    """Resolve an explicit or provider-specific OpenAI-compatible endpoint."""
    if config.base_url:
        return config.base_url.rstrip("/")
    return _DEFAULT_BASE_URLS.get(config.provider.casefold().replace(" ", "_"))


def create_chat_model(config: LLMSettings) -> Any:
    """Create a PydanticAI chat model for supported provider endpoints."""
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    provider_name = config.provider.casefold().replace(" ", "_")
    supported = {"openai", "openrouter", "gateway", "ollama", "lm_studio", "lm-studio"}
    if provider_name not in supported:
        raise ValueError(f"Unsupported LLM provider: {config.provider}")
    provider = OpenAIProvider(
        base_url=provider_base_url(config),
        api_key=config.api_key.get_secret_value() or "not-needed",
    )
    return OpenAIChatModel(config.model, provider=provider)


def settings_from_profile(profile: ProviderProfile) -> LLMSettings:
    """Build private runtime settings from an enabled encrypted provider profile."""
    if not profile.enabled:
        raise ValueError("Provider profile is disabled")
    api_key = ""
    if profile.api_key_encrypted is not None:
        api_key = decrypt_secret(profile.api_key_encrypted, settings.secrets.master_key)
    return LLMSettings(
        provider=profile.provider,
        base_url=profile.base_url,
        api_key=SecretStr(api_key),
        model=profile.model,
        enabled=True,
    )
