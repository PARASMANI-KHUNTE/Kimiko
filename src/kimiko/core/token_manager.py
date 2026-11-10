"""Token manager — model-specific budgeting and truncation (Fixes #2, review #2).

Handles token counting, budget allocation, and context truncation
to prevent exceeding model context limits.
"""

from __future__ import annotations

import structlog

from kimiko.models.schemas import Message

logger = structlog.get_logger(__name__)

# ── Model-specific token budgets ──
# These represent the maximum allocation per context section.
MODEL_BUDGETS: dict[str, dict[str, int]] = {
    "qwen3.5": {
        # Native context is 256K, but a 4B model on a 6 GB GPU stays fast and
        # accurate with a much smaller working window.
        "context_window": 32768,
        "system": 500,
        "history": 4000,
        "memories": 1500,
        "retrieval": 2000,
        "response": 4000,
    },
    "qwen2.5": {
        "context_window": 131072,
        "system": 500,
        "history": 4000,
        "memories": 1500,
        "retrieval": 2000,
        "response": 4000,
    },
    "llama3": {
        "context_window": 8192,
        "system": 400,
        "history": 1500,
        "memories": 500,
        "retrieval": 1000,
        "response": 2000,
    },
    "codellama": {
        "context_window": 16384,
        "system": 400,
        "history": 2000,
        "memories": 500,
        "retrieval": 2000,
        "response": 4000,
    },
    "mistral": {
        "context_window": 32768,
        "system": 500,
        "history": 3000,
        "memories": 1000,
        "retrieval": 2000,
        "response": 4000,
    },
    "qwen2-vl": {
        "context_window": 16384,
        "system": 400,  # Default from DEFAULT_BUDGET
        "history": 4000,
        "memories": 500,  # Default from DEFAULT_BUDGET
        "retrieval": 2000,
        "response": 2000, # Mapped from 'output'
    },
    "llava": {
        "context_window": 4096,
        "system": 400,  # Default from DEFAULT_BUDGET
        "history": 1000,
        "memories": 500,  # Default from DEFAULT_BUDGET
        "retrieval": 1000,
        "response": 1000, # Mapped from 'output'
    },
}

# Default budget for unknown models
DEFAULT_BUDGET: dict[str, int] = {
    "context_window": 8192,
    "system": 400,
    "history": 1500,
    "memories": 500,
    "retrieval": 1000,
    "response": 2000,
}


class TokenManager:
    """Manages token budgets, counting, and truncation for LLM context assembly.

    Uses a character-based approximation (1 token ≈ 4 chars) for Phase 1.
    Model-specific tokenizers can be added in tokenizers/ later (review Fix #2).
    """

    CHARS_PER_TOKEN = 4  # Conservative estimate
    IMAGE_TOKEN_ESTIMATE = 1000  # Vision models typically use ~1k tokens per image

    def __init__(self) -> None:
        self._budgets = MODEL_BUDGETS

    def count_tokens(self, text: str) -> int:
        """Estimate token count. Uses char-based approximation for Phase 1.

        TODO: Replace with model-specific tokenizers (tiktoken wrappers).
        """
        return len(text) // self.CHARS_PER_TOKEN + 1

    def count_messages_tokens(self, messages: list[Message]) -> int:
        """Count total tokens across a list of messages including images."""
        total = 0
        for msg in messages:
            # ~4 tokens overhead per message for role + formatting
            total += self.count_tokens(msg.content) + 4
            if msg.images:
                total += len(msg.images) * self.IMAGE_TOKEN_ESTIMATE
        return total

    def get_budget(self, model: str) -> dict[str, int]:
        """Get the token budget for a specific model."""
        # Exact base-name match first (e.g. "qwen3.5:4b" → "qwen3.5").
        base = model.split(":", 1)[0]
        budget = self._budgets.get(base)
        if budget is not None:
            return budget.copy()
        # Then fall back to prefix matching for unusual tags.
        for model_key, budget in self._budgets.items():
            if model.startswith(model_key):
                return budget.copy()
        logger.warning("token_budget_fallback", model=model)
        return DEFAULT_BUDGET.copy()

    def truncate_messages(
        self, messages: list[Message], max_tokens: int
    ) -> list[Message]:
        """Truncate message history to fit within token budget.

        Keeps the most recent messages, always preserving the last user message.
        """
        if not messages:
            return []

        # Always keep the last message
        kept_reversed = [messages[-1]]
        remaining = max_tokens - self.count_tokens(messages[-1].content) - 4

        # Walk backwards collecting the newest messages that fit. Appending and
        # reversing at the end is O(n); the old ``insert(0, ...)`` was O(n²).
        for msg in reversed(messages[:-1]):
            msg_tokens = self.count_tokens(msg.content) + 4
            if remaining - msg_tokens < 0:
                break
            kept_reversed.append(msg)
            remaining -= msg_tokens

        result = kept_reversed[::-1]

        if len(result) < len(messages):
            logger.info(
                "messages_truncated",
                original=len(messages),
                kept=len(result),
                max_tokens=max_tokens,
            )

        return result

    def truncate_text(self, text: str, max_tokens: int) -> str:
        """Truncate text to fit within token budget."""
        max_chars = max_tokens * self.CHARS_PER_TOKEN
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "..."

    def allocate_budget(
        self,
        model: str,
        knowledge_tokens: int = 0,
        image_count: int = 0
    ) -> dict[str, int]:
        """Get the full budget allocation for a model, ensuring total fits window.
        
        Implements Dynamic Budgeting:
        - History budget scales inversely with Image tokens (ratio-based sizing).
        """
        budget = self.get_budget(model)
        window = budget.pop("context_window")

        # Account for images if any
        image_tokens = image_count * self.IMAGE_TOKEN_ESTIMATE

        # Dynamic Scaling: Shrink history budget based on image token ratio
        if image_tokens > 0:
            base_history = budget.get("history", 1500)
            # Prevent negative ratio if images exceed context window (clamped)
            ratio = max(0.1, 1.0 - (image_tokens / window))
            budget["history"] = int(base_history * ratio)

            # Reduce retrieval slightly as well if image load is massive
            if image_tokens > (window * 0.3):
                base_retrieval = budget.get("retrieval", 1000)
                budget["retrieval"] = int(base_retrieval * ratio)

        # Ensure allocations don't exceed remaining window
        total_allocated = sum(budget.values()) + image_tokens
        if total_allocated > window:
            # Scale down non-system components if we are still overflowing
            reserved = budget.get("system", 400) + image_tokens
            if reserved < window:
                scale = (window - reserved) / max(1, total_allocated - reserved)
                for k in budget:
                    if k != "system":
                        budget[k] = max(100, int(budget[k] * scale))
            else:
                # If images alone exceed window, we have bigger problems, just slash everything
                for k in budget:
                    if k != "system":
                        budget[k] = 100

            logger.warning(
                "budget_scaled_down",
                model=model,
                window=window,
                image_tokens=image_tokens,
                original_total=total_allocated,
            )

        return budget

    def rank_and_trim(
        self, items: list[dict], max_tokens: int, text_key: str = "text"
    ) -> list[dict]:
        """Rank items by score and trim to fit token budget.

        Items should have a 'score' and text_key field.
        """
        # Sort by score descending
        sorted_items = sorted(items, key=lambda x: x.get("score", 0), reverse=True)

        result = []
        remaining = max_tokens

        for item in sorted_items:
            text = item.get(text_key, "")
            tokens = self.count_tokens(text)
            if remaining - tokens < 0:
                break
            result.append(item)
            remaining -= tokens

        return result
