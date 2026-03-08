"""Retrieval ranking — hybrid scoring for memory/document results (Fix #1 review round 2).

score = semantic_similarity × 0.7 + recency_score × 0.2 + tag_match × 0.1
"""

from __future__ import annotations

import time

import structlog

logger = structlog.get_logger(__name__)

# ── Weights (Fix #3 review round 3) ──
SEMANTIC_WEIGHT = 0.6
RECENCY_WEIGHT = 0.2
TAG_MATCH_WEIGHT = 0.1
IMPORTANCE_WEIGHT = 0.1

# How quickly recency decays (seconds). Memories older than this get score ~0.
RECENCY_DECAY_SECONDS = 7 * 24 * 3600  # 7 days


class RetrievalRanker:
    """Hybrid ranker combining semantic similarity, recency, and tag matching."""

    def __init__(
        self,
        semantic_weight: float = SEMANTIC_WEIGHT,
        recency_weight: float = RECENCY_WEIGHT,
        tag_weight: float = TAG_MATCH_WEIGHT,
        importance_weight: float = IMPORTANCE_WEIGHT,
        recency_decay: float = RECENCY_DECAY_SECONDS,
    ) -> None:
        self.semantic_weight = semantic_weight
        self.recency_weight = recency_weight
        self.tag_weight = tag_weight
        self.importance_weight = importance_weight
        self.recency_decay = recency_decay

    def compute_recency_score(self, timestamp: float) -> float:
        """Compute recency score with exponential decay.

        Returns 1.0 for now, decaying toward 0.0 as age → recency_decay.
        """
        age = time.time() - timestamp
        if age <= 0:
            return 1.0
        # Exponential decay
        score = max(0.0, 1.0 - (age / self.recency_decay))
        return score

    def compute_tag_match_score(
        self, item_tags: list[str], query_tags: list[str]
    ) -> float:
        """Compute tag overlap score (Jaccard-like)."""
        if not item_tags or not query_tags:
            return 0.0
        item_set = set(t.lower() for t in item_tags)
        query_set = set(t.lower() for t in query_tags)
        intersection = item_set & query_set
        union = item_set | query_set
        return len(intersection) / len(union) if union else 0.0

    def rank(
        self,
        results: list[dict],
        query_tags: list[str] | None = None,
    ) -> list[dict]:
        """Rank retrieval results using the hybrid scoring function.

        Each result dict should have:
            - score: float (semantic similarity from vector search)
            - metadata.timestamp: float (unix timestamp)
            - metadata.tags: list[str] (optional)
        """
        query_tags = query_tags or []
        scored = []

        for item in results:
            semantic_score = item.get("score", 0.0)

            metadata = item.get("metadata", {})
            timestamp = metadata.get("timestamp", time.time())
            item_tags = metadata.get("tags", [])

            importance_score = item.get("importance", 0.5)
            recency_score = self.compute_recency_score(timestamp)
            tag_score = self.compute_tag_match_score(item_tags, query_tags)
 
            final_score = (
                self.semantic_weight * semantic_score
                + self.recency_weight * recency_score
                + self.tag_weight * tag_score
                + self.importance_weight * importance_score
            )

            scored_item = {**item, "final_score": final_score}
            scored.append(scored_item)

        # Sort by final score descending
        scored.sort(key=lambda x: x["final_score"], reverse=True)

        logger.debug(
            "retrieval_ranked",
            total_items=len(scored),
            top_score=scored[0]["final_score"] if scored else 0,
        )

        return scored
