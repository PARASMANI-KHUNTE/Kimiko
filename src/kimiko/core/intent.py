"""Intent classifier — rule-based + keyword matching for Phase 1.

Classifies incoming user messages into intents before model routing.

Performance: every pattern is compiled once at import time. The previous
implementation re-ran ``re.findall`` with a string pattern for every intent on
every request, which repeatedly hit the regex cache and allocated match lists.
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

# Compiled once. Tuples are immutable and cheap to iterate.
_COMPILED_PATTERNS: tuple[tuple[Intent, tuple[re.Pattern[str], ...]], ...] = tuple(
    (intent, tuple(re.compile(pattern) for pattern in patterns))
    for intent, patterns in _INTENT_PATTERNS.items()
)


class IntentClassifier:
    """Rule-based intent classifier. Will be upgraded to ML in Phase 2+."""

    def classify(self, text: str) -> IntentResult:
        """Classify the intent of a user message."""
        text_lower = text.lower().strip()

        # A fenced code block is an unambiguous code signal; skip the scan.
        if "```" in text_lower:
            return IntentResult(intent=Intent.CODE, confidence=1.0)

        best_intent = Intent.CHAT
        best_score = 0.0

        for intent, patterns in _COMPILED_PATTERNS:
            score = 0.0
            for pattern in patterns:
                # ``search`` stops at the first match and allocates no match
                # list, unlike ``findall``. One hit per pattern is enough for
                # intent selection; cap at 1.0 and move on.
                if pattern.search(text_lower):
                    score += 0.3
                if score >= 1.0:
                    score = 1.0
                    break
            if score > best_score:
                best_score = score
                best_intent = intent
                if score >= 1.0:
                    break

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
