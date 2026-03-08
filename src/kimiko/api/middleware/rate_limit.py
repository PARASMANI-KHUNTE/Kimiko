"""Rate limiter — multi-dimension Redis sliding window (Phase 5).

Supports:
- max_requests_per_minute (RPM)
- max_agent_steps_per_hour
- max_tokens_per_request
"""

from __future__ import annotations

import time

from fastapi import HTTPException, Request, status
import structlog

from kimiko.config import get_settings
from kimiko.db.redis import get_redis

logger = structlog.get_logger(__name__)


class RateLimitManager:
    """Multi-dimension rate limiter backed by Redis sorted sets.

    Architecture:
        RateLimitManager
         ├─ request limiter  (per-minute)
         ├─ agent step limiter (per-hour)
         └─ token limiter    (per-request, config-based)
    """

    @staticmethod
    async def check_request_rate(client_id: str) -> None:
        """Enforce per-minute request rate limit."""
        settings = get_settings()
        await RateLimitManager._sliding_window_check(
            key=f"ratelimit:rpm:{client_id}",
            limit=settings.rate_limit_rpm,
            window=60,
            label="requests per minute",
        )

    @staticmethod
    async def check_agent_steps(client_id: str) -> None:
        """Enforce per-hour agent step limit."""
        settings = get_settings()
        await RateLimitManager._sliding_window_check(
            key=f"ratelimit:agent_steps:{client_id}",
            limit=settings.rate_limit_agent_steps_per_hour,
            window=3600,
            label="agent steps per hour",
        )

    @staticmethod
    async def record_agent_step(client_id: str) -> None:
        """Record one agent step for the user."""
        try:
            redis = get_redis()
            now = time.time()
            key = f"ratelimit:agent_steps:{client_id}"
            await redis.zadd(key, {str(now): now})
            await redis.expire(key, 3601)
        except Exception as e:
            logger.warning("rate_limit_record_error", error=str(e))

    @staticmethod
    def check_token_limit(token_count: int) -> None:
        """Enforce per-request token limit (synchronous, no Redis needed)."""
        settings = get_settings()
        if token_count > settings.rate_limit_max_tokens_per_request:
            logger.warning(
                "token_limit_exceeded",
                tokens=token_count,
                limit=settings.rate_limit_max_tokens_per_request,
            )
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Token limit exceeded. Max {settings.rate_limit_max_tokens_per_request} tokens per request.",
            )

    @staticmethod
    async def _sliding_window_check(
        key: str, limit: int, window: int, label: str
    ) -> None:
        """Generic Redis sliding window limiter."""
        try:
            redis = get_redis()
            now = time.time()

            await redis.zremrangebyscore(key, 0, now - window)
            count = await redis.zcard(key)

            if count >= limit:
                logger.warning("rate_limit_exceeded", key=key, count=count)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded. Max {limit} {label}.",
                    headers={"Retry-After": str(window)},
                )

            await redis.zadd(key, {str(now): now})
            await redis.expire(key, window + 1)

        except HTTPException:
            raise
        except Exception as e:
            # Fail-open if Redis goes down
            logger.warning("rate_limit_redis_error", error=str(e))


async def rate_limit_middleware(request: Request) -> None:
    """FastAPI dependency: enforces per-minute request rate limit."""
    client_id = request.client.host if request.client else "unknown"
    await RateLimitManager.check_request_rate(client_id)

