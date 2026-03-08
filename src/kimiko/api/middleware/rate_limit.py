"""Rate limiter middleware — Redis sliding window (Fix #7 review round 2)."""

from __future__ import annotations

import time

from fastapi import HTTPException, Request, status
import structlog

from kimiko.config import get_settings
from kimiko.db.redis import get_redis

logger = structlog.get_logger(__name__)


async def rate_limit_middleware(request: Request) -> None:
    """Sliding window rate limiter using Redis.

    Called as a dependency on rate-limited endpoints.
    """
    settings = get_settings()

    # Identify client by IP or API key
    client_id = request.client.host if request.client else "unknown"

    try:
        redis = get_redis()
        key = f"ratelimit:{client_id}"
        now = time.time()
        window = 60  # 1 minute window

        # Remove entries outside the window
        await redis.zremrangebyscore(key, 0, now - window)

        # Count requests in window
        count = await redis.zcard(key)

        if count >= settings.rate_limit_rpm:
            logger.warning("rate_limit_exceeded", client_id=client_id, count=count)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Max {settings.rate_limit_rpm} requests per minute.",
                headers={"Retry-After": "60"},
            )

        # Add current request
        await redis.zadd(key, {str(now): now})
        await redis.expire(key, window + 1)

    except HTTPException:
        raise
    except Exception as e:
        # If Redis is down, allow the request (fail-open)
        logger.warning("rate_limit_redis_error", error=str(e))
