"""Pluggable LLM service — abstract base + Ollama implementation.

Designed to be swappable (Fix #9): add VLLMService later without changing callers.
Uses tenacity for circuit breaker / retry (Fix #5 from review round 2).
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from functools import lru_cache
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

_VISION_KEYWORDS = frozenset(
    {"llava", "vision", "minicpm", "moondream", "bakllava", "multimodal", "v-", "vl", "qwen2-", "qwen2.5"}
)


@lru_cache(maxsize=256)
def _is_vision_model_name(model: str) -> bool:
    """Heuristic to check if a model supports vision (memoized)."""
    lowered = model.lower()
    return any(k in lowered for k in _VISION_KEYWORDS)



class LLMServiceError(Exception):
    """Base error for LLM service failures."""

    pass


class ModelNotAvailableError(LLMServiceError):
    """Model is not loaded or does not exist."""

    pass


class BaseLLMService(ABC):
    """Abstract base for LLM backends — swap Ollama for vLLM later."""

    @abstractmethod
    async def generate(
        self,
        model: str,
        prompt: str,
        *,
        system: str | None = None,
        images: list[str] | None = None,
        temperature: float = 0.3,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
    ) -> dict[str, Any]:
        """Generate a complete response."""
        ...

    @abstractmethod
    async def stream(
        self,
        model: str,
        prompt: str,
        *,
        system: str | None = None,
        images: list[str] | None = None,
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Stream tokens one by one."""
        ...

    @abstractmethod
    async def list_models(self) -> list[dict[str, Any]]:
        """List available models."""
        ...

    @abstractmethod
    async def model_info(self, model: str) -> dict[str, Any]:
        """Get information about a specific model."""
        ...

    @abstractmethod
    async def is_model_loaded(self, model: str) -> bool:
        """Check if a model is currently loaded / warm."""
        ...


