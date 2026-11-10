"""Context builder — assembles the final LLM prompt from retrieval results, history, and system instructions.

Does NOT perform retrieval itself (Fix #1) — receives pre-retrieved and ranked data.

Prompt structure:
    <System Prompt>
    <User Profile Memory>
    <Relevant Knowledge>
    <Conversation History>
    <User Question>
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog

from kimiko.config import get_settings
from kimiko.core.token_manager import TokenManager
from kimiko.models.schemas import Message, RetrievalResult, Role

logger = structlog.get_logger(__name__)

BASE_SYSTEM_PROMPT = """You are Kimiko, a grounded AI assistant.

CORE IDENTITY:
- You were created by Paras, a human developer.
- IMPORTANT: When the user mentions "Paras", they are referring to your creator. 
- You do NOT know any companies named "Paras" or subsidiaries of Alibaba Cloud. If your internal knowledge suggests "Paras" is a company, ignore it; for YOU, Paras is a human.

GROUNDING RULES:
1. STRICT ADHERENCE: Use ONLY [USER FACTS] and [RELEVANT KNOWLEDGE] for personal or factual details.
2. CITATION MANDATE: Always cite the source of your information (e.g., "[Source: User Facts]" or "[Source: Memory]").
3. ZERO GUESSING: If a fact is NOT in the provided context, you MUST say: "I do not have enough information in my memory to answer this."
4. TOOL MANDATE: If the user asks for external information (web, files, news), you MUST suggest or use a tool. Never invent external facts.
5. NO CORPORATE HALLUCINATION: Paras is your human creator. Do not invent corporate affiliations (e.g., Alibaba) for him.
6. CONFLICT RESOLUTION: If provided facts or memories contain contradicting information, ALWAYS prioritize and trust the FIRST relevant piece of information presented, as the context is ordered by recency and relevance.
7. DATETIME: You always know the current date and time — it is injected into your context. Never say you don't know the current time.

