"""Embedding service — fixed model: nomic-embed-text via Ollama.

Single model policy (Fix #4): all embeddings use the same model to ensure
vector consistency across the system.

Performance notes
-----------------
Embeddings are deterministic for a given model + text, so the service keeps a
small bounded LRU+TTL cache. Concurrent requests for the same text are
coalesced into a single upstream call (single-flight). ``embed_batch`` sends the
whole batch to Ollama in one HTTP request instead of looping one call per text.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from kimiko.config import get_settings
from kimiko.core.cache import AsyncSingleFlight, TTLCache

logger = structlog.get_logger(__name__)


class EmbeddingService:
    """Generates embeddings via Ollama using nomic-embed-text."""

    def __init__(self, base_url: str | None = None) -> None:
        settings = get_settings()
        self._base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self._model = settings.embedding_model
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(60.0, connect=10.0),
        )
        self._cache = TTLCache(
            maxsize=settings.embedding_cache_size,
            ttl=settings.embedding_cache_ttl,
        )
        self._flight: AsyncSingleFlight = AsyncSingleFlight()

    async def close(self) -> None:
        await self._client.aclose()

    # ── Public API ──

    async def embed(self, text: str) -> list[float]:
        """Generate an embedding vector for a single text (cached)."""
        cached = self._cache.get(text)
        if cached is not None:
            return cached
        return await self._flight.run(text, lambda: self._embed_uncached(text))

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts in one upstream request.

        Cached texts are served from memory; only the misses are sent to Ollama.
        The returned list preserves the input order.
        """
        if not texts:
            return []

        # Deduplicate while preserving order: {text: vector}
        unique: dict[str, list[float]] = {}
        missing: list[str] = []
        seen: set[str] = set()
        for text in texts:
            if text in seen:
                continue
            seen.add(text)
            cached = self._cache.get(text)
            if cached is not None:
                unique[text] = cached
            else:
                missing.append(text)

        if missing:
            vectors = await self._request(missing)
            for text, vector in zip(missing, vectors):
                self._cache.set(text, vector)
                unique[text] = vector

        return [unique[text] for text in texts]

    # ── Internal ──

    async def _embed_uncached(self, text: str) -> list[float]:
        vectors = await self._request([text])
        vector = vectors[0]
        self._cache.set(text, vector)
        return vector

    @retry(
        retry=retry_if_exception_type((httpx.ConnectError, httpx.ReadTimeout)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _request(self, inputs: list[str]) -> list[list[float]]:
        """POST one or many inputs to Ollama's ``/api/embed`` endpoint."""
        # Ollama accepts a string or an array for ``input``.
        payload: dict[str, Any] = {
            "model": self._model,
            "input": inputs[0] if len(inputs) == 1 else inputs,
        }
        resp = await self._client.post("/api/embed", json=payload)
        resp.raise_for_status()
        data = resp.json()

        embeddings = data.get("embeddings") or []
        if len(embeddings) != len(inputs):
            raise ValueError(
                f"Expected {len(inputs)} embeddings from Ollama, got {len(embeddings)}"
            )

        logger.debug(
            "embeddings_generated",
            model=self._model,
            count=len(embeddings),
            dimensions=len(embeddings[0]) if embeddings else 0,
        )
        return embeddings

    def clear_cache(self) -> None:
        """Drop all cached embeddings (useful after a model change)."""
        self._cache.clear()

    @property
    def model_name(self) -> str:
        return self._model


# ── Singleton ──

_embedding_service: EmbeddingService | None = None


def init_embedding_service(base_url: str | None = None) -> EmbeddingService:
    """Initialize the embedding service singleton (idempotent)."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService(base_url=base_url)
    return _embedding_service


async def close_embedding_service() -> None:
    global _embedding_service
    if _embedding_service is not None:
        await _embedding_service.close()
        _embedding_service = None


def get_embedding_service() -> EmbeddingService:
    if _embedding_service is None:
        raise RuntimeError("Embedding service not initialized.")
    return _embedding_service
