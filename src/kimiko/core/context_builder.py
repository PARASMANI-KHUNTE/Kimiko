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

import structlog

from kimiko.config import get_settings
from kimiko.core.token_manager import TokenManager
from kimiko.models.schemas import Message, RetrievalResult, Role

logger = structlog.get_logger(__name__)

DEFAULT_SYSTEM_PROMPT = """You are Kimiko, an advanced AI assistant created by Paras.
You are helpful, knowledgeable, and conversational.
You provide clear, accurate, and thoughtful responses.
When you don't know something, you say so honestly.
You can help with coding, analysis, creative tasks, and general questions."""


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
    ) -> Union[str, dict[str, Any]]:
        """Build the complete prompt with token budgeting.
        
        Returns a prompt string OR a dict for multimodal models.
        """
        # 0. Pre-calculate Retrieval Tokens for Dynamic Budgeting
        retrieval_tokens = 0
        if retrieval_results:
            for r in retrieval_results:
                retrieval_tokens += self.token_manager.count_tokens(r.text)
 
        budget = self.token_manager.allocate_budget(
            model, 
            knowledge_tokens=retrieval_tokens,
            image_count=len(images) if images else 0
        )
        system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT

        sections: list[str] = []

        # 1. System prompt (always first)
        sys_text = self.token_manager.truncate_text(system_prompt, budget.get("system", 400))
        sections.append(sys_text)

        # 2. Retrieved knowledge / facts / memories
        if retrieval_results:
            facts = [r.text for r in retrieval_results if r.source == "fact_store"]
            memories = [r.text for r in retrieval_results if r.source != "fact_store"]
            
            if facts:
                fact_section = "\n".join([f"- {f}" for f in facts])
                sections.append(f"### [USER FACTS]\n{fact_section}")

            if memories:
                knowledge_section = self._build_knowledge_section(
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

        prompt = "\n\n".join(sections)
        
        # If images are present, return a structured prompt for LLMService
        if images:
            return {
                "prompt": prompt,
                "images": images
            }

        total_tokens = self.token_manager.count_tokens(prompt)

        logger.info(
            "context_built",
            model=model,
            total_tokens=total_tokens,
            sections=len(sections),
            retrieval_items=len(retrieval_results) if retrieval_results else 0,
            history_messages=len(conversation_history) if conversation_history else 0,
        )
        
        # 6. Debug Logging (Fix #2 review round 3)
        if get_settings().debug_prompt:
            logger.debug(
                "llm_prompt_debug",
                prompt=prompt,
                model=model,
            )

        return prompt

    def build_system_prompt(
        self,
        base_prompt: str | None = None,
        retrieval_results: list[RetrievalResult] | None = None,
        model: str = "qwen2.5",
    ) -> str:
        """Build just the system prompt with knowledge context (for chat-style APIs)."""
        budget = self.token_manager.allocate_budget(model)
        prompt = base_prompt or DEFAULT_SYSTEM_PROMPT

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

        section = "Relevant knowledge:\n"
        remaining = max_tokens - self.token_manager.count_tokens(section)

        for i, text in enumerate(texts):
            entry = f"- {text}\n"
            entry_tokens = self.token_manager.count_tokens(entry)
            if remaining - entry_tokens < 0:
                break
            section += entry
            remaining -= entry_tokens

        return section.strip()

    def _build_history_section(self, messages: list[Message]) -> str:
        """Format conversation history into a prompt section."""
        if not messages:
            return ""

        lines = ["Conversation history:"]
        for msg in messages:
            prefix = "User" if msg.role == Role.USER else "Assistant"
            lines.append(f"{prefix}: {msg.content}")

        return "\n".join(lines)
