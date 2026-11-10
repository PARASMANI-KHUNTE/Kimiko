"""Small in-process caching primitives used on hot paths.

These are intentionally dependency-free and asyncio-friendly:

- :class:`TTLCache` — bounded LRU map with per-entry expiry (O(1) get/set).
- :class:`AsyncSingleFlight` — coalesces concurrent identical async calls so a
  cache miss under load triggers one upstream request instead of N.

The caches live in the API/worker process. They are not shared between
processes, which is the right trade-off for hot, cheap-to-recompute values such
as embeddings and the Ollama model list.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Hashable
from typing import Any, TypeVar

T = TypeVar("T")


class TTLCache:
    """A bounded LRU cache where every entry also expires after ``ttl`` seconds.

    ``get`` returns ``None`` for a miss or an expired entry. Store only
    non-``None`` values (all current call sites do).
    """

    __slots__ = ("_data", "_maxsize", "_ttl")

    def __init__(self, maxsize: int = 512, ttl: float = 300.0) -> None:
        if maxsize < 1:
            raise ValueError("maxsize must be >= 1")
        if ttl <= 0:
            raise ValueError("ttl must be > 0")
        self._data: OrderedDict[Hashable, tuple[float, Any]] = OrderedDict()
        self._maxsize = maxsize
        self._ttl = ttl

    def get(self, key: Hashable) -> Any | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at < time.monotonic():
            del self._data[key]
            return None
        # Mark as recently used for LRU eviction.
        self._data.move_to_end(key)
        return value

    def set(self, key: Hashable, value: Any) -> None:
        self._data[key] = (time.monotonic() + self._ttl, value)
        self._data.move_to_end(key)
        while len(self._data) > self._maxsize:
            self._data.popitem(last=False)

    def clear(self) -> None:
        self._data.clear()

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, key: Hashable) -> bool:
        return self.get(key) is not None


class AsyncSingleFlight:
    """Coalesce concurrent calls sharing the same key.

    The first caller runs ``factory``; everyone else awaits the same task. The
    in-flight entry is removed as soon as the task finishes, so later calls run
    again (usually hitting a warm cache).
    """

    __slots__ = ("_inflight",)

    def __init__(self) -> None:
        self._inflight: dict[Hashable, asyncio.Task[Any]] = {}

    async def run(
        self, key: Hashable, factory: Callable[[], Awaitable[T]]
    ) -> T:
        task = self._inflight.get(key)
        if task is None:
            task = asyncio.ensure_future(factory())
            self._inflight[key] = task
            task.add_done_callback(lambda _t, _k=key: self._inflight.pop(_k, None))
        # Shield the shared task so one cancelled waiter does not cancel it for
        # the others.
        return await asyncio.shield(task)