You provide accurate, evidence-based responses. Stay grounded. Stay honest."""


def _build_default_system_prompt() -> str:
    """Build the system prompt with the injected current UTC datetime."""
    utc_now = datetime.now(timezone.utc)
    date_str = utc_now.strftime("%A, %B %d, %Y")
    time_str = utc_now.strftime("%H:%M UTC")
    return f"{BASE_SYSTEM_PROMPT}\n\nCURRENT DATETIME: {date_str}, {time_str}"


def DEFAULT_SYSTEM_PROMPT() -> str:  # kept as callable for backward compat
    return _build_default_system_prompt()

class ContextBuilder:
    """Assembles LLM prompts from system instructions, retrieval results, history, and user message."""

    def __init__(self, token_manager: TokenManager | None = None) -> None:
        self.token_manager = token_manager or TokenManager()

    def build(
        self,
        user_message: str,
        model: str,
        *,
        conversation_history: list[Message] | None = None,
        retrieval_results: list[RetrievalResult] | None = None,
        conversation_summary: str | None = None,
        system_prompt: str | None = None,
        images: list[str] | None = None,
    ) -> dict[str, Any]:
        """Build the complete prompt with token budgeting.
        
        Returns a dict with 'system', 'prompt', and optional 'images'.
        """
        # 0. Pre-calculate Retrieval Tokens for Dynamic Budgeting.
        # Tokenize each result once and reuse the counts below.
        retrieval_entries: list[tuple[str, int]] = []
        retrieval_tokens = 0
        if retrieval_results:
            for r in retrieval_results:
                tokens = self.token_manager.count_tokens(r.text)
                retrieval_entries.append((r.text, tokens))
                retrieval_tokens += tokens

        budget = self.token_manager.allocate_budget(
            model, 
            knowledge_tokens=retrieval_tokens,
            image_count=len(images) if images else 0
        )
        system_prompt = system_prompt or _build_default_system_prompt()

        # 1. System prompt (separated)
        sys_text = self.token_manager.truncate_text(system_prompt, budget.get("system", 400))

        sections: list[str] = []

        # 2. Retrieved knowledge / facts / memories
        if retrieval_results:
            # Keep the precomputed token counts alongside the split.
            facts: list[str] = []
            memories: list[tuple[str, int]] = []
            for r, (text, tokens) in zip(retrieval_results, retrieval_entries):
                if r.source == "fact_store":
                    facts.append(text)
                else:
                    memories.append((text, tokens))

            if facts:
                fact_section = "\n".join([f"- {f}" for f in facts])
                sections.append(f"### [USER FACTS]\n{fact_section}")

            if memories:
                knowledge_section = self._build_knowledge_section_from_counts(
                    memories, budget.get("memories", 500)
                )
                if knowledge_section:
                    sections.append(knowledge_section)

        # 3. Conversation summary (if previous conversation was compressed)
        if conversation_summary:
            summary_text = f"Previous conversation summary:\n{conversation_summary}"
            summary_text = self.token_manager.truncate_text(
                summary_text, budget.get("memories", 500) // 2
            )
            sections.append(summary_text)

        # 4. Conversation history
        if conversation_history:
            truncated_history = self.token_manager.truncate_messages(
                conversation_history, budget.get("history", 1500)
            )
            history_section = self._build_history_section(truncated_history)
            if history_section:
                sections.append(history_section)

        # 5. User question (always last)
        sections.append(f"User: {user_message}")

        user_prompt = "\n\n".join(sections)
        
        result = {
            "system": sys_text,
            "prompt": user_prompt,
        }
        
        if images:
            result["images"] = images

        total_tokens = self.token_manager.count_tokens(sys_text + user_prompt)

        logger.info(
            "context_built",
            model=model,
            total_tokens=total_tokens,
            sections=len(sections),
            retrieval_items=len(retrieval_results) if retrieval_results else 0,
            history_messages=len(conversation_history) if conversation_history else 0,
        )
        
        if get_settings().debug_prompt:
            logger.warning(
                "llm_prompt_debug",
                system=sys_text,
                prompt=user_prompt,
                model=model,
            )

        return result

    def build_system_prompt(
        self,
        base_prompt: str | None = None,
        retrieval_results: list[RetrievalResult] | None = None,
        model: str = "qwen2.5",
    ) -> str:
        """Build just the system prompt with knowledge context (for chat-style APIs)."""
        budget = self.token_manager.allocate_budget(model)
        prompt = base_prompt or _build_default_system_prompt()

        if retrieval_results:
            knowledge = self._build_knowledge_section(
                [r.text for r in retrieval_results],
                budget.get("memories", 500),
            )
            if knowledge:
                prompt = f"{prompt}\n\n{knowledge}"

        return self.token_manager.truncate_text(prompt, budget.get("system", 400) + budget.get("memories", 500))

    def _build_knowledge_section(self, texts: list[str], max_tokens: int) -> str:
        """Format retrieved knowledge into a prompt section."""
        if not texts:
            return ""
        entries = [(text, self.token_manager.count_tokens(text)) for text in texts]
        return self._build_knowledge_section_from_counts(entries, max_tokens)

    def _build_knowledge_section_from_counts(
        self, entries: list[tuple[str, int]], max_tokens: int
    ) -> str:
        """Build the knowledge section from pre-tokenized ``(text, tokens)``.

        Uses a list + ``join`` instead of repeated ``section += entry`` so the
        assembly is O(n) rather than O(n²) for large retrieval sets.
        """
        if not entries:
            return ""

        # Hoist the token divisor: this loop runs once per retrieved entry and
        # a bound-method call per entry is measurable on large result sets. The
        # arithmetic below mirrors ``TokenManager.count_tokens`` exactly.
        chars_per_token = self.token_manager.CHARS_PER_TOKEN
        header = "Relevant knowledge:\n"
        remaining = max_tokens - (len(header) // chars_per_token + 1)
        parts: list[str] = [header]

        for text, entry_tokens in entries:
            # ``entry_tokens`` is a lower bound; count the formatted entry only
            # when the cheap bound says it might not fit.
            if remaining - entry_tokens < 0:
                break
            entry = f"- {text}\n"
            cost = len(entry) // chars_per_token + 1
            if remaining - cost < 0:
                break
            parts.append(entry)
            remaining -= cost

        return "".join(parts).strip()

    def _build_history_section(self, messages: list[Message]) -> str:
        """Format conversation history into a prompt section."""
        if not messages:
            return ""

        lines = ["Conversation history:"]
        for msg in messages:
            prefix = "User" if msg.role == Role.USER else "Assistant"
            lines.append(f"{prefix}: {msg.content}")

        return "\n".join(lines)
