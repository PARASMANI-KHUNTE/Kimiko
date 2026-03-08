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

    def __init__(self) -> None:
        self._budgets = MODEL_BUDGETS

    def count_tokens(self, text: str) -> int:
        """Estimate token count. Uses char-based approximation for Phase 1.

        TODO: Replace with model-specific tokenizers (tiktoken wrappers).
        """
        return len(text) // self.CHARS_PER_TOKEN + 1

    def count_messages_tokens(self, messages: list[Message]) -> int:
        """Count total tokens across a list of messages."""
        total = 0
        for msg in messages:
            # ~4 tokens overhead per message for role + formatting
            total += self.count_tokens(msg.content) + 4
        return total

    def get_budget(self, model: str) -> dict[str, int]:
        """Get the token budget for a specific model."""
        # Match by prefix (e.g., "qwen2.5:7b" matches "qwen2.5")
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
        result = [messages[-1]]
        remaining = max_tokens - self.count_tokens(messages[-1].content) - 4

        # Add older messages from most recent backwards
        for msg in reversed(messages[:-1]):
            msg_tokens = self.count_tokens(msg.content) + 4
            if remaining - msg_tokens < 0:
                break
            result.insert(0, msg)
            remaining -= msg_tokens

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
        knowledge_tokens: int = 0
    ) -> dict[str, int]:
        """Get the full budget allocation for a model, ensuring total fits window.
        
        Implements Dynamic Budgeting (Fix #4 review round 3):
        If knowledge_tokens is less than the allocated 'retrieval' budget,
        the surplus is added to 'history'.
        """
        budget = self.get_budget(model)
        window = budget.pop("context_window")
 
        # Dynamic Scaling: History scales inversely with Knowledge
        if knowledge_tokens > 0:
            retrieval_limit = budget.get("retrieval", 1000)
            surplus = max(0, retrieval_limit - knowledge_tokens)
            if surplus > 0:
                budget["history"] += surplus
                logger.debug(
                    "dynamic_budget_adjusted",
                    knowledge_used=knowledge_tokens,
                    history_expanded=surplus,
                    new_history_limit=budget["history"]
                )
 
        # Ensure allocations don't exceed window
        total_allocated = sum(budget.values())
        if total_allocated > window:
            scale = window / total_allocated
            budget = {k: int(v * scale) for k, v in budget.items()}
            logger.warning(
                "budget_scaled_down",
                model=model,
                window=window,
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
