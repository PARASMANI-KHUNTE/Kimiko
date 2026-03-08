"""Model router — routes requests to appropriate models based on intent and availability.

Tracks warm models, supports fallback, designed for pluggable backends (Fix #9).
"""

from __future__ import annotations

import structlog

from kimiko.config import get_settings
from kimiko.models.schemas import Intent
from kimiko.services.llm import get_llm_service

logger = structlog.get_logger(__name__)

# Default intent → model mapping
INTENT_MODEL_MAP: dict[Intent, str] = {
    Intent.CHAT: "qwen2.5",
    Intent.QUESTION: "qwen2.5",
    Intent.GREETING: "qwen2.5",
    Intent.CODE: "codellama",
    Intent.IMAGE_ANALYSIS: "qwen2.5",  # Vision model in Phase 3
    Intent.DOCUMENT_QUERY: "qwen2.5",
    Intent.AGENT_TASK: "qwen2.5",
    Intent.TOOL_REQUEST: "qwen2.5",
    Intent.SPEECH: "qwen2.5",
}


class ModelRouter:
    """Routes requests to the best available model based on intent and state."""

    def __init__(self) -> None:
        self._model_map = INTENT_MODEL_MAP.copy()

    async def route(
        self,
        intent: Intent,
        preferred_model: str | None = None,
    ) -> str:
        """Select the best model for a given intent.

        Priority:
        1. User-specified model (if available)
        2. Intent-mapped model (if available)
        3. Default fallback model
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

        # 2. Intent-based routing
        intent_model = self._model_map.get(intent, settings.default_model)

        # Prefer warm models to avoid loading latency
        if await llm.is_model_loaded(intent_model):
            logger.info("model_routed", model=intent_model, reason="intent_warm")
            return intent_model

        if await self._is_available(intent_model):
            logger.info("model_routed", model=intent_model, reason="intent_cold")
            return intent_model

        # 3. Fallback
        logger.warning(
            "model_fallback",
            intended=intent_model,
            fallback=settings.default_model,
        )
        return settings.default_model

    async def _is_available(self, model: str) -> bool:
        """Check if a model is available in the runtime."""
        try:
            llm = get_llm_service()
            models = await llm.list_models()
            model_names = [m.get("name", "").split(":")[0] for m in models]
            return model in model_names or any(model in name for name in model_names)
        except Exception:
            return False

    def update_mapping(self, intent: Intent, model: str) -> None:
        """Dynamically update the intent → model mapping."""
        self._model_map[intent] = model
        logger.info("model_mapping_updated", intent=intent.value, model=model)
