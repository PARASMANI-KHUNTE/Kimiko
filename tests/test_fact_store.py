"""Unit tests for FactStore."""

import uuid
import unittest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timedelta, timezone

from kimiko.memory.fact_store import FactStore
from kimiko.memory.fact_extraction import ExtractedFact
from kimiko.models.database import UserFact


def _result(rows):
    """Build a mock SQLAlchemy result whose ``scalars().all()`` returns rows."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return result


class TestFactStore(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.session = AsyncMock()
        self.store = FactStore(self.session)
        self.user_id = str(uuid.uuid4())

    async def test_store_new_fact(self):
        # One bulk SELECT finds no existing facts.
        self.session.execute.return_value = _result([])

        facts = [ExtractedFact(category="preference", fact="likes pizza", importance=0.9)]
        count = await self.store.store_facts(self.user_id, facts)

        self.assertEqual(count, 1)
        self.session.add.assert_called_once()
        self.session.commit.assert_called_once()

        # Verify the new fact object
        added_fact = self.session.add.call_args[0][0]
        self.assertEqual(added_fact.category, "preference")
        self.assertEqual(added_fact.fact, "likes pizza")
        self.assertEqual(added_fact.importance, 0.9)
        self.assertEqual(added_fact.confidence_score, 1.0)

    async def test_store_facts_deduplicates_within_batch(self):
        self.session.execute.return_value = _result([])

        facts = [
            ExtractedFact(category="preference", fact="likes pizza", importance=0.9),
            ExtractedFact(category="preference", fact="likes pizza", importance=0.7),
        ]
        count = await self.store.store_facts(self.user_id, facts)

        # The duplicate in the incoming batch must not create a second row.
        self.assertEqual(count, 1)
        self.session.add.assert_called_once()

    async def test_reinforce_existing_fact(self):
        existing_fact = UserFact(
            user_id=uuid.UUID(self.user_id),
            category="preference",
            fact="likes pizza",
            confidence_score=0.5,
            verification_count=1,
            importance=0.5,
        )
        # The single bulk SELECT returns the previously stored fact.
        self.session.execute.return_value = _result([existing_fact])

        facts = [ExtractedFact(category="preference", fact="likes pizza", importance=0.9)]
        count = await self.store.store_facts(self.user_id, facts)

        self.assertEqual(count, 0)  # No new fact stored
        self.assertEqual(existing_fact.confidence_score, 0.6)  # 0.5 + 0.1 boost
        self.assertEqual(existing_fact.verification_count, 2)
        self.assertEqual(existing_fact.importance, 0.9)  # Updated to max
        self.session.commit.assert_called_once()
        # Exactly one SELECT for the whole batch (no N+1).
        self.assertEqual(self.session.execute.await_count, 1)

    async def test_apply_decay(self):
        old = datetime.now(timezone.utc) - timedelta(days=10)
        fact = UserFact(
            user_id=uuid.UUID(self.user_id),
            category="preference",
            fact="likes pizza",
            confidence_score=0.8,
            verification_count=1,
            importance=0.5,
        )
        fact.last_seen = old
        self.session.execute.return_value = _result([fact])

        decayed = await self.store.apply_decay(self.user_id)

        self.assertEqual(decayed, 1)
        self.assertLess(fact.confidence_score, 0.8)
        self.session.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
