"""Conversation summarizer — compresses long conversations via LLM (Fix #3).

When message count exceeds threshold, summarize → store summary → prune messages.
"""

from __future__ import annotations

import structlog

from kimiko.models.schemas import Message
from kimiko.services.llm import get_llm_service

logger = structlog.get_logger(__name__)

SUMMARIZE_PROMPT = """Summarize the following conversation concisely. 
Capture the key topics discussed, any decisions made, and important context.
Keep the summary under 200 words.

Conversation:
{conversation}

Summary:"""


class ConversationSummarizer:
    """Summarizes conversations using the LLM to enable context compression."""

    async def summarize(self, messages: list[Message], model: str | None = None) -> str:
        """Generate a summary of the conversation messages."""
        from kimiko.config import get_settings

        settings = get_settings()
        llm = get_llm_service()
        model = model or settings.default_model

        # Format conversation for summarization
        conversation_text = self._format_conversation(messages)

        prompt = SUMMARIZE_PROMPT.format(conversation=conversation_text)

        try:
            result = await llm.generate(
                model=model,
                prompt=prompt,
                temperature=0.3,  # Low temp for factual summary
                max_tokens=300,
            )
            summary = result.get("response", "").strip()

            logger.info(
                "conversation_summarized",
                message_count=len(messages),
                summary_length=len(summary),
            )
            return summary

        except Exception as e:
            logger.error("summarization_failed", error=str(e))
            # Fallback: create a simple extractive summary
            return self._fallback_summary(messages)

    def _format_conversation(self, messages: list[Message]) -> str:
        """Format messages into a readable conversation string."""
        lines = []
        for msg in messages:
            lines.append(f"{msg.role.value}: {msg.content}")
        return "\n".join(lines)

    def _fallback_summary(self, messages: list[Message]) -> str:
        """Simple extractive fallback if LLM summarization fails."""
        # Take first and last few messages as summary
        preview = []
        if len(messages) > 4:
            preview = messages[:2] + messages[-2:]
        else:
            preview = messages

        parts = [f"[{m.role.value}] {m.content[:100]}" for m in preview]
        return "Conversation excerpt: " + " | ".join(parts)
