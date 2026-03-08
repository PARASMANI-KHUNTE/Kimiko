"""Memory manager — unified interface to all memory backends.

Coordinates short-term (Redis), long-term (PostgreSQL), and semantic (Qdrant)
memory with memory promotion logic (Fix #4 review round 2).
"""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from kimiko.memory.conversation_summarizer import ConversationSummarizer
from kimiko.memory.long_term import LongTermMemory
from kimiko.memory.semantic import SemanticMemory
from kimiko.memory.short_term import ShortTermMemory
from kimiko.models.schemas import Message

logger = structlog.get_logger(__name__)

# Memory promotion threshold — messages scoring above this are persisted
PROMOTION_IMPORTANCE_THRESHOLD = 0.6


class MemoryManager:
    """Unified memory interface coordinating all three storage layers."""

    def __init__(self) -> None:
        self.short_term = ShortTermMemory()
        self.long_term = LongTermMemory()
        self.semantic = SemanticMemory()
        self.summarizer = ConversationSummarizer()

    # ── Session / Short-Term ──

    async def add_message(self, session_id: str, message: Message) -> None:
        """Add a message to the session conversation history."""
        await self.short_term.add_message(session_id, message)

        # Check if summarization is needed
        if await self.short_term.needs_summarization(session_id):
            await self._trigger_summarization(session_id)

    async def get_conversation(self, session_id: str) -> list[Message]:
        """Get conversation history for a session."""
        return await self.short_term.get_messages(session_id)

    async def get_conversation_summary(self, session_id: str) -> str | None:
        """Get the compressed conversation summary if available."""
        return await self.short_term.get_summary(session_id)

    # ── Long-Term / Persistent ──

    async def store_memory(
        self,
        db: AsyncSession,
        user_id: str,
        text: str,
        tags: list[str] | None = None,
        memory_type: str = "general",
        importance: float = 0.5,
    ) -> str:
        """Store a persistent memory, optionally promoting to semantic index.

        Returns the memory ID.
        """
        # Store in PostgreSQL
        memory = await self.long_term.store(
            db=db,
            user_id=user_id,
            text=text,
            tags=tags,
            memory_type=memory_type,
            importance=importance,
        )

        # Memory promotion: only index important memories in vector DB
        vector_id = None
        if importance >= PROMOTION_IMPORTANCE_THRESHOLD:
            vector_id = await self.semantic.index(
                text=text,
                user_id=user_id,
                tags=tags,
                memory_type=memory_type,
            )
            memory.vector_id = vector_id
            await db.flush()

            logger.info(
                "memory_promoted_to_semantic",
                memory_id=str(memory.id),
                importance=importance,
            )

        return str(memory.id)

    async def retrieve_memories(
        self,
        db: AsyncSession,
        user_id: str,
        limit: int = 20,
        memory_type: str | None = None,
    ) -> list[dict]:
        """Retrieve persistent memories for a user."""
        memories = await self.long_term.retrieve(
            db=db, user_id=user_id, limit=limit, memory_type=memory_type
        )
        return [
            {
                "id": str(m.id),
                "text": m.text,
                "tags": m.tags or [],
                "memory_type": m.memory_type,
                "importance": m.importance,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in memories
        ]

    async def delete_memory(self, db: AsyncSession, memory_id: str) -> bool:
        """Delete a memory from both PostgreSQL and Qdrant."""
        memory = await self.long_term.get_by_id(db, memory_id)
        if memory and memory.vector_id:
            await self.semantic.delete(memory.vector_id)
        return await self.long_term.delete(db, memory_id)

    # ── Semantic Search ──

    async def search(
        self, query: str, user_id: str | None = None, top_k: int = 5
    ) -> list[dict]:
        """Perform semantic search across memories."""
        return await self.semantic.search(
            query=query, user_id=user_id, top_k=top_k
        )

    # ── Internal ──

    async def _trigger_summarization(self, session_id: str) -> None:
        """Summarize and compress conversation when threshold is exceeded."""
        messages = await self.short_term.get_messages(session_id)
        summary = await self.summarizer.summarize(messages)
        await self.short_term.store_summary(session_id, summary)
        logger.info("auto_summarization_triggered", session_id=session_id)

    async def clear_session(self, session_id: str) -> None:
        """Clear all session data."""
        await self.short_term.clear_session(session_id)
