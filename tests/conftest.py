"""Shared pytest configuration: tier markers and the local LM Studio fixture."""

from pathlib import Path

import httpx
import pytest
from _lmstudio import LMStudio, discover_lmstudio

from draftpilot.core.config import settings

E2E_DIR = Path(__file__).parent / "e2e"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Mark every browser journey under ``tests/e2e`` with the ``e2e`` marker."""
    for item in items:
        if E2E_DIR in Path(str(item.fspath)).parents:
            item.add_marker(pytest.mark.e2e)


@pytest.fixture(scope="session")
def lmstudio() -> LMStudio:
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
    return server
