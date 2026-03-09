"""Retrieval engine — orchestrates memory + semantic retrieval, then ranks results.

This module is the SEPARATE retrieval step in the pipeline (Fix #1 from review):
  Intent → Retrieval Engine → Context Ranking → Context Builder
"""

from __future__ import annotations

import time
import re
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from kimiko.core.ranking import RetrievalRanker
from kimiko.memory.manager import MemoryManager
from kimiko.memory.fact_store import FactStore
from kimiko.models.schemas import RetrievalResult

logger = structlog.get_logger(__name__)


class RetrievalEngine:
    """Orchestrates retrieval from multiple sources and ranks results."""

    def __init__(self, memory_manager: MemoryManager) -> None:
        self.memory = memory_manager
        self.ranker = RetrievalRanker()

    @staticmethod
    def _conflict_sort_key(item: dict) -> tuple[float, float, float, float]:
        """Stable conflict ordering: newest first, with deterministic tie-breakers.

        Order by:
        1) primary timestamp
        2) updated timestamp
        3) created timestamp
        4) score
        """
        metadata = item.get("metadata", {}) or {}
        primary_ts = float(metadata.get("timestamp") or 0.0)
        updated_ts = float(metadata.get("updated_timestamp") or primary_ts)
        created_ts = float(metadata.get("created_timestamp") or updated_ts)
        score = float(item.get("final_score") or item.get("score") or 0.0)
        return (primary_ts, updated_ts, created_ts, score)

    @staticmethod
    def _extract_conflict_key(text: str) -> str | None:
        """Extract a coarse conflict key for mutable personal preferences.

        Example:
        - "My favorite programming language is Python"
        - "Actually my favorite language is Rust now"
        both map to: "favorite:language"
        """
        normalized = text.lower().replace("fact (preference):", "").strip()
        match = re.search(r"favorite\s+([a-z\s-]{1,40}?)\s+is\s+([^\n\.;]+)", normalized)
        if not match:
            return None

        topic = match.group(1).strip()
        topic_tokens = [t for t in re.split(r"[\s-]+", topic) if t]
        if not topic_tokens:
            return None

        # Use the head noun-ish token as a stable key across phrasing variants
        # like "programming language" vs "language".
        return f"favorite:{topic_tokens[-1]}"

    def _resolve_conflicts(self, ranked: list[dict]) -> list[dict]:
        """Keep newest winner per conflict key and preserve strongest group score.

        This avoids stale high-similarity memories overriding newer user updates.
        """
        grouped: dict[str, list[dict]] = {}
        passthrough: list[dict] = []

        for item in ranked:
            key = self._extract_conflict_key(str(item.get("text", "")))
            if not key:
                passthrough.append(item)
                continue
            grouped.setdefault(key, []).append(item)

        winners: list[dict] = []
        for group_items in grouped.values():
            group_items.sort(key=self._conflict_sort_key, reverse=True)
            winner = group_items[0]
            max_group_score = max(float(i.get("final_score") or i.get("score") or 0.0) for i in group_items)
            winner["final_score"] = max(float(winner.get("final_score") or 0.0), max_group_score)
            winners.append(winner)

        return passthrough + winners

    @staticmethod
    def _passes_threshold(item: dict, default_threshold: float) -> bool:
        """Source-aware thresholding to avoid dropping stable long-term memories."""
        source = str(item.get("source", ""))
        score = float(item.get("final_score") or item.get("score") or 0.0)

        # Long-term and fact-store entries are already curated; keep them with a lower cutoff.
        if source in {"long_term", "fact_store"}:
            return score >= 0.45
        return score >= default_threshold

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
                db=db, user_id=user_id, limit=5
            )
            for mem in lt_memories:
                all_results.append({
                    "text": mem["text"],
                    "score": mem["importance"],
                    "importance": mem["importance"],
                    "source": "long_term",
                    "metadata": {
                        "type": mem.get("memory_type", "general"),
                        "timestamp": mem["created_at"].timestamp() if mem.get("created_at") else time.time(),
                        "created_timestamp": mem["created_at"].timestamp() if mem.get("created_at") else time.time(),
                    },
                })

            # 3b. Fact Store (Phase 3)
            fact_store = FactStore(db)
            user_facts = await fact_store.get_facts(user_id)
            for f in user_facts:
                created_at = f.created_at.timestamp() if getattr(f, "created_at", None) else time.time()
                updated_at = f.updated_at.timestamp() if getattr(f, "updated_at", None) else created_at
                last_seen = f.last_seen.timestamp() if f.last_seen else updated_at
                all_results.append({
                    "text": f"Fact ({f.category}): {f.fact}",
                    "score": f.importance,
                    "importance": f.importance,
                    "confidence": f.confidence_score,
                    "source": "fact_store",
                    "category": f.category,
                    "metadata": {
                        "category": f.category, 
                        "type": "fact",
                        "timestamp": last_seen,
                        "updated_timestamp": updated_at,
                        "created_timestamp": created_at,
                    },
                })

        # 4. Rank all results with hybrid scoring
        MIN_RETRIEVAL_SCORE = 0.65
        if all_results:
            ranked = self.ranker.rank(all_results)
            ranked = self._resolve_conflicts(ranked)
            # Filter by minimum score threshold to prevent hallucination from weak matches
            filtered = [r for r in ranked if self._passes_threshold(r, MIN_RETRIEVAL_SCORE)]
            
            if not filtered and ranked:
                logger.warning("all_results_filtered_below_threshold", top_score=ranked[0].get("final_score"))
            
            ranked = filtered[:top_k]
            
            # PHASE 5.7: Conflict Resolution Support
            # Sort final context strictly by recency (newest first) so the LLM
            # sees the most recent conflicting memories first (trusts FIRST rule).
            ranked.sort(key=self._conflict_sort_key, reverse=True)
        else:
            ranked = []

        # 5. Convert to RetrievalResult with strict defensive casting
        results = []
        for r in ranked:
            score_val = r.get("final_score")
            if score_val is None:
                score_val = r.get("score", 0.0)
                
            results.append(RetrievalResult(
                text=str(r.get("text", "")),
                score=float(score_val or 0.0),
                importance=float(r.get("importance") or 0.5),
                confidence=float(r.get("confidence") or 1.0),
                source=str(r.get("source", "unknown")),
                metadata=dict(r.get("metadata") or {}),
            ))

        logger.info(
            "retrieval_complete",
            query_preview=query[:50],
            total_sources=len(all_results),
            returned=len(results),
        )

        return results
