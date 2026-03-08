"""Embedding service — fixed model: nomic-embed-text via Ollama.

Single model policy (Fix #4): all embeddings use the same model
to ensure vector consistency across the system.
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

    async def close(self) -> None:
        await self._client.aclose()

    @retry(
        retry=retry_if_exception_type((httpx.ConnectError, httpx.ReadTimeout)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def embed(self, text: str) -> list[float]:
        """Generate embedding vector for a single text."""
        resp = await self._client.post(
            "/api/embed",
            json={"model": self._model, "input": text},
        )
        resp.raise_for_status()
        data = resp.json()

        embeddings = data.get("embeddings", [])
        if not embeddings:
            raise ValueError("No embeddings returned from Ollama")

        vector = embeddings[0]
        logger.debug("embedding_generated", model=self._model, dimensions=len(vector))
        return vector

    @retry(
        retry=retry_if_exception_type((httpx.ConnectError, httpx.ReadTimeout)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        results = []
        for text in texts:
            vector = await self.embed(text)
            results.append(vector)
        return results

    @property
    def model_name(self) -> str:
        return self._model


# ── Singleton ──

_embedding_service: EmbeddingService | None = None


def init_embedding_service(base_url: str | None = None) -> EmbeddingService:
    global _embedding_service
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
