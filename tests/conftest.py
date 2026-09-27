"""Shared pytest configuration: tier markers, the model-request guard, and the LM Studio fixture.

Tier 0 must never reach a model: the default LLM is disabled for tests and PydanticAI's
``ALLOW_MODEL_REQUESTS`` guard fails any accidental real call. The ``lmstudio`` fixture
re-enables both for Tier 1 tests, which always target local LM Studio.
"""

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

os.environ.setdefault("LLM__ENABLED", "false")
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
# The in-process RAG service uses a throwaway SQLite store with deterministic hash embeddings.
os.environ.setdefault("RAG__BACKEND", "sqlite")
os.environ.setdefault("RAG__EMBEDDING_PROVIDER", "hash")
os.environ.setdefault("RAG__EMBEDDING_DIMENSIONS", "256")
os.environ.setdefault("RAG__DATABASE_PATH", os.path.join(tempfile.mkdtemp(prefix="draftpilot-rag-"), "rag.sqlite3"))

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


async def _temporal_unavailable() -> None:
    """Fail fast like an absent Temporal server instead of retrying the connection."""
    raise ConnectionError("no Temporal server in Tier 0 tests")


@pytest.fixture(autouse=True)
def _no_temporal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make workflow starts fail immediately; tests that need them use ``started_workflows``."""
    monkeypatch.setattr("draftpilot.core.temporal.get_client", _temporal_unavailable)


@pytest.fixture
def started_workflows(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, tuple[object, ...]]]:
    """Record every workflow started (type name and arguments) instead of reaching Temporal."""
    started: list[tuple[str, tuple[object, ...]]] = []

    async def start_job(workflow: str, *args: object, id: str | None = None, **_options: object) -> str:
        """Record the start and return the workflow id."""
        started.append((workflow, args))
        return id or f"{workflow}-test"

    monkeypatch.setattr("draftpilot.core.temporal.start_job", start_job)
    return started
