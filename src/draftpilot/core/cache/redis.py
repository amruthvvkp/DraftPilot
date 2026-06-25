"""Redis cache client and small JSON helpers.

A module-level lazy client is shared across the process. Values are stored as
JSON strings; ``cache_get``/``cache_set`` handle (de)serialization.
"""

import json
from typing import Any

import redis.asyncio as aioredis

from draftpilot.core.config import settings

_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    """Return the shared async Redis client, creating it on first use."""
    global _client
    if _client is None:
        _client = aioredis.from_url(settings.redis.url, decode_responses=True)
    return _client


async def cache_get(key: str) -> Any | None:
    """Fetch and JSON-decode a cached value, or ``None`` if absent."""
    raw = await get_redis().get(key)
    return json.loads(raw) if raw is not None else None


async def cache_set(key: str, value: Any, ttl: int | None = None) -> None:
    """JSON-encode and store a value, with an optional TTL in seconds."""
    await get_redis().set(key, json.dumps(value), ex=ttl)


async def close_redis() -> None:
    """Close the shared client on shutdown."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
