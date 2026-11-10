"""Regression tests for memory conflict ordering."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from kimiko.core.retrieval_engine import RetrievalEngine


@dataclass
class _FakeFact:
    category: str
    fact: str
    importance: float
    confidence_score: float
    last_seen: datetime
    created_at: datetime
    updated_at: datetime


class _FakeMemoryManager:
    async def get_conversation_summary(self, session_id: str) -> str | None:
        return None

    async def search(self, query: str, user_id: str, top_k: int) -> list[dict]:
        return []

    async def retrieve_memories(self, db, user_id: str, limit: int) -> list[dict]:
        return []


class _FakeMemoryManagerLongTermOnly:
    async def get_conversation_summary(self, session_id: str) -> str | None:
        return None

    async def search(self, query: str, user_id: str, top_k: int) -> list[dict]:
        return []

    async def retrieve_memories(self, db, user_id: str, limit: int) -> list[dict]:
        base = datetime(2026, 3, 9, 12, 0, 0, tzinfo=timezone.utc)
        return [
            {
                "text": "My favorite programming language is Python.",
                "importance": 0.5,
                "memory_type": "general",
                "created_at": base - timedelta(days=2),
            },
            {
                "text": "Actually, I have decided my favorite language is Rust now.",
                "importance": 0.5,
                "memory_type": "general",
                "created_at": base,
            },
        ]


class _FakeFactStore:
    def __init__(self, _session) -> None:
        pass

    async def get_facts(self, _user_id: str, limit: int | None = None):
        base = datetime(2026, 3, 9, 12, 0, 0, tzinfo=timezone.utc)
        # Intentionally return in stale order and with equal last_seen to verify tie-breakers.
        return [
            _FakeFact(
                category="preference",
                fact="favorite language is Python",
                importance=0.9,
                confidence_score=1.0,
                last_seen=base,
                created_at=base - timedelta(days=10),
                updated_at=base - timedelta(days=10),
            ),
            _FakeFact(
                category="preference",
                fact="favorite language is Rust",
                importance=0.9,
                confidence_score=1.0,
                last_seen=base,
                created_at=base - timedelta(days=1),
                updated_at=base - timedelta(days=1),
            ),
        ]


class TestConflictResolution(unittest.IsolatedAsyncioTestCase):
    async def test_newer_fact_wins_when_last_seen_ties(self):
        engine = RetrievalEngine(memory_manager=_FakeMemoryManager())

        with patch("kimiko.core.retrieval_engine.FactStore", _FakeFactStore):
            results = await engine.retrieve(
                query="what is my favorite language?",
                user_id="11111111-1111-1111-1111-111111111111",
                db=object(),
                top_k=10,
            )

        fact_texts = [r.text for r in results if r.source == "fact_store"]
        self.assertEqual(len(fact_texts), 1)
        self.assertEqual(
            fact_texts[0],
            "Fact (preference): favorite language is Rust",
        )

    async def test_newer_wins_even_if_older_has_higher_similarity_score(self):
        engine = RetrievalEngine(memory_manager=_FakeMemoryManager())
        base = datetime(2026, 3, 9, 12, 0, 0, tzinfo=timezone.utc)
        ranked = [
            {
                "text": "My favorite programming language is Python.",
                "source": "semantic",
                "score": 0.95,
                "final_score": 0.95,
                "metadata": {"timestamp": (base - timedelta(hours=2)).timestamp()},
            },
            {
                "text": "Actually, I have decided my favorite language is Rust now.",
                "source": "semantic",
                "score": 0.61,
                "final_score": 0.61,
                "metadata": {"timestamp": base.timestamp()},
            },
        ]

        resolved = engine._resolve_conflicts(ranked)
        self.assertEqual(len(resolved), 1)
        self.assertIn("favorite language is Rust", resolved[0]["text"])
        # Winner inherits strongest confidence from the group so it survives thresholds.
        self.assertAlmostEqual(resolved[0]["final_score"], 0.95, places=6)

    async def test_low_importance_long_term_conflict_keeps_newest(self):
        engine = RetrievalEngine(memory_manager=_FakeMemoryManagerLongTermOnly())

        with patch("kimiko.core.retrieval_engine.FactStore", _FakeFactStore):
            results = await engine.retrieve(
                query="what is my favorite language?",
                user_id="11111111-1111-1111-1111-111111111111",
                db=object(),
                top_k=10,
            )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].source, "long_term")
        self.assertIn("favorite language is Rust", results[0].text)

    async def test_created_timestamp_breaks_equal_timestamp_tie(self):
        engine = RetrievalEngine(memory_manager=_FakeMemoryManager())
        base = datetime(2026, 3, 9, 12, 0, 0, tzinfo=timezone.utc)
        same_ts = base.timestamp()

        ranked = [
            {
                "text": "My favorite programming language is Python.",
                "source": "semantic",
                "score": 0.95,
                "final_score": 0.95,
                "metadata": {
                    "timestamp": same_ts,
                    "created_timestamp": (base - timedelta(days=2)).timestamp(),
                },
            },
            {
                "text": "Actually, I have decided my favorite language is Rust now.",
                "source": "semantic",
                "score": 0.61,
                "final_score": 0.61,
                "metadata": {
                    "timestamp": same_ts,
                    "created_timestamp": base.timestamp(),
                },
            },
        ]

        resolved = engine._resolve_conflicts(ranked)
        self.assertEqual(len(resolved), 1)
        self.assertIn("favorite language is Rust", resolved[0]["text"])


if __name__ == "__main__":
    unittest.main()
