"""Shared pytest configuration: tier markers, the model-request guard, and the LM Studio fixture.

Tier 0 must never reach a model: the default LLM is disabled for tests and PydanticAI's
``ALLOW_MODEL_REQUESTS`` guard fails any accidental real call. The ``lmstudio`` fixture
re-enables both for Tier 1 tests, which always target local LM Studio.
"""

import os
from collections.abc import Iterator
from pathlib import Path

os.environ.setdefault("LLM__ENABLED", "false")
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

import httpx
import pytest
from _lmstudio import LMStudio, discover_lmstudio
from pydantic_ai import models

from draftpilot.core.config import settings

E2E_DIR = Path(__file__).parent / "e2e"
models.ALLOW_MODEL_REQUESTS = False


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Mark every browser journey under ``tests/e2e`` with the ``e2e`` marker."""
    for item in items:
        if E2E_DIR in Path(str(item.fspath)).parents:
            item.add_marker(pytest.mark.e2e)


@pytest.fixture(scope="session")
def lmstudio() -> Iterator[LMStudio]:
    """Return the local LM Studio server, failing loudly when it is unreachable."""
    base_url = settings.eval.base_url
    try:
        server = discover_lmstudio(base_url)
    except httpx.HTTPError as exc:
        pytest.fail(
            f"LM Studio is not reachable at {base_url} ({exc}). Start LM Studio's local server "
            "or set EVAL__BASE_URL; LM Studio tests never fall back to another provider."
        )
    if not server.chat_models:
        pytest.fail(f"LM Studio at {base_url} has no chat model available")
    models.ALLOW_MODEL_REQUESTS = True
    try:
        yield server
    finally:
        models.ALLOW_MODEL_REQUESTS = False
