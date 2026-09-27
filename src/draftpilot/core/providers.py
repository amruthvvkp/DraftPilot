"""Build PydanticAI models from server-side provider configuration.

Local model servers (LM Studio, Ollama) and OpenAI-compatible gateways go through
``OpenAIChatModel`` (Chat Completions); Anthropic and Google use their native models.
LM Studio gets a model profile without strict tool schemas, which local servers do not
enforce, and ``model="auto"`` resolves to the first model LM Studio reports as loaded.
"""

import ipaddress
import socket
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, SecretStr

from draftpilot.core.config import LLMSettings, settings
from draftpilot.core.security import decrypt_secret
from draftpilot.models import ProviderProfile

_DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "ollama": "http://localhost:11434/v1",
    "lm_studio": "http://localhost:1234/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}
_OPENAI_COMPATIBLE = {"openai", "openrouter", "gateway", "ollama", "lm_studio"}
_NATIVE = {"anthropic", "google"}
SUPPORTED_PROVIDERS = frozenset(_OPENAI_COMPATIBLE | _NATIVE)
AUTO_MODEL = "auto"


class ModelOption(BaseModel):
    """Describe one model a provider can serve."""

    id: str
    loaded: bool = True
    kind: str = "llm"


def normalize_provider(name: str) -> str:
    """Return the canonical provider key (``LM Studio`` and ``lm-studio`` become ``lm_studio``)."""
    return name.strip().casefold().replace(" ", "_").replace("-", "_")


def provider_base_url(config: LLMSettings) -> str | None:
    """Resolve an explicit or provider-specific OpenAI-compatible endpoint."""
    if config.base_url:
        return config.base_url.rstrip("/")
    return _DEFAULT_BASE_URLS.get(normalize_provider(config.provider))


def _unsafe(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return whether an address is a private, link-local, reserved, or multicast target."""
    return (
        address.is_private or address.is_link_local or address.is_reserved or address.is_multicast
    ) and not address.is_loopback


def validate_provider_url(url: str | None) -> str:
    """Validate an OpenAI-compatible URL before making an outbound request.

    Loopback hosts and the explicitly trusted local model hosts are allowed; other private,
    link-local, and cloud-metadata targets are rejected to prevent SSRF.
    """
    if not url:
        raise ValueError("Provider URL is not configured")
    parsed = urlsplit(url)
    blocked_hosts = {"169.254.169.254", "metadata.google.internal", "metadata.google.com"}
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Provider URL must be an HTTP(S) URL without embedded credentials")
    hostname = parsed.hostname.casefold()
    if hostname in blocked_hosts:
        raise ValueError("Provider metadata endpoints are not allowed")
    if hostname == "localhost" or hostname in {host.casefold() for host in settings.llm.trusted_model_hosts}:
        return url.rstrip("/")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None:
        if _unsafe(address):
            raise ValueError("Private provider endpoints are not allowed")
        return url.rstrip("/")
    try:
        resolved = socket.getaddrinfo(
            hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM
        )
    except socket.gaierror as exc:
        raise ValueError("Provider endpoint hostname could not be resolved") from exc
    if any(_unsafe(ipaddress.ip_address(result[4][0])) for result in resolved):
        raise ValueError("Private provider endpoints are not allowed")
    return url.rstrip("/")


def _lm_studio_profile(model_name: str) -> Any:
    """Return an OpenAI-compatible profile for LM Studio: model-family defaults, no strict tools."""
    from pydantic_ai.profiles import merge_profile
    from pydantic_ai.profiles.openai import OpenAIModelProfile
    from pydantic_ai.providers.ollama import OllamaProvider

    family = OllamaProvider.model_profile(model_name.split("/")[-1])
    return merge_profile(
        family,
        OpenAIModelProfile(
            openai_supports_strict_tool_definition=False,
            supports_json_schema_output=True,
            supports_json_object_output=True,
        ),
    )


async def list_models(config: LLMSettings) -> list[ModelOption]:
    """List the chat models a provider serves; LM Studio also reports which are loaded."""
    provider = normalize_provider(config.provider)
    if provider in _NATIVE:
        return [ModelOption(id=config.model)] if config.model and config.model != AUTO_MODEL else []
    base = validate_provider_url(provider_base_url(config))
    headers = {"Authorization": f"Bearer {config.api_key.get_secret_value()}"} if config.api_key.get_secret_value() else {}
    async with httpx.AsyncClient(timeout=5.0, headers=headers) as client:
        if provider == "lm_studio":
            root = base.removesuffix("/v1")
            try:
                native = await client.get(f"{root}/api/v0/models")
                native.raise_for_status()
                entries = native.json().get("data", [])
                options = [
                    ModelOption(id=item["id"], loaded=item.get("state") == "loaded", kind=item.get("type", "llm"))
                    for item in entries
                    if isinstance(item, dict) and "id" in item
                ]
                return sorted(options, key=lambda option: (not option.loaded, option.kind != "llm"))
            except (httpx.HTTPError, ValueError):
                pass
        response = await client.get(f"{base}/models")
        response.raise_for_status()
        return [
            ModelOption(id=item["id"], kind="embeddings" if "embed" in item["id"].casefold() else "llm")
            for item in response.json().get("data", [])
            if isinstance(item, dict) and "id" in item
        ]


async def resolve_model_name(config: LLMSettings) -> str:
    """Return the configured model, resolving ``auto`` to a loaded chat model."""
    if config.model and config.model != AUTO_MODEL:
        return config.model
    options = [option for option in await list_models(config) if option.kind in {"llm", "vlm"}]
    if not options:
        raise RuntimeError(f"No chat model is available from {config.provider}")
    loaded = [option for option in options if option.loaded]
    return (loaded or options)[0].id


def create_chat_model(config: LLMSettings, model_name: str | None = None) -> Any:
    """Create a PydanticAI chat model for a configured provider."""
    provider_name = normalize_provider(config.provider)
    if provider_name not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unsupported LLM provider: {config.provider}")
    name = model_name or config.model
    if not name or name == AUTO_MODEL:
        raise ValueError("Resolve the model name before creating a model")
    api_key = config.api_key.get_secret_value()
    if provider_name == "anthropic":
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider

        return AnthropicModel(name, provider=AnthropicProvider(api_key=api_key or None))
    if provider_name == "google":
        from pydantic_ai.models.google import GoogleModel
        from pydantic_ai.providers.google import GoogleProvider

        return GoogleModel(name, provider=GoogleProvider(api_key=api_key or None))
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    provider = OpenAIProvider(
        base_url=validate_provider_url(provider_base_url(config)),
        api_key=api_key or "not-needed",
    )
    profile = _lm_studio_profile(name) if provider_name == "lm_studio" else None
    return OpenAIChatModel(name, provider=provider, profile=profile)


async def build_chat_model(config: LLMSettings) -> tuple[Any, str]:
    """Resolve the model name (including ``auto``) and return ``(model, model_name)``."""
    name = await resolve_model_name(config)
    return create_chat_model(config, name), name


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
