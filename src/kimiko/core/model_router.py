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
    Intent.CODE: "deepseek-r1:7b",
    Intent.IMAGE_ANALYSIS: "qwen2-vl",
    Intent.DOCUMENT_QUERY: "qwen2.5",
    Intent.AGENT_TASK: "qwen2.5",
    Intent.TOOL_REQUEST: "qwen2.5",
    Intent.SPEECH: "qwen2.5",
}

# All models available for user selection (must be pulled in Ollama)
AVAILABLE_MODELS = [
    {"id": "qwen2.5",         "name": "Qwen 2.5",        "type": "chat"},
    {"id": "deepseek-r1:7b",  "name": "DeepSeek R1 7B",  "type": "reasoning"},
    {"id": "codellama",       "name": "CodeLlama",        "type": "code"},
    {"id": "llama3.2",        "name": "Llama 3.2",        "type": "chat"},
    {"id": "qwen2-vl",        "name": "Qwen 2 VL",        "type": "vision"},
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

        # Prefer warm models to avoid loading latency
        if await llm.is_model_loaded(intent_model):
            logger.info("model_routed", model=intent_model, reason="intent_warm")
            return intent_model

        if await self._is_available(intent_model):
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

    def set_remote_model(self, model: str) -> None:
        """Configure the remote model for smart overflow routing."""
        self._remote_model = model
        logger.info("remote_model_configured", model=model)
