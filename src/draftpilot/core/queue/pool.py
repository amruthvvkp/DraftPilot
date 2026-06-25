"""ARQ Redis pool for enqueuing background jobs from the web process.

The web process uses ``get_arq_pool`` to enqueue jobs; the worker process
(``draftpilot.worker``) consumes them. Both share the ``RedisSettings`` derived
``redis_settings`` so they target the same Redis/queue.
"""

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings as ArqRedisSettings

from draftpilot.core.config import settings


def redis_settings() -> ArqRedisSettings:
    """Build ARQ ``RedisSettings`` from the app's queue configuration."""
    return ArqRedisSettings(
        host=settings.queue.host,
        port=settings.queue.port,
        database=settings.queue.db,
    )


_pool: ArqRedis | None = None


async def get_arq_pool() -> ArqRedis:
    """Return the shared ARQ pool, creating it on first use."""
    global _pool
    if _pool is None:
        _pool = await create_pool(redis_settings())
    return _pool


async def close_arq_pool() -> None:
    """Close the shared ARQ pool on shutdown."""
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None
