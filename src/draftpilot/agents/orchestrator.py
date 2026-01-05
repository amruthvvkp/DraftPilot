"""PydanticAI agent orchestrator for DraftPilot."""

from typing import Any

import logfire
from pydantic_ai import Agent, RunContext

from draftpilot.core.config import settings

__all__ = ["create_agent", "create_agent_with_provider"]


def _create_model():
    """Create a PydanticAI model based on configuration settings.

    :return: Model instance configured for the specified provider.
    """
    provider = settings.llm_provider.lower()

    if provider == "openai":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        cfg = settings.openai
        openai_kwargs: dict[str, Any] = {}
        if cfg.api_key:
            openai_kwargs["api_key"] = cfg.api_key
        if cfg.base_url:
            openai_kwargs["base_url"] = cfg.base_url
        provider_instance = OpenAIProvider(**openai_kwargs)
        return OpenAIChatModel(cfg.model_name, provider=provider_instance)

    elif provider == "anthropic":
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider

        cfg = settings.anthropic
        anthropic_kwargs: dict[str, Any] = {}
        if cfg.api_key:
            anthropic_kwargs["api_key"] = cfg.api_key
        provider_instance = AnthropicProvider(**anthropic_kwargs)
        return AnthropicModel(cfg.model_name, provider=provider_instance)

    elif provider == "google":
        from pydantic_ai.models.google import GoogleModel
        from pydantic_ai.providers.google import GoogleProvider

        cfg = settings.google
        google_kwargs: dict[str, Any] = {}
        if cfg.api_key:
            google_kwargs["api_key"] = cfg.api_key
        if cfg.vertexai:
            google_kwargs["vertexai"] = True
        if cfg.project_id:
            google_kwargs["project"] = cfg.project_id
        if cfg.location:
            google_kwargs["location"] = cfg.location
        provider_instance = GoogleProvider(**google_kwargs)
        return GoogleModel(cfg.model_name, provider=provider_instance)

    elif provider == "azure":
        from openai import AsyncAzureOpenAI
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        cfg = settings.azure
        client = AsyncAzureOpenAI(
            azure_endpoint=cfg.endpoint or "",
            api_version=cfg.api_version or "2024-07-01-preview",
            api_key=cfg.api_key or "",
        )
        provider_instance = OpenAIProvider(openai_client=client)
        return OpenAIChatModel(cfg.model_name, provider=provider_instance)

    elif provider == "bedrock":
        from pydantic_ai.models.bedrock import BedrockConverseModel
        from pydantic_ai.providers.bedrock import BedrockProvider

        cfg = settings.bedrock
        provider_instance = BedrockProvider(
            region_name=cfg.region,
            aws_access_key_id=cfg.access_key_id,
            aws_secret_access_key=cfg.secret_access_key,
        )
        return BedrockConverseModel(cfg.model_name, provider=provider_instance)

    elif provider == "ollama":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.ollama import OllamaProvider

        cfg = settings.ollama
        provider_instance = OllamaProvider(
            base_url=cfg.base_url,
            api_key=cfg.api_key,
        )
        return OpenAIChatModel(cfg.model_name, provider=provider_instance)

    elif provider == "deepseek":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.deepseek import DeepSeekProvider

        cfg = settings.deepseek
        deepseek_kwargs: dict[str, Any] = {}
        if cfg.api_key:
            deepseek_kwargs["api_key"] = cfg.api_key
        provider_instance = DeepSeekProvider(**deepseek_kwargs)
        return OpenAIChatModel(cfg.model_name, provider=provider_instance)

    elif provider == "alibaba":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.alibaba import AlibabaProvider

        cfg = settings.alibaba
        alibaba_kwargs: dict[str, Any] = {}
        if cfg.api_key:
            alibaba_kwargs["api_key"] = cfg.api_key
        provider_instance = AlibabaProvider(**alibaba_kwargs)
        return OpenAIChatModel(cfg.model_name, provider=provider_instance)

    elif provider == "fireworks":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.fireworks import FireworksProvider

        cfg = settings.fireworks
        fireworks_kwargs: dict[str, Any] = {}
        if cfg.api_key:
            fireworks_kwargs["api_key"] = cfg.api_key
        provider_instance = FireworksProvider(**fireworks_kwargs)
        return OpenAIChatModel(cfg.model_name, provider=provider_instance)

    elif provider == "together":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.together import TogetherProvider

        cfg = settings.together
        together_kwargs: dict[str, Any] = {}
        if cfg.api_key:
            together_kwargs["api_key"] = cfg.api_key
        provider_instance = TogetherProvider(**together_kwargs)
        return OpenAIChatModel(cfg.model_name, provider=provider_instance)

    else:
        # Default to OpenAI-compatible with custom base_url
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        cfg = settings.openai
        default_kwargs: dict[str, Any] = {}
        if cfg.base_url:
            default_kwargs["base_url"] = cfg.base_url
        else:
            default_kwargs["base_url"] = "https://api.openai.com/v1"
        if cfg.api_key:
            default_kwargs["api_key"] = cfg.api_key
        provider_instance = OpenAIProvider(**default_kwargs)
        return OpenAIChatModel(cfg.model_name, provider=provider_instance)


