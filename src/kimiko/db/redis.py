"""Redis connection pool and dependency."""

from __future__ import annotations

import redis.asyncio as aioredis

from kimiko.config import get_settings

_redis_pool: aioredis.Redis | None = None


async def init_redis() -> aioredis.Redis:
    """Initialize the Redis connection pool (idempotent)."""
    global _redis_pool
    if _redis_pool is not None:
        return _redis_pool
    settings = get_settings()
    _redis_pool = aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
        max_connections=20,
    )
    # Verify connection
    await _redis_pool.ping()
    return _redis_pool


async def close_redis() -> None:
    """Close the Redis connection pool."""
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.aclose()
        _redis_pool = None


def get_redis() -> aioredis.Redis:
    """Get the Redis client instance."""
    if _redis_pool is None:
        raise RuntimeError("Redis not initialized. Call init_redis() first.")
    return _redis_pool
