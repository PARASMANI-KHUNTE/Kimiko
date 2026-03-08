"""Pluggable LLM service — abstract base + Ollama implementation.

Designed to be swappable (Fix #9): add VLLMService later without changing callers.
Uses tenacity for circuit breaker / retry (Fix #5 from review round 2).
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

import httpx
import structlog
from typing import Union
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from kimiko.config import get_settings

logger = structlog.get_logger(__name__)


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
        prompt: Union[str, dict[str, Any]],
        *,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Generate a complete response."""
        ...

    @abstractmethod
    async def stream(
        self,
        model: str,
        prompt: Union[str, dict[str, Any]],
        *,
        system: str | None = None,
        temperature: float = 0.7,
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
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Generate a complete (non-streaming) response from Ollama."""
        # Handle multimodal prompt
        actual_prompt = prompt
        images = None
        if isinstance(prompt, dict):
            actual_prompt = prompt.get("prompt", "")
            images = prompt.get("images")

        payload: dict[str, Any] = {
            "model": model,
            "prompt": actual_prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if images:
            payload["images"] = images
        if system:
            payload["system"] = system
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

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
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Stream tokens from Ollama. Yields individual token strings."""
        # Handle multimodal prompt
        actual_prompt = prompt
        images = None
        if isinstance(prompt, dict):
            actual_prompt = prompt.get("prompt", "")
            images = prompt.get("images")

        payload: dict[str, Any] = {
            "model": model,
            "prompt": actual_prompt,
            "stream": True,
            "options": {"temperature": temperature},
        }
        if images:
            payload["images"] = images
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

    @retry(
        retry=retry_if_exception_type(httpx.ConnectError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        reraise=True,
    )
    async def list_models(self) -> list[dict[str, Any]]:
        """List all models available in Ollama."""
        resp = await self._client.get("/api/tags")
        resp.raise_for_status()
        return resp.json().get("models", [])

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
    """Initialize the LLM service singleton."""
    global _llm_service
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
