"""Retrieval engine — orchestrates memory + semantic retrieval, then ranks results.

This module is the SEPARATE retrieval step in the pipeline (Fix #1 from review):
  Intent → Retrieval Engine → Context Ranking → Context Builder

Performance notes
-----------------
The three sources (conversation summary, vector search, SQL memory/facts) are
independent. They now run concurrently with ``asyncio.gather`` so an embedding
round-trip overlaps with database work instead of stacking on top of it.
Duplicate texts are collapsed with a hash map before ranking, and conflict
groups pick their winner in O(n) instead of sorting every group.
"""

from __future__ import annotations

import asyncio
import re
import time
from functools import lru_cache

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from kimiko.core.ranking import RetrievalRanker
from kimiko.memory.fact_store import FactStore
from kimiko.memory.manager import MemoryManager
from kimiko.models.schemas import RetrievalResult

logger = structlog.get_logger(__name__)

# Compiled once; was previously recompiled via ``re.search(pattern_str, ...)``
# for every result on every request.
_FAVORITE_RE = re.compile(r"favorite\s+([a-z\s-]{1,40}?)\s+is\s+([^\n\.;]+)")
_TOPIC_SPLIT_RE = re.compile(r"[\s-]+")


@lru_cache(maxsize=2048)
def _extract_conflict_key_cached(normalized: str) -> str | None:
    match = _FAVORITE_RE.search(normalized)
    if not match:
        return None

    topic_tokens = [t for t in _TOPIC_SPLIT_RE.split(match.group(1).strip()) if t]
    if not topic_tokens:
        return None

    # Use the head noun-ish token as a stable key across phrasing variants
    # like "programming language" vs "language".
    return f"favorite:{topic_tokens[-1]}"


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
        return _extract_conflict_key_cached(normalized)

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
            if len(group_items) == 1:
                winners.append(group_items[0])
                continue

            # Single O(n) pass: pick the max ordering key and the strongest
            # score in the group at once (sorting the group is O(n log n)).
            sort_key = self._conflict_sort_key
            winner = group_items[0]
            best_key = sort_key(winner)
            max_group_score = float(
                winner.get("final_score") or winner.get("score") or 0.0
            )
            for item in group_items[1:]:
                key = sort_key(item)
                if key > best_key:
                    winner, best_key = item, key
                item_score = float(item.get("final_score") or item.get("score") or 0.0)
                if item_score > max_group_score:
                    max_group_score = item_score
            winner["final_score"] = max(
                float(winner.get("final_score") or 0.0), max_group_score
            )
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

    @staticmethod
    def _score(item: dict) -> float:
        return float(item.get("final_score") or item.get("score") or 0.0)

    async def _summary_results(self, session_id: str) -> list[dict]:
        summary = await self.memory.get_conversation_summary(session_id)
        if not summary:
            return []
        return [
            {
                "text": summary,
                "score": 0.8,  # High base score for conversation context
                "importance": 1.0,
                "source": "short_term",
                "metadata": {"type": "conversation_summary", "tags": []},
            }
        ]

    async def _semantic_results(
        self, query: str, user_id: str, top_k: int
    ) -> list[dict]:
        semantic_results = await self.memory.search(
            query=query, user_id=user_id, top_k=top_k
        )
        return [
            {
                "text": sr["text"],
                "score": sr["score"],
                "importance": sr.get("metadata", {}).get("importance", 0.5),
                "source": "semantic",
                "metadata": sr.get("metadata", {}),
            }
            for sr in semantic_results
        ]

    async def _persistent_results(
        self, db: AsyncSession, user_id: str, fact_limit: int
    ) -> list[dict]:
        """Read SQL-backed memories + facts (sequentially on one session)."""
        results: list[dict] = []

        lt_memories = await self.memory.retrieve_memories(
            db=db, user_id=user_id, limit=5
        )
        for mem in lt_memories:
            created_at = mem.get("created_at")
            created_ts = created_at.timestamp() if created_at else time.time()
            results.append(
                {
                    "text": mem["text"],
                    "score": mem["importance"],
                    "importance": mem["importance"],
                    "source": "long_term",
                    "metadata": {
                        "type": mem.get("memory_type", "general"),
                        "timestamp": created_ts,
                        "created_timestamp": created_ts,
                    },
                }
            )

        fact_store = FactStore(db)
        user_facts = await fact_store.get_facts(user_id, limit=fact_limit)
        for f in user_facts:
            created_at = f.created_at.timestamp() if getattr(f, "created_at", None) else time.time()
            updated_at = f.updated_at.timestamp() if getattr(f, "updated_at", None) else created_at
            last_seen = f.last_seen.timestamp() if f.last_seen else updated_at
            results.append(
                {
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
                }
            )

        return results

    async def retrieve(
        self,
        query: str,
        session_id: str | None = None,
        user_id: str | None = None,
        db: AsyncSession | None = None,
        top_k: int = 10,
        *,
        conversation_summary: str | None = None,
        include_summary: bool = True,
    ) -> list[RetrievalResult]:
        """Execute full retrieval pipeline:
        1. Short-term conversation history
        2. Semantic vector search
        3. Long-term memory lookup
        4. Hybrid ranking
        5. Return top-k results
        """
        all_results: list[dict] = []

        # Callers that already fetched the summary pass it in to save a Redis GET.
        if conversation_summary is not None:
            all_results.append(
                {
                    "text": conversation_summary,
                    "score": 0.8,
                    "importance": 1.0,
                    "source": "short_term",
                    "metadata": {"type": "conversation_summary", "tags": []},
                }
            )
            include_summary = False

        # Build the independent source coroutines.
        coros = []
        labels: list[str] = []

        if include_summary and session_id:
            coros.append(self._summary_results(session_id))
            labels.append("short_term")
        if user_id:
            coros.append(self._semantic_results(query, user_id, top_k))
            labels.append("semantic")
        if db is not None and user_id:
            fact_limit = max(10, top_k * 2)
            coros.append(self._persistent_results(db, user_id, fact_limit))
            labels.append("long_term")

        if coros:
            gathered = await asyncio.gather(*coros, return_exceptions=True)
            for label, batch in zip(labels, gathered):
                if isinstance(batch, BaseException):
                    # One backend being slow/down should not discard the others.
                    logger.warning(
                        "retrieval_source_failed",
                        source=label,
                        error=str(batch),
                    )
                    continue
                all_results.extend(batch)

        # 4. Deduplicate identical texts, keeping the highest-scoring copy.
        if all_results:
            best_by_text: dict[str, dict] = {}
            for item in all_results:
                text = str(item.get("text", "")).strip()
                if not text:
                    continue
                item["text"] = text
                key = text.casefold()
                previous = best_by_text.get(key)
                if previous is None or self._score(item) > self._score(previous):
                    best_by_text[key] = item
            all_results = list(best_by_text.values())

        # 5. Rank all results with hybrid scoring
        MIN_RETRIEVAL_SCORE = 0.65
        if all_results:
            ranked = self.ranker.rank(all_results)
            ranked = self._resolve_conflicts(ranked)
            # Filter by minimum score threshold to prevent hallucination from weak matches
            filtered = [r for r in ranked if self._passes_threshold(r, MIN_RETRIEVAL_SCORE)]
            
            if not filtered and ranked:
                logger.warning(
                    "all_results_filtered_below_threshold",
                    top_score=ranked[0].get("final_score"),
                )
            
            ranked = filtered[:top_k]
            
            # PHASE 5.7: Conflict Resolution Support
            # Sort final context strictly by recency (newest first) so the LLM
            # sees the most recent conflicting memories first (trusts FIRST rule).
            ranked.sort(key=self._conflict_sort_key, reverse=True)
        else:
            ranked = []

        # 6. Convert to RetrievalResult with strict defensive casting
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
