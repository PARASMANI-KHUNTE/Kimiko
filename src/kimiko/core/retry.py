"""Retry utility — exponential backoff for transient failures (Phase 5).

Provides a decorator for retrying async operations with configurable
backoff, max retries, and exception filtering. Only safe for idempotent
operations (LLM calls, vector searches, reads).
"""

from __future__ import annotations

import asyncio
import functools
import random
from typing import Any, Callable, Sequence, Type

import structlog

logger = structlog.get_logger(__name__)

# Default retryable exceptions
DEFAULT_RETRYABLE = (
    ConnectionError,
    TimeoutError,
    OSError,
)


def with_retry(
    max_retries: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 5.0,
    retryable_exceptions: Sequence[Type[Exception]] = DEFAULT_RETRYABLE,
    jitter: bool = True,
) -> Callable:
    """Decorator that retries an async function with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts.
        base_delay: Initial delay in seconds.
        max_delay: Maximum delay cap in seconds.
        retryable_exceptions: Tuple of exception types safe to retry.
        jitter: Add random jitter to prevent thundering herd.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except tuple(retryable_exceptions) as e:
                    last_exception = e

                    if attempt == max_retries:
                        logger.error(
                            "retry_exhausted",
                            function=func.__name__,
                            attempts=attempt + 1,
                            error=str(e),
                        )
                        raise

                    # Exponential backoff: delay = base * 2^attempt
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    if jitter:
                        delay = delay * (0.5 + random.random())

                    logger.warning(
                        "retrying_operation",
                        function=func.__name__,
                        attempt=attempt + 1,
                        delay=round(delay, 2),
                        error=str(e),
                    )

                    await asyncio.sleep(delay)

            # Should not reach here, but safety net
            raise last_exception  # type: ignore

        return wrapper

    return decorator