def _create_model_settings():
    """Create model settings with thinking configuration based on provider.

    :return: Model settings instance with thinking enabled if configured, None otherwise.
    """
    provider = settings.llm_provider.lower()
    model_settings = None

    if provider == "openai":
        from pydantic_ai.models.openai import OpenAIResponsesModelSettings

        cfg = settings.openai
        if cfg.thinking_enabled or cfg.openai_responses_reasoning_effort:
            # For OpenAI Responses API
            if (
                cfg.openai_responses_reasoning_effort
                or cfg.openai_responses_reasoning_summary
            ):
                settings_kwargs: dict[str, Any] = {}
                if cfg.openai_responses_reasoning_effort:
                    settings_kwargs["openai_reasoning_effort"] = (
                        cfg.openai_responses_reasoning_effort
                    )
                if cfg.openai_responses_reasoning_summary:
                    settings_kwargs["openai_reasoning_summary"] = (
                        cfg.openai_responses_reasoning_summary
                    )
                if settings_kwargs:
                    model_settings = OpenAIResponsesModelSettings(**settings_kwargs)
            # For OpenAI Chat with thinking tags
            elif cfg.thinking_tags:
                # Thinking tags are handled via model profile, not settings
                pass

    elif provider == "anthropic":
        from pydantic_ai.models.anthropic import AnthropicModelSettings

        cfg = settings.anthropic
        if cfg.thinking_enabled and cfg.thinking_budget_tokens:
            model_settings = AnthropicModelSettings(
                anthropic_thinking={
                    "type": "enabled",
                    "budget_tokens": cfg.thinking_budget_tokens,
                }
            )

    elif provider == "google":
        from pydantic_ai.models.google import GoogleModelSettings

        cfg = settings.google
        if cfg.thinking_enabled:
            # Google thinking config requires specific structure
            thinking_config: dict[str, Any] = {"include_thoughts": True}
            if cfg.thinking_budget is not None:
                thinking_config["thinking_budget"] = cfg.thinking_budget
            # Type cast to satisfy type checker - the dict structure matches ThinkingConfigDict
            model_settings = GoogleModelSettings(
                google_thinking_config=thinking_config  # type: ignore[arg-type]
            )

    elif provider == "bedrock":
        from pydantic_ai.models.bedrock import BedrockModelSettings

        cfg = settings.bedrock
        if cfg.thinking_enabled and cfg.thinking_budget_tokens:
            model_settings = BedrockModelSettings(
                bedrock_additional_model_requests_fields={
                    "thinking": {
                        "type": "enabled",
                        "budget_tokens": cfg.thinking_budget_tokens,
                    }
                }
            )

    return model_settings


