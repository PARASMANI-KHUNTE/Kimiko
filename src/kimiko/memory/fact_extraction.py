"""Fact extraction service — extracts structured facts from conversation history."""

from __future__ import annotations

import json

import structlog
from pydantic import BaseModel, Field

from kimiko.models.schemas import Message
from kimiko.services.llm import get_llm_service

logger = structlog.get_logger(__name__)

FACT_EXTRACTION_PROMPT = """
Extract persistent facts and user preferences from the following conversation segment.
Return a JSON list of objects with 'category', 'fact', and 'importance'.

Categories:
- preference (e.g., "likes blue", "hates cilantro")
- fact (e.g., "lives in Tokyo", "is a software engineer")
- persona (e.g., "is helpful", "prefers concise answers")

Rules:
- Only extract clear, persistent facts.
- Do NOT extract transient state (e.g., "is hungry now").
- Output MUST be valid JSON.

Example Output:
[
  {"category": "preference", "fact": "likes dark mode", "importance": 0.8},
  {"category": "fact", "fact": "works at Google", "importance": 0.7}
]

Conversation:
{conversation}
"""


class ExtractedFact(BaseModel):
    category: str
    fact: str
    importance: float = Field(ge=0.0, le=1.0)


class FactExtractionService:
    """Uses LLM to extract structured facts from dialogue."""

    def __init__(self, model: str = "qwen3.5:4b") -> None:
        self.model = model
        self.llm = get_llm_service()

    async def extract(self, messages: list[Message]) -> list[ExtractedFact]:
        """Extract facts from a list of messages."""
        if not messages:
            return []

        # Format conversation for prompt (join is O(n); repeated += was O(n²)).
        conv_text = "\n".join(f"{m.role}: {m.content}" for m in messages)

        prompt = FACT_EXTRACTION_PROMPT.format(conversation=conv_text)

        try:
            response = await self.llm.generate(
                model=self.model,
                prompt=prompt,
                temperature=0.1,  # Low temperature for extraction
            )

            content = response.get("response", "")
            # Basic JSON extraction from markdown if necessary
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "[" in content:
                # Attempt to find the first [ and last ]
                start = content.find("[")
                end = content.rfind("]") + 1
                content = content[start:end]

            facts_data = json.loads(content)
            return [ExtractedFact(**f) for f in facts_data]

        except Exception as e:
            logger.error("fact_extraction_failed", error=str(e), content=content if 'content' in locals() else None)
            return []
