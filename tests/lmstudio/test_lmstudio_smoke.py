"""Prove the Tier 1 path: PydanticAI structured output against local LM Studio."""

import pytest
from _async import run_async
from _lmstudio import LMStudio
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from draftpilot.core.config import settings

pytestmark = pytest.mark.lmstudio


class Slugline(BaseModel):
    """Capture one screenplay scene heading."""

    heading: str


def test_lmstudio_returns_structured_output(lmstudio: LMStudio) -> None:
    """A loaded LM Studio model answers a structured request through PydanticAI."""
    model_name = settings.eval.chat_model or lmstudio.chat_models[0]
    model = OpenAIChatModel(
        model_name, provider=OpenAIProvider(base_url=lmstudio.base_url, api_key="lm-studio")
    )
    agent = Agent(model, output_type=Slugline, instructions="Answer with a screenplay slugline.")
    result = run_async(agent.run("A diner at night, seen from inside."))
    assert result.output.heading.strip()
    assert result.output.heading.upper().startswith(("INT", "EXT"))