def create_agent() -> Agent:
    """Create and configure a PydanticAI agent.

    Returns an agent configured based on settings. Supports multiple providers:
    - OpenAI and OpenAI-compatible APIs (Ollama, LMStudio, etc.)
    - Anthropic/Claude (including Bedrock)
    - Google/GCP (Vertex AI)
    - Azure OpenAI
    - AWS Bedrock
    - DeepSeek, Alibaba, Fireworks, Together AI, etc.

    :return: Configured PydanticAI agent instance.
    """
    model = _create_model()
    model_settings = _create_model_settings()

    agent = Agent(
        model=model,
        system_prompt="You are a helpful assistant for DraftPilot, a screenplay editing platform.",
        model_settings=model_settings,
    )

    # Add a simple tool for demonstration
    @agent.tool
    async def greet(ctx: RunContext, name: str) -> str:
        """Greet someone by name.

        :param ctx: Run context (automatically provided).
        :param name: The name of the person to greet.
        :return: A greeting message.
        """
        with logfire.span("agent.greet", name=name):
            return f"Hello, {name}! Welcome to DraftPilot."

    return agent


def create_agent_with_provider(provider: str, model_name: str) -> Agent:
    """Create a PydanticAI agent with a specific provider and model.

    This function allows runtime selection of provider and model without
    modifying global settings.

    :param provider: LLM provider name (e.g., "ollama", "openai", "anthropic").
    :param model_name: Model name/identifier for the selected provider.
    :return: Configured PydanticAI agent instance.
    """
    provider_lower = provider.lower()

    # Create model based on provider
    if provider_lower == "openai":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        provider_instance = OpenAIProvider(
            api_key=settings.openai.api_key, base_url=settings.openai.base_url
        )
        model = OpenAIChatModel(model_name, provider=provider_instance)

    elif provider_lower == "anthropic":
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider

        provider_instance = AnthropicProvider(api_key=settings.anthropic.api_key)
        model = AnthropicModel(model_name, provider=provider_instance)

    elif provider_lower == "google":
        from pydantic_ai.models.google import GoogleModel
        from pydantic_ai.providers.google import GoogleProvider

        google_kwargs: dict[str, Any] = {}
        if settings.google.api_key:
            google_kwargs["api_key"] = settings.google.api_key
        if settings.google.vertexai:
            google_kwargs["vertexai"] = True
        if settings.google.project_id:
            google_kwargs["project"] = settings.google.project_id
        if settings.google.location:
            google_kwargs["location"] = settings.google.location
        provider_instance = GoogleProvider(**google_kwargs)
        model = GoogleModel(model_name, provider=provider_instance)

    elif provider_lower == "ollama":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.ollama import OllamaProvider

        provider_instance = OllamaProvider(
            base_url=settings.ollama.base_url, api_key=settings.ollama.api_key
        )
        model = OpenAIChatModel(model_name, provider=provider_instance)

    elif provider_lower == "deepseek":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.deepseek import DeepSeekProvider

        deepseek_kwargs: dict[str, Any] = {}
        if settings.deepseek.api_key:
            deepseek_kwargs["api_key"] = settings.deepseek.api_key
        provider_instance = DeepSeekProvider(**deepseek_kwargs)
        model = OpenAIChatModel(model_name, provider=provider_instance)

    elif provider_lower == "together":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.together import TogetherProvider

        together_kwargs: dict[str, Any] = {}
        if settings.together.api_key:
            together_kwargs["api_key"] = settings.together.api_key
        provider_instance = TogetherProvider(**together_kwargs)
        model = OpenAIChatModel(model_name, provider=provider_instance)

    else:
        # Default to OpenAI-compatible
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        provider_instance = OpenAIProvider(
            api_key=settings.openai.api_key, base_url=settings.openai.base_url
        )
        model = OpenAIChatModel(model_name, provider=provider_instance)

    # Create agent with the model
    agent = Agent(
        model=model,
        system_prompt="You are a helpful assistant for DraftPilot, a screenplay editing platform.",
    )

    return agent
