import os
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

try:
    import tomllib as toml
except ImportError:
    import toml  # type: ignore


__all__ = [
    "settings",
    "LogfireSettings",
    "OpenAISettings",
    "AnthropicSettings",
    "GoogleSettings",
    "AzureSettings",
    "BedrockSettings",
    "OllamaSettings",
    "DeepSeekSettings",
    "AlibabaSettings",
    "FireworksSettings",
    "TogetherSettings",
]

_ROOT = Path(__file__).parent.parent.parent.parent
_PYPROJECT_TOML = _ROOT / "pyproject.toml"

_cache: dict[str, Any] | None = None


def get_pyproject_toml_content() -> dict[str, Any]:
    """Get pyproject.toml content with caching."""
    global _cache
    if _cache is None:
        _cache = toml.loads(_PYPROJECT_TOML.read_text())
    return _cache


class Metadata(BaseSettings):
    @property
    def name(self) -> str:
        return get_pyproject_toml_content()["project"]["name"]

    @property
    def version(self) -> str:
        return get_pyproject_toml_content()["project"]["version"]

    @property
    def description(self) -> str:
        return get_pyproject_toml_content()["project"]["description"]


# Logfire settings
class LogfireSettings(BaseSettings):
    """Logfire OTEL observability settings."""

    model_config = SettingsConfigDict(env_prefix="draftpilot_logfire_")

    enabled: bool = Field(default=True, description="Enable Logfire tracing")
    service_name: str = Field(
        default="draftpilot", description="Service name for Logfire traces"
    )
    otel_endpoint: str = Field(
        default="http://localhost:4318",
        description="OTEL collector endpoint (OTLP/HTTP)",
    )


# Provider-specific settings classes
class OpenAISettings(BaseSettings):
    """OpenAI and OpenAI-compatible API settings."""

    model_config = SettingsConfigDict(env_prefix="draftpilot_openai_")

    model_name: str = Field(default="gpt-4o-mini", description="Model name/identifier")
    api_key: str | None = Field(
        default=None, description="API key (or set OPENAI_API_KEY env var)"
    )
    base_url: str | None = Field(
        default=None,
        description="Custom base URL for OpenAI-compatible APIs (e.g., Ollama, LMStudio)",
    )
    # Thinking configuration
    thinking_enabled: bool = Field(
        default=False, description="Enable thinking/reasoning capabilities"
    )
    thinking_tags: tuple[str, str] | None = Field(
        default=None,
        description="Custom thinking tags tuple (start_tag, end_tag) for OpenAI-compatible models",
    )
    openai_responses_reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh"] | None = Field(
        default=None,
        description="Reasoning effort for OpenAI Responses API",
    )
    openai_responses_reasoning_summary: Literal["detailed", "concise", "auto"] | None = Field(
        default=None,
        description="Reasoning summary for OpenAI Responses API",
    )


class AnthropicSettings(BaseSettings):
    """Anthropic/Claude API settings."""

    model_config = SettingsConfigDict(env_prefix="draftpilot_anthropic_")

    model_name: str = Field(
        default="claude-sonnet-4-5", description="Model name/identifier"
    )
    api_key: str | None = Field(
        default=None, description="API key (or set ANTHROPIC_API_KEY env var)"
    )
    # Thinking configuration
    thinking_enabled: bool = Field(
        default=False, description="Enable thinking/reasoning capabilities"
    )
    thinking_budget_tokens: int | None = Field(
        default=None,
        description="Token budget for thinking (e.g., 1024). Required if thinking_enabled=True",
    )


class GoogleSettings(BaseSettings):
    """Google/GCP API settings."""

    model_config = SettingsConfigDict(env_prefix="draftpilot_google_")

    model_name: str = Field(
        default="gemini-2.5-pro", description="Model name/identifier"
    )
    api_key: str | None = Field(
        default=None, description="API key (or set GOOGLE_API_KEY env var)"
    )
    vertexai: bool = Field(
        default=False, description="Use Vertex AI instead of Generative Language API"
    )
    project_id: str | None = Field(
        default=None, description="GCP project ID for Vertex AI"
    )
    location: str | None = Field(
        default=None, description="GCP location/region for Vertex AI"
    )
    # Thinking configuration
    thinking_enabled: bool = Field(
        default=False, description="Enable thinking/reasoning capabilities"
    )
    thinking_budget: int | None = Field(
        default=None,
        description="Thinking budget (0 to disable, or token count). For models older than Gemini 2.5 Pro",
    )


class AzureSettings(BaseSettings):
    """Azure OpenAI settings."""

    model_config = SettingsConfigDict(env_prefix="draftpilot_azure_")

    model_name: str = Field(default="gpt-4", description="Model name/identifier")
    endpoint: str | None = Field(default=None, description="Azure OpenAI endpoint")
    api_key: str | None = Field(default=None, description="Azure OpenAI API key")
    api_version: str | None = Field(
        default="2024-07-01-preview", description="Azure API version"
    )


