"""Model router — routes requests to appropriate models based on intent and availability.

Tracks warm models, supports fallback, designed for pluggable backends (Fix #9).
"""

from __future__ import annotations

import structlog

from kimiko.config import get_settings
from kimiko.models.schemas import Intent
from kimiko.services.llm import get_llm_service

logger = structlog.get_logger(__name__)

# Primary local model. Qwen 3.5 4B is natively multimodal (text + images),
# supports tool calls and optional thinking, and needs only ~3.3 GB on disk —
# it fits a 6 GB laptop GPU with room left for the KV cache.
#
# One model serves every intent on purpose: Ollama keeps a single model
# resident, so routing between models evicts the warm one and pays a cold-start
# penalty on each switch. A single resident model keeps latency predictable.
PRIMARY_MODEL = "qwen3.5:4b"

# Default intent → model mapping
INTENT_MODEL_MAP: dict[Intent, str] = {
    Intent.CHAT: PRIMARY_MODEL,
    Intent.QUESTION: PRIMARY_MODEL,
    Intent.GREETING: PRIMARY_MODEL,
    Intent.CODE: PRIMARY_MODEL,
    Intent.IMAGE_ANALYSIS: PRIMARY_MODEL,
    Intent.DOCUMENT_QUERY: PRIMARY_MODEL,
    Intent.AGENT_TASK: PRIMARY_MODEL,
    Intent.TOOL_REQUEST: PRIMARY_MODEL,
    Intent.SPEECH: PRIMARY_MODEL,
}

# Curated models offered in the UI. Entries may not be pulled yet; the catalog
# endpoint reports an ``available`` flag per model and the router falls back to
# ``settings.default_model`` when one is missing.
AVAILABLE_MODELS = [
    {"id": "qwen3.5:4b",          "name": "Qwen 3.5 4B",        "type": "chat"},
    {"id": "qwen3.5:9b",          "name": "Qwen 3.5 9B",        "type": "reasoning"},
    {"id": "qwen2.5-coder:3b",    "name": "Qwen 2.5 Coder 3B",  "type": "code"},
    {"id": "mimo-v2.6:9b",        "name": "MiMo v2.6 9B",       "type": "code"},
    {"id": "llama3.2",            "name": "Llama 3.2",          "type": "chat"},
    {"id": "embeddinggemma-2:270m", "name": "EmbeddingGemma 2", "type": "embedding"},
    {"id": "nomic-embed-text",    "name": "Nomic Embed Text",   "type": "embedding"},
]

# Intents that MUST stay local for privacy (memory, identity, personal data)
PRIVACY_LOCAL_INTENTS: set[Intent] = {
    Intent.CHAT,      # Personal conversations
    Intent.GREETING,  # Identity context
}

# Token threshold: if estimated tokens exceed this, consider routing to remote
LOCAL_TOKEN_LIMIT = 6000


class ModelRouter:
    """Routes requests to the best available model based on intent, privacy, and token budget.
    
    Phase 4 Smart Routing:
    - Privacy-sensitive tasks (personal memory) are always routed locally.
    - Token-heavy tasks can overflow to a configured remote provider.
    - Warm models are preferred to avoid cold-start latency.
    """

    def __init__(self, remote_model: str | None = None) -> None:
        self._model_map = INTENT_MODEL_MAP.copy()
        self._remote_model = remote_model  # e.g., "gpt-4o" or "claude-3.5-sonnet"

    async def route(
        self,
        intent: Intent,
        preferred_model: str | None = None,
        estimated_tokens: int = 0,
    ) -> str:
        """Select the best model for a given intent.

        Priority:
        1. User-specified model (if available)
        2. Smart routing: token budget + privacy check
        3. Intent-mapped model (if available)
        4. Default fallback model
        """
        settings = get_settings()
        llm = get_llm_service()

        # 1. User preference
        if preferred_model:
            if await self._is_available(preferred_model):
                logger.info("model_routed", model=preferred_model, reason="user_preference")
                return preferred_model
            logger.warning(
                "preferred_model_unavailable",
                model=preferred_model,
                fallback=settings.default_model,
            )

        # 2. Smart Routing (Phase 4)
        #    If tokens exceed local limits AND the task is not privacy-sensitive,
        #    route to a remote provider if configured.
        if (
            self._remote_model
            and estimated_tokens > LOCAL_TOKEN_LIMIT
            and intent not in PRIVACY_LOCAL_INTENTS
        ):
            logger.info(
                "smart_route_remote",
                model=self._remote_model,
                reason="token_overflow",
                estimated_tokens=estimated_tokens,
                limit=LOCAL_TOKEN_LIMIT,
            )
            return self._remote_model

        # 3. Intent-based routing
        intent_model = self._model_map.get(intent, settings.default_model)

        # Prefer warm models to avoid loading latency (in-process set lookup).
        if await llm.is_model_loaded(intent_model):
            logger.info("model_routed", model=intent_model, reason="intent_warm")
            return intent_model

        # Cached model-list lookup — no per-request /api/tags round-trip.
        if await llm.is_available(intent_model):
            logger.info("model_routed", model=intent_model, reason="intent_cold")
            return intent_model

        # 4. Fallback
        logger.warning(
            "model_fallback",
            intended=intent_model,
            fallback=settings.default_model,
        )
        return settings.default_model

    async def _is_available(self, model: str) -> bool:
        """Check if a model is available in the runtime (cached)."""
        try:
            llm = get_llm_service()
            return await llm.is_available(model)
        except Exception:
            return False

    def update_mapping(self, intent: Intent, model: str) -> None:
        """Dynamically update the intent → model mapping."""
        self._model_map[intent] = model
        logger.info("model_mapping_updated", intent=intent.value, model=model)

    def set_remote_model(self, model: str) -> None:
        """Configure the remote model for smart overflow routing."""
        self._remote_model = model
        logger.info("remote_model_configured", model=model)
