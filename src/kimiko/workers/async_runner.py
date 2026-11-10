"""Run coroutines from Celery's synchronous worker without per-task loop churn.

The previous workers called ``asyncio.new_event_loop()`` for every task. That
recreated the loop (and, with it, invalidated loop-bound HTTP/Redis clients)
on each invocation. A thread-local persistent loop lets the worker reuse the
same event loop and connection pools for the lifetime of the process.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")

_local = threading.local()


def _get_loop() -> asyncio.AbstractEventLoop:
    loop: asyncio.AbstractEventLoop | None = getattr(_local, "loop", None)
    if loop is None or loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        _local.loop = loop
    return loop


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """Run ``coro`` to completion on the worker thread's persistent loop."""
    return _get_loop().run_until_complete(coro)


def close_loop() -> None:
    """Close the thread-local loop (call on worker shutdown if desired)."""
    loop: asyncio.AbstractEventLoop | None = getattr(_local, "loop", None)
    if loop is not None and not loop.is_closed():
        loop.close()
    _local.loop = None