class BedrockSettings(BaseSettings):
    """AWS Bedrock settings."""

    model_config = SettingsConfigDict(env_prefix="draftpilot_bedrock_")

    model_name: str = Field(
        default="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        description="Model name/identifier",
    )
    region: str = Field(default="us-east-1", description="AWS region for Bedrock")
    access_key_id: str | None = Field(default=None, description="AWS access key ID")
    secret_access_key: str | None = Field(
        default=None, description="AWS secret access key"
    )
    # Thinking configuration
    thinking_enabled: bool = Field(
        default=False, description="Enable thinking/reasoning capabilities"
    )
    thinking_budget_tokens: int | None = Field(
        default=None,
        description="Token budget for thinking (e.g., 1024). Used for Claude models on Bedrock",
    )


class OllamaSettings(BaseSettings):
    """Ollama settings."""

    model_config = SettingsConfigDict(env_prefix="draftpilot_ollama_")

    model_name: str = Field(default="llama3", description="Model name/identifier")
    base_url: str = Field(
        default="http://localhost:11434/v1",
        description="Ollama base URL. Use 'http://host.docker.internal:11434/v1' when running in Docker to access Ollama on host machine (Mac/Windows).",
    )
    api_key: str | None = Field(
        default=None, description="Ollama API key (for Ollama Cloud)"
    )


class DeepSeekSettings(BaseSettings):
    """DeepSeek API settings."""

    model_config = SettingsConfigDict(env_prefix="draftpilot_deepseek_")

    model_name: str = Field(
        default="deepseek-chat", description="Model name/identifier"
    )
    api_key: str | None = Field(default=None, description="DeepSeek API key")


class AlibabaSettings(BaseSettings):
    """Alibaba/DashScope API settings."""

    model_config = SettingsConfigDict(env_prefix="draftpilot_alibaba_")

    model_name: str = Field(default="qwen-max", description="Model name/identifier")
    api_key: str | None = Field(default=None, description="Alibaba/DashScope API key")


class FireworksSettings(BaseSettings):
    """Fireworks AI settings."""

    model_config = SettingsConfigDict(env_prefix="draftpilot_fireworks_")

    model_name: str = Field(
        default="accounts/fireworks/models/qwq-32b", description="Model name/identifier"
    )
    api_key: str | None = Field(default=None, description="Fireworks API key")


class TogetherSettings(BaseSettings):
    """Together AI settings."""

    model_config = SettingsConfigDict(env_prefix="draftpilot_together_")

    model_name: str = Field(
        default="meta-llama/Llama-3.3-70B-Instruct-Turbo-Free",
        description="Model name/identifier",
    )
    api_key: str | None = Field(default=None, description="Together AI API key")


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(env_prefix="draftpilot_")

    metadata: Metadata = Metadata()

    # Redis settings
    redis_url: str = Field(default="redis://localhost:6379")
    nicegui_redis_url: str | None = Field(
        default=None,
        description="NiceGUI Redis URL. If None, NiceGUI uses file-based storage (default for local dev)",
    )

    @model_validator(mode="after")
    def set_nicegui_redis_url(self) -> "Settings":
        """Set NICEGUI_REDIS_URL environment variable if configured.

        This ensures NiceGUI uses Redis when explicitly configured,
        otherwise falls back to file-based storage for local development.

        :return: Settings instance (for chaining).
        """
        if self.nicegui_redis_url:
            os.environ["NICEGUI_REDIS_URL"] = self.nicegui_redis_url
        # If not set, NiceGUI defaults to file-based storage in .nicegui directory
        return self

    # Logfire settings
    logfire: LogfireSettings = Field(default_factory=LogfireSettings)

    # FastMCP settings
    mcp_mount_path: str = Field(default="/mcp")

    # LLM Provider selection
    llm_provider: str = Field(
        default="openai",
        description="LLM provider name: openai, anthropic, google, azure, bedrock, ollama, deepseek, alibaba, fireworks, together",
    )

    # Provider-specific settings
    openai: OpenAISettings = Field(default_factory=OpenAISettings)
    anthropic: AnthropicSettings = Field(default_factory=AnthropicSettings)
    google: GoogleSettings = Field(default_factory=GoogleSettings)
    azure: AzureSettings = Field(default_factory=AzureSettings)
    bedrock: BedrockSettings = Field(default_factory=BedrockSettings)
    ollama: OllamaSettings = Field(default_factory=OllamaSettings)
    deepseek: DeepSeekSettings = Field(default_factory=DeepSeekSettings)
    alibaba: AlibabaSettings = Field(default_factory=AlibabaSettings)
    fireworks: FireworksSettings = Field(default_factory=FireworksSettings)
    together: TogetherSettings = Field(default_factory=TogetherSettings)

    def get_llm_settings(self) -> BaseSettings:
        """Get the LLM settings for the currently selected provider.

        :return: The settings object for the active LLM provider.
        """
        provider = self.llm_provider.lower()
        provider_map = {
            "openai": self.openai,
            "anthropic": self.anthropic,
            "google": self.google,
            "azure": self.azure,
            "bedrock": self.bedrock,
            "ollama": self.ollama,
            "deepseek": self.deepseek,
            "alibaba": self.alibaba,
            "fireworks": self.fireworks,
            "together": self.together,
        }
        return provider_map.get(provider, self.openai)


settings = Settings()
