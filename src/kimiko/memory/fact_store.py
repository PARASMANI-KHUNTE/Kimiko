"""Fact store — manages persistence, deduplication, and decay of structured knowledge."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

import structlog
from sqlalchemy import select, update, delete, and_
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
        """Store extracted facts, handling deduplication and reinforcement."""
        stored_count = 0
        user_uuid = uuid.UUID(user_id)
        
        for fact in facts:
            # Check for existing fact
            stmt = select(UserFact).where(
                and_(
                    UserFact.user_id == user_uuid,
                    UserFact.category == fact.category,
                    UserFact.fact == fact.fact
                )
            )
            result = await self.session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                # Reinforce existing fact
                existing.confidence_score = min(1.0, existing.confidence_score + REINFORCEMENT_BOOST)
                existing.verification_count += 1
                existing.last_seen = datetime.now(timezone.utc)
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
                    verification_count=1
                )
                self.session.add(new_fact)
                stored_count += 1
                logger.debug("fact_stored", category=fact.category, fact=fact.fact)

        await self.session.commit()
        return stored_count

    async def get_facts(self, user_id: str, category: str | None = None) -> list[UserFact]:
        """Retrieve high-confidence facts for a user."""
        user_uuid = uuid.UUID(user_id)
        stmt = select(UserFact).where(
            and_(
                UserFact.user_id == user_uuid,
                UserFact.confidence_score >= MIN_CONFIDENCE
            )
        )
        if category:
            stmt = stmt.where(UserFact.category == category)
        
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def apply_decay(self, user_id: str) -> int:
        """Apply passive decay to all facts for a user.
        
        Use this to simulate forgetting non-reinforced knowledge.
        """
        user_uuid = uuid.UUID(user_id)
        # Decay facts
        stmt = (
            update(UserFact)
            .where(UserFact.user_id == user_uuid)
            .values(confidence_score=UserFact.confidence_score - DECAY_RATE)
        )
        await self.session.execute(stmt)
        
        # Cleanup very low confidence facts
        cleanup_stmt = delete(UserFact).where(
            and_(
                UserFact.user_id == user_uuid,
                UserFact.confidence_score < MIN_CONFIDENCE
            )
        )
        res = await self.session.execute(cleanup_stmt)
        await self.session.commit()
        
        deleted_count = res.rowcount
        logger.info("fact_decay_applied", user_id=user_id, forgotten_count=deleted_count)
        return deleted_count
