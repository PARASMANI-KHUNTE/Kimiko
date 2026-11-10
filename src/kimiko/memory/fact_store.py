"""Fact store — manages persistence, deduplication, and decay of structured knowledge."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from kimiko.models.database import UserFact
from kimiko.memory.fact_extraction import ExtractedFact

logger = structlog.get_logger(__name__)

# Constants for fact life-cycle
DECAY_RATE = 0.05  # 5% confidence drop per update if not reinforced
REINFORCEMENT_BOOST = 0.1  # 10% boost per re-confirmation
MIN_CONFIDENCE = 0.2  # Threshold for fact "forgetting"


class FactStore:
    """Manages UserFact storage and curation."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def store_facts(self, user_id: str, facts: list[ExtractedFact]) -> int:
        """Store extracted facts, handling deduplication and reinforcement.

        All existing facts for the user are fetched in a single query and
        indexed by ``(category, fact)`` so the write path is O(n + m) instead of
        issuing one SELECT per extracted fact (the previous N+1 pattern).
        """
        if not facts:
            return 0

        stored_count = 0
        user_uuid = uuid.UUID(user_id)

        result = await self.session.execute(
            select(UserFact).where(UserFact.user_id == user_uuid)
        )
        index: dict[tuple[str, str], UserFact] = {
            (row.category, row.fact): row for row in result.scalars().all()
        }
        now = datetime.now(timezone.utc)

        for fact in facts:
            key = (fact.category, fact.fact)
            existing = index.get(key)

            if existing is not None:
                # Reinforce existing fact
                existing.confidence_score = min(
                    1.0, existing.confidence_score + REINFORCEMENT_BOOST
                )
                existing.verification_count += 1
                existing.last_seen = now
                existing.importance = max(existing.importance, fact.importance)
                logger.debug("fact_reinforced", category=fact.category, fact=fact.fact)
            else:
                # Store new fact
                new_fact = UserFact(
                    user_id=user_uuid,
                    category=fact.category,
                    fact=fact.fact,
                    importance=fact.importance,
                    confidence_score=1.0,
                    verification_count=1,
                )
                self.session.add(new_fact)
                # Also guard against duplicates within the incoming batch.
                index[key] = new_fact
                stored_count += 1
                logger.debug("fact_stored", category=fact.category, fact=fact.fact)

        await self.session.commit()
        return stored_count

    async def get_facts(
        self, user_id: str, category: str | None = None, limit: int | None = None
    ) -> list[UserFact]:
        """Retrieve active facts for a user, optionally filtered and bounded."""
        user_uuid = uuid.UUID(user_id)

        stmt = (
            select(UserFact)
            .where(
                and_(
                    UserFact.user_id == user_uuid,
                    UserFact.confidence_score >= MIN_CONFIDENCE
                )
            )
            .order_by(
                UserFact.last_seen.desc(),
                UserFact.updated_at.desc(),
                UserFact.created_at.desc(),
            )
        )
        if category:
            stmt = stmt.where(UserFact.category == category)
        if limit is not None:
            stmt = stmt.limit(limit)
        
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def apply_decay(self, user_id: str) -> int:
        """Apply passive decay to all facts for a user.
        
        Uses exponential formula: confidence = confidence * exp(-decay_rate * days_since_seen).
        Enforces a MIN_CONFIDENCE floor so core knowledge is never fully deleted.
        """
        import math
        
        user_uuid = uuid.UUID(user_id)
        
        # Fetch all facts to safely calculate timedelta
        stmt = select(UserFact).where(UserFact.user_id == user_uuid)
        result = await self.session.execute(stmt)
        facts = result.scalars().all()
        
        now = datetime.now(timezone.utc)
        decayed_count = 0
        
        for fact in facts:
            # Ensure timezone awareness
            last_seen = (
                fact.last_seen.replace(tzinfo=timezone.utc)
                if fact.last_seen.tzinfo is None
                else fact.last_seen
            )
            days_since = max(0, (now - last_seen).days)
            
            if days_since > 0:
                new_conf = fact.confidence_score * math.exp(-DECAY_RATE * days_since)
                # Keep floor so facts don't permanently disappear
                fact.confidence_score = max(MIN_CONFIDENCE, new_conf)
                decayed_count += 1
                
        await self.session.commit()
        
        logger.info("fact_decay_applied", user_id=user_id, decayed_count=decayed_count)
        return decayed_count
