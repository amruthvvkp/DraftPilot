"""ARQ background tasks.

``analyze_screenplay`` computes deterministic structural metrics for a
screenplay and, when an LLM provider is configured, augments them with a short
qualitative note via a PydanticAI agent. Results are cached in Redis so the UI
can display them. The LLM step is fully optional — the task always returns the
deterministic metrics even when no model is reachable.
"""

import logfire

from draftpilot.core.cache import cache_set
from draftpilot.core.config import settings
from draftpilot.core.db import session_scope
from draftpilot.crud import scenes as scenes_crud
from draftpilot.crud import screenplays as screenplays_crud

ANALYSIS_CACHE_KEY = "analysis:{id}"


async def _llm_note(title: str, scene_count: int, word_count: int) -> str | None:
    """Optional one-line qualitative note from a PydanticAI agent."""
    if not settings.llm.enabled:
        return None
    try:
        from pydantic_ai import Agent
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        provider = OpenAIProvider(
            base_url=settings.llm.base_url,
            api_key=settings.llm.api_key.get_secret_value() or "not-needed",
        )
        model = OpenAIChatModel(settings.llm.model, provider=provider)
        agent = Agent(
            model,
            system_prompt=(
                "You are a script consultant. Given basic stats about a screenplay, "
                "reply with a single concise sentence of constructive feedback."
            ),
        )
        result = await agent.run(
            f"Title: {title}. Scenes: {scene_count}. Words: {word_count}."
        )
        return result.output
    except Exception as exc:  # pragma: no cover - provider/network dependent
        logfire.warning("LLM note skipped: {exc}", exc=str(exc))
        return None


async def analyze_screenplay(ctx: dict, screenplay_id: int) -> dict:
    """Compute metrics for a screenplay and cache the result in Redis."""
    with logfire.span("analyze_screenplay", screenplay_id=screenplay_id):
        async with session_scope() as session:
            screenplay = await screenplays_crud.get(session, screenplay_id)
            if screenplay is None:
                logfire.warning("Screenplay {id} not found", id=screenplay_id)
                return {"error": "not_found"}
            scenes = await scenes_crud.list_for_screenplay(session, screenplay_id)
            title = screenplay.title

        scene_count = len(scenes)
        word_count = sum(len(s.body.split()) for s in scenes)
        avg_scene_words = round(word_count / scene_count, 1) if scene_count else 0

        result: dict = {
            "scene_count": scene_count,
            "word_count": word_count,
            "avg_scene_words": avg_scene_words,
            "estimated_pages": round(word_count / 190, 1),  # ~190 words/page heuristic
        }

        note = await _llm_note(title, scene_count, word_count)
        if note:
            result["note"] = note

        await cache_set(ANALYSIS_CACHE_KEY.format(id=screenplay_id), result, ttl=3600)
        logfire.info("Analysis complete for {id}: {result}", id=screenplay_id, result=result)
        return result