class OllamaService(BaseLLMService):
    """Ollama HTTP API client with circuit breaker and retry logic."""

    def __init__(self, base_url: str | None = None, timeout: float = 120.0) -> None:
        settings = get_settings()
        self._base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self._timeout = timeout
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout, connect=10.0),
        )
        # Track warm models
        self._warm_models: set[str] = set()
        # Cache the (network-backed) model list for a short TTL. Concurrent
        # refreshes are serialized so we never stampede Ollama.
        self._models_ttl = get_settings().model_list_cache_ttl
        self._models_cache: list[dict[str, Any]] | None = None
        self._models_names: frozenset[str] = frozenset()
        self._models_cached_at = 0.0
        self._models_lock = asyncio.Lock()

    def _is_vision_model(self, model: str) -> bool:
        """Heuristic to check if a model supports vision."""
        return _is_vision_model_name(model)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    # ── Generate ──

    @retry(
        retry=retry_if_exception_type((httpx.ConnectError, httpx.ReadTimeout)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def generate(
        self,
        model: str,
        prompt: str,
        *,
        system: str | None = None,
        images: list[str] | None = None,
        temperature: float = 0.3,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
    ) -> dict[str, Any]:
        """Generate a complete (non-streaming) response from Ollama."""
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if images and self._is_vision_model(model):
            payload["images"] = images
        elif images:
            logger.warning("omitting_images_for_non_vision_model", model=model)
        if system:
            payload["system"] = system
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens
        if stop:
            payload["options"]["stop"] = stop

        try:
            resp = await self._client.post("/api/generate", json=payload)
            resp.raise_for_status()
            self._warm_models.add(model)
            data = resp.json()
            logger.info(
                "llm_generate_complete",
                model=model,
                eval_count=data.get("eval_count"),
                total_duration=data.get("total_duration"),
            )
            return data
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ModelNotAvailableError(f"Model '{model}' not found") from e
            raise LLMServiceError(f"Ollama error: {e.response.status_code}") from e

    # ── Stream ──

    async def stream(
        self,
        model: str,
        prompt: str,
        *,
        system: str | None = None,
        images: list[str] | None = None,
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Stream tokens from Ollama. Yields individual token strings."""
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": True,
            "options": {"temperature": temperature},
        }
        if images and self._is_vision_model(model):
            payload["images"] = images
        elif images:
            logger.warning("omitting_images_for_non_vision_model", model=model)
        if system:
            payload["system"] = system
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        try:
            async with self._client.stream(
                "POST", "/api/generate", json=payload, timeout=self._timeout
            ) as resp:
                resp.raise_for_status()
                self._warm_models.add(model)
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    import json
                    chunk = json.loads(line)
                    if chunk.get("done"):
                        return
                    token = chunk.get("response", "")
                    if token:
                        yield token
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise ModelNotAvailableError(f"Model '{model}' not found") from e
            raise LLMServiceError(f"Ollama streaming error: {e.response.status_code}") from e

    # ── Model Management ──

    async def list_models(self, *, force: bool = False) -> list[dict[str, Any]]:
        """List all models available in Ollama.

        Results are cached for ``model_list_cache_ttl`` seconds and concurrent
        refreshes are coalesced behind a lock. This method sits on the routing
        hot path, so avoiding a network round-trip per chat request matters.
        """
        now = time.monotonic()
        if (
            not force
            and self._models_cache is not None
            and (now - self._models_cached_at) < self._models_ttl
        ):
            return self._models_cache

        async with self._models_lock:
            # Another coroutine may have refreshed while we waited.
            now = time.monotonic()
            if (
                not force
                and self._models_cache is not None
                and (now - self._models_cached_at) < self._models_ttl
            ):
                return self._models_cache

            models = await self._fetch_models()
            names: set[str] = set()
            for model in models:
                name = str(model.get("name", ""))
                if not name:
                    continue
                names.add(name)
                # Ollama reports "qwen2.5:7b"; callers usually ask for "qwen2.5".
                names.add(name.split(":", 1)[0])
            self._models_cache = models
            self._models_names = frozenset(names)
            self._models_cached_at = time.monotonic()
            return models

    @retry(
        retry=retry_if_exception_type(httpx.ConnectError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        reraise=True,
    )
    async def _fetch_models(self) -> list[dict[str, Any]]:
        resp = await self._client.get("/api/tags")
        resp.raise_for_status()
        return resp.json().get("models", [])

    async def is_available(self, model: str) -> bool:
        """Return True if ``model`` (or a tagged variant) exists in Ollama.

        Uses the cached model list, so the common case is an O(1) set lookup.
        """
        if not model:
            return False
        try:
            await self.list_models()
        except Exception:
            return False
        if model in self._models_names:
            return True
        # Allow callers to pass a bare name when only "name:tag" exists.
        base = model.split(":", 1)[0]
        return base in self._models_names

    def invalidate_model_cache(self) -> None:
        """Force the next ``list_models`` call to refresh."""
        self._models_cache = None
        self._models_cached_at = 0.0

    async def model_info(self, model: str) -> dict[str, Any]:
        """Get detailed info about a model."""
        resp = await self._client.post("/api/show", json={"name": model})
        if resp.status_code == 404:
            raise ModelNotAvailableError(f"Model '{model}' not found")
        resp.raise_for_status()
        return resp.json()

    async def is_model_loaded(self, model: str) -> bool:
        """Check if a model is currently warm (recently used)."""
        return model in self._warm_models

    async def health_check(self) -> bool:
        """Check if Ollama is reachable."""
        try:
            resp = await self._client.get("/")
            return resp.status_code == 200
        except (httpx.ConnectError, httpx.ReadTimeout):
            return False


# ── Singleton ──

_llm_service: OllamaService | None = None


def init_llm_service(base_url: str | None = None) -> OllamaService:
    """Initialize the LLM service singleton (idempotent)."""
    global _llm_service
    if _llm_service is None:
        _llm_service = OllamaService(base_url=base_url)
    return _llm_service


async def close_llm_service() -> None:
    """Close the LLM service."""
    global _llm_service
    if _llm_service is not None:
        await _llm_service.close()
        _llm_service = None


def get_llm_service() -> OllamaService:
    """Get the LLM service instance."""
    if _llm_service is None:
        raise RuntimeError("LLM service not initialized. Call init_llm_service() first.")
    return _llm_service
