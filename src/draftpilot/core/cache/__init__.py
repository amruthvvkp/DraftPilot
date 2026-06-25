"""Redis caching layer."""

from draftpilot.core.cache.redis import cache_get, cache_set, close_redis, get_redis

__all__ = ["cache_get", "cache_set", "close_redis", "get_redis"]
