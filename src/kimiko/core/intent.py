"""Intent classifier — rule-based + keyword matching for Phase 1.

Classifies incoming user messages into intents before model routing.
"""

from __future__ import annotations

import re

import structlog

from kimiko.models.schemas import Intent, IntentResult

logger = structlog.get_logger(__name__)

# Keyword patterns for each intent
_INTENT_PATTERNS: dict[Intent, list[str]] = {
    Intent.GREETING: [
        r"\b(hi|hello|hey|howdy|greetings|good\s*(morning|afternoon|evening))\b",
    ],
    Intent.CODE: [
        r"\b(code|function|class|debug|error|traceback|implement|refactor|syntax)\b",
        r"\b(python|javascript|java|c\+\+|rust|golang|typescript|html|css)\b",
        r"```",
    ],
    Intent.IMAGE_ANALYSIS: [
        r"\b(image|photo|picture|screenshot|diagram|circuit|visual)\b",
        r"\b(what\s+(is|are)\s+this|analyze|describe\s+this)\b",
    ],
    Intent.DOCUMENT_QUERY: [
        r"\b(document|pdf|file|paper|article|summarize)\b",
    ],
    Intent.AGENT_TASK: [
        r"\b(step\s*by\s*step|plan|create\s+a\s+project|build\s+me|automate)\b",
    ],
    Intent.TOOL_REQUEST: [
        r"\b(search\s+the\s+web|run\s+command|execute|terminal|browse)\b",
    ],
    Intent.QUESTION: [
        r"\b(what|why|how|when|where|who|explain|describe|tell\s+me)\b",
    ],
}


class IntentClassifier:
    """Rule-based intent classifier. Will be upgraded to ML in Phase 2+."""

    def classify(self, text: str) -> IntentResult:
        """Classify the intent of a user message."""
        text_lower = text.lower().strip()

        # Score each intent
        scores: dict[Intent, float] = {}

        for intent, patterns in _INTENT_PATTERNS.items():
            score = 0.0
            for pattern in patterns:
                matches = re.findall(pattern, text_lower)
                score += len(matches) * 0.3
            scores[intent] = min(score, 1.0)

        # Find highest scoring intent
        if scores:
            best_intent = max(scores, key=lambda k: scores[k])
            best_score = scores[best_intent]

            if best_score > 0:
                logger.debug(
                    "intent_classified",
                    intent=best_intent.value,
                    confidence=best_score,
                    text_preview=text_lower[:50],
                )
                return IntentResult(intent=best_intent, confidence=best_score)

        # Default to chat
        return IntentResult(intent=Intent.CHAT, confidence=0.5)
