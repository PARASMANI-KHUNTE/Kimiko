"""Long-term memory — PostgreSQL-backed persistent memory with importance scoring."""

from __future__ import annotations

import uuid
from functools import lru_cache

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kimiko.core.observability import MEMORY_RETRIEVAL_DURATION
from kimiko.models.database import Memory, UserActivity

logger = structlog.get_logger(__name__)


@lru_cache(maxsize=1024)
def _as_uuid(user_id: str) -> uuid.UUID:
    """Parse (and memoize) user IDs. UUID parsing is pure and highly repetitive."""
    return uuid.UUID(user_id)


class LongTermMemory:
    """PostgreSQL-backed persistent memory store."""

    async def store(
        self,
        db: AsyncSession,
        user_id: str,
        text: str,
        tags: list[str] | None = None,
        memory_type: str = "general",
        importance: float = 0.5,
        vector_id: str | None = None,
    ) -> Memory:
        """Store a new persistent memory."""
        memory = Memory(
            id=uuid.uuid4(),
            user_id=_as_uuid(user_id),
            text=text,
            tags=tags or [],
            memory_type=memory_type,
            importance=importance,
            vector_id=vector_id,
        )
        db.add(memory)
        await db.flush()

        logger.info(
            "long_term_memory_stored",
            memory_id=str(memory.id),
            user_id=user_id,
            memory_type=memory_type,
        )
        return memory

    async def retrieve(
        self,
        db: AsyncSession,
        user_id: str,
        limit: int = 20,
        memory_type: str | None = None,
    ) -> list[Memory]:
        """Retrieve memories for a user, optionally filtered by type."""
        with MEMORY_RETRIEVAL_DURATION.labels(memory_type="long_term").time():
            stmt = (
                select(Memory)
                .where(Memory.user_id == _as_uuid(user_id))
                .where(Memory.is_active)
                .order_by(Memory.importance.desc(), Memory.created_at.desc())
                .limit(limit)
            )

            if memory_type:
                stmt = stmt.where(Memory.memory_type == memory_type)

            result = await db.execute(stmt)
            return list(result.scalars().all())

    async def get_by_id(self, db: AsyncSession, memory_id: str) -> Memory | None:
        """Get a specific memory by ID."""
        stmt = select(Memory).where(Memory.id == uuid.UUID(memory_id))
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def delete(self, db: AsyncSession, memory_id: str) -> bool:
        """Soft-delete a memory."""
        memory = await self.get_by_id(db, memory_id)
        if memory:
            memory.is_active = False
            await db.flush()
            logger.info("long_term_memory_deleted", memory_id=memory_id)
            return True
        return False

    async def update_importance(
        self, db: AsyncSession, memory_id: str, importance: float
    ) -> bool:
        """Update the importance score of a memory."""
        memory = await self.get_by_id(db, memory_id)
        if memory:
            memory.importance = importance
            await db.flush()
            return True
        return False

    # ── User Activity ──

    async def record_activity(
        self,
        db: AsyncSession,
        user_id: str,
        action: str,
        app_name: str | None = None,
        file_path: str | None = None,
        metadata: dict | None = None,
    ) -> UserActivity:
        """Record a new user activity (telemetry)."""
        import json
        activity = UserActivity(
            user_id=_as_uuid(user_id),
            action=action,
            app_name=app_name,
            file_path=file_path,
            metadata_json=json.dumps(metadata) if metadata else None,
        )
        db.add(activity)
        await db.flush()
        return activity

    async def get_recent_activity(
        self,
        db: AsyncSession,
        user_id: str,
        limit: int = 50,
    ) -> list[UserActivity]:
        """Get recent activities for context."""
        stmt = (
            select(UserActivity)
            .where(UserActivity.user_id == _as_uuid(user_id))
            .order_by(UserActivity.timestamp.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())
