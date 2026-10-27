"""Resolve the model a room run uses, by ref, so durable agents can switch models per run.

A Temporal activity cannot carry a ``Model`` instance, so a run carries a model ref instead
(``core.providers.model_ref``). ``describe_model`` does the I/O once, before the run: it loads the
provider profile and resolves LM Studio's ``auto``. ``resolve_room_model`` is the agents'
``ResolveModelId`` hook. It runs in workflow code, where it returns a no-I/O planning model, and
again in the model-request activity, where it builds the real one.
"""

from time import monotonic
from typing import Any

from pydantic_ai.models import Model, ModelResolutionContext
from temporalio import workflow

from draftpilot.core.config import LLMSettings, settings
from draftpilot.core.db import session_scope
from draftpilot.core.providers import (
    create_chat_model,
    model_ref,
    parse_model_ref,
    planning_model,
    resolve_model_name,
    settings_from_profile,
)
from draftpilot.crud import provider_profiles as profiles_crud

INSTANCE = "instance:"
MODEL_CACHE_SECONDS = 60.0

_instances: dict[str, Any] = {}
_built: dict[str, tuple[float, Any]] = {}


def register_model(model: Any, name: str | None = None) -> str:
    """Return a ref for a ready-made model instance (tests and evals), resolvable in this process only.

    ``name`` gives the ref a stable key, so recorded workflow histories that carry it can be replayed.
    """
    key = f"{INSTANCE}{name or id(model)}"
    _instances[key] = model
    return model_ref(key, str(getattr(model, "system", "test")), str(getattr(model, "model_name", "test")))


def default_ref() -> str:
    """Return the ref of the installation's default model (``auto`` is resolved by ``describe_model``)."""
    return model_ref("default", settings.llm.provider, settings.llm.model)


async def llm_settings(source: str) -> LLMSettings:
    """Return the provider settings a ref's source names: the installation default or a stored profile."""
    if source == "default":
        return settings.llm
    if source.startswith("profile:"):
        async with session_scope() as session:
            profile = await profiles_crud.get(session, int(source.removeprefix("profile:")))
        if profile is None:
            raise ValueError("Provider profile not found")
        return settings_from_profile(profile)
    raise ValueError(f"Unknown model source {source!r}")


async def describe_model(provider_profile_id: int | None = None) -> str:
    """Resolve a run's model (profile, ``auto``) once and return its ref; fails when the provider is disabled."""
    source = f"profile:{provider_profile_id}" if provider_profile_id is not None else "default"
    config = await llm_settings(source)
    if not config.enabled:
        raise RuntimeError("LLM provider is disabled")
    return model_ref(source, config.provider, await resolve_model_name(config))


async def resolve_room_model(_ctx: ModelResolutionContext[Any], model_id: str) -> Model | None:
    """Build the model a ref names: a planning model in workflow code, the real one anywhere else."""
    parsed = parse_model_ref(model_id)
    if parsed is None:
        return None
    source, provider, model_name = parsed
    if source.startswith(INSTANCE):
        return _instances[source]
    if workflow.in_workflow():
        return planning_model(provider, model_name)
    cached = _built.get(model_id)
    if cached is not None and monotonic() - cached[0] < MODEL_CACHE_SECONDS:
        return cached[1]
    model = create_chat_model(await llm_settings(source), model_name)
    _built[model_id] = (monotonic(), model)
    return model
