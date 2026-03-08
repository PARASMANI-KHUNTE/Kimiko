"""Retrieval engine — orchestrates memory + semantic retrieval, then ranks results.

This module is the SEPARATE retrieval step in the pipeline (Fix #1 from review):
  Intent → Retrieval Engine → Context Ranking → Context Builder
"""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from kimiko.core.ranking import RetrievalRanker
from kimiko.memory.manager import MemoryManager
from kimiko.models.schemas import RetrievalResult

logger = structlog.get_logger(__name__)


class RetrievalEngine:
    """Orchestrates retrieval from multiple sources and ranks results."""

    def __init__(self, memory_manager: MemoryManager) -> None:
        self.memory = memory_manager
        self.ranker = RetrievalRanker()

    async def retrieve(
        self,
        query: str,
        session_id: str | None = None,
        user_id: str | None = None,
        db: AsyncSession | None = None,
        top_k: int = 10,
    ) -> list[RetrievalResult]:
        """Execute full retrieval pipeline:
        1. Short-term conversation history
        2. Semantic vector search
        3. Long-term memory lookup
        4. Hybrid ranking
        5. Return top-k results
        """
        all_results: list[dict] = []

        # 1. Conversation summary (if exists)
        if session_id:
            summary = await self.memory.get_conversation_summary(session_id)
            if summary:
                all_results.append({
                    "text": summary,
                    "score": 0.8,  # High base score for conversation context
                    "importance": 1.0,
                    "source": "short_term",
                    "metadata": {"type": "conversation_summary", "tags": []},
                })

        # 2. Semantic search in vector DB
        if user_id:
            semantic_results = await self.memory.search(
                query=query, user_id=user_id, top_k=top_k
            )
            for sr in semantic_results:
                all_results.append({
                    "text": sr["text"],
                    "score": sr["score"],
                    "importance": sr.get("metadata", {}).get("importance", 0.5),
                    "source": "semantic",
                    "metadata": sr.get("metadata", {}),
                })

        # 3. Long-term memory from PostgreSQL
        if db and user_id:
            lt_memories = await self.memory.retrieve_memories(
                db=db, user_id=user_id, limit=10
            )
            for mem in lt_memories:
                all_results.append({
                    "text": mem["text"],
                    "score": mem["importance"],  # Use importance as base score
                    "importance": mem["importance"],
                    "source": "long_term",
                    "metadata": {
                        "tags": mem.get("tags", []),
                        "type": mem.get("memory_type", "general"),
                        "timestamp": 0,  # Would convert created_at to timestamp
                    },
                })

        # 4. Rank all results with hybrid scoring
        if all_results:
            ranked = self.ranker.rank(all_results)
            # Take top-k after ranking
            ranked = ranked[:top_k]
        else:
            ranked = []

        # 5. Convert to RetrievalResult
        results = [
            RetrievalResult(
                text=r["text"],
                score=r.get("final_score", r.get("score", 0)),
                importance=r.get("importance", 0.5),
                source=r.get("source", "unknown"),
                metadata=r.get("metadata", {}),
            )
            for r in ranked
        ]

        logger.info(
            "retrieval_complete",
            query_preview=query[:50],
            total_sources=len(all_results),
            returned=len(results),
        )

        return results
