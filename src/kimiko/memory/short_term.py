"""Short-term memory — Redis-backed conversation store with TTL and summarization.

Keys:
  session:{id}:messages  → JSON list of messages   (TTL: session_ttl_seconds)
  session:{id}:summary   → Compressed summary text  (TTL: summary_ttl_seconds)
"""

from __future__ import annotations

import json
from datetime import datetime

import structlog

from kimiko.config import get_settings
from kimiko.core.observability import ACTIVE_SESSIONS, MEMORY_RETRIEVAL_DURATION
from kimiko.db.redis import get_redis
from kimiko.models.schemas import Message, Role

logger = structlog.get_logger(__name__)


class ShortTermMemory:
    """Redis-backed conversation session store."""

    def _messages_key(self, session_id: str) -> str:
        return f"session:{session_id}:messages"

    def _summary_key(self, session_id: str) -> str:
        return f"session:{session_id}:summary"

    async def add_message(self, session_id: str, message: Message) -> int:
        """Append a message to the session conversation.

        Returns the new list length so callers can decide whether to summarize
        without an extra ``LLEN`` round-trip.

        ``RPUSH`` + ``EXPIRE`` are pipelined into a single network round-trip.
        """
        settings = get_settings()
        redis = get_redis()
        key = self._messages_key(session_id)

        raw = {
            "role": message.role.value if hasattr(message.role, "value") else message.role,
            "content": message.content,
            "images": message.images or [],
            "timestamp": (message.timestamp or datetime.utcnow()).isoformat(),
        }

        pipe = redis.pipeline(transaction=False)
        pipe.rpush(key, json.dumps(raw))
        pipe.expire(key, settings.session_ttl_seconds)
        results = await pipe.execute()
        length = int(results[0])

        # Count each session once, not once per message (the old code leaked the
        # gauge upward on every message).
        if length == 1:
            ACTIVE_SESSIONS.inc()

        logger.debug("short_term_message_added", session_id=session_id, role=message.role)
        return length

    async def get_messages(self, session_id: str) -> list[Message]:
        """Retrieve all messages for a session."""
        redis = get_redis()
        key = self._messages_key(session_id)

        with MEMORY_RETRIEVAL_DURATION.labels(memory_type="short_term").time():
            raw_messages = await redis.lrange(key, 0, -1)

        messages = []
        for raw in raw_messages:
            data = json.loads(raw)
            messages.append(
                Message(
                    role=Role(data["role"]),
                    content=data["content"],
                    images=data.get("images"),
                    timestamp=datetime.fromisoformat(data["timestamp"]) if data.get("timestamp") else None,
                )
            )
        return messages

    async def get_message_count(self, session_id: str) -> int:
        """Get the number of messages in a session."""
        redis = get_redis()
        return await redis.llen(self._messages_key(session_id))

    async def store_summary(self, session_id: str, summary: str) -> None:
        """Store a conversation summary and prune old messages."""
        settings = get_settings()
        redis = get_redis()

        # Store summary + trim in one round-trip. ``LTRIM -keep_recent -1`` is a
        # no-op when the list is already short, so the LLEN probe was redundant.
        key = self._messages_key(session_id)
        keep_recent = 5  # Keep last 5 messages after summarization
        pipe = redis.pipeline(transaction=False)
        pipe.set(
            self._summary_key(session_id),
            summary,
            ex=settings.summary_ttl_seconds,
        )
        pipe.ltrim(key, -keep_recent, -1)
        await pipe.execute()

        logger.info("conversation_summarized", session_id=session_id)

    async def get_summary(self, session_id: str) -> str | None:
        """Retrieve conversation summary if it exists."""
        redis = get_redis()
        return await redis.get(self._summary_key(session_id))

    async def needs_summarization(self, session_id: str, count: int | None = None) -> bool:
        """Check if conversation has exceeded the summarization threshold.

        Pass ``count`` when the caller already knows the list length (e.g. from
        :meth:`add_message`) to avoid an extra Redis round-trip.
        """
        settings = get_settings()
        if count is None:
            count = await self.get_message_count(session_id)
        return count >= settings.conversation_summary_threshold

    async def clear_session(self, session_id: str) -> None:
        """Delete all data for a session."""
        redis = get_redis()
        deleted = await redis.delete(
            self._messages_key(session_id),
            self._summary_key(session_id),
        )
        if deleted:
            ACTIVE_SESSIONS.dec()
        logger.info("session_cleared", session_id=session_id)
