"""Search the RAG service over HTTP, or an in-process index when one is bound (evals, offline tools)."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import httpx

from draftpilot.core.config import settings
from draftpilot.core.rag import HybridIndex

_local_index: HybridIndex | None = None


@contextmanager
def local_index(index: HybridIndex) -> Iterator[None]:
    """Answer every search from ``index`` instead of the RAG service while the context is open."""
    global _local_index
    previous = _local_index
    _local_index = index
    try:
        yield
    finally:
        _local_index = previous


async def search(project_id: int, query: str, limit: int, *, timeout: float) -> dict[str, Any]:
    """Return ``{"results": [...]}`` of citation-bearing chunks for one project."""
    if _local_index is not None:
        results = await _local_index.search(project_id, query, limit)
        return {"results": [result.model_dump(mode="json") for result in results]}
    url = f"{settings.rag.service_url.rstrip('/')}/projects/{project_id}/search"
    headers = {"Authorization": f"Bearer {settings.rag.auth_token.get_secret_value()}"}
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, json={"query": query, "limit": limit}, headers=headers)
        response.raise_for_status()
        if len(response.content) > settings.mcp.max_output_chars:
            raise ValueError("RAG response exceeds MCP output limit")
        payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("RAG response is invalid")
    return payload
