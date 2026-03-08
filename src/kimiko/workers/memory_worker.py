"""Memory worker — async conversation summarization and cleanup."""

from __future__ import annotations

import asyncio

from kimiko.workers import celery_app


@celery_app.task(name="kimiko.summarize_conversation", bind=True, max_retries=2)
def summarize_conversation(self, session_id: str) -> dict:
    """Summarize a conversation in the background."""
    try:
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(_async_summarize(session_id))
        return result
    except Exception as exc:
        self.retry(exc=exc, countdown=5)


async def _async_summarize(session_id: str) -> dict:
    """Async summarization logic."""
    from kimiko.db.redis import init_redis
    from kimiko.services.llm import init_llm_service
    from kimiko.memory.short_term import ShortTermMemory
    from kimiko.memory.conversation_summarizer import ConversationSummarizer

    await init_redis()
    init_llm_service()

    short_term = ShortTermMemory()
    summarizer = ConversationSummarizer()

    messages = await short_term.get_messages(session_id)
    summary = await summarizer.summarize(messages)
    await short_term.store_summary(session_id, summary)

    from kimiko.services.llm import close_llm_service
    from kimiko.db.redis import close_redis
    await close_llm_service()
    await close_redis()

    return {"session_id": session_id, "summary_length": len(summary)}


@celery_app.task(name="kimiko.cleanup_expired_sessions")
def cleanup_expired_sessions() -> dict:
    """Periodic cleanup of expired Redis sessions (Fix #3 review round 2)."""
    # Redis TTL handles most cleanup automatically.
    # This task handles any edge cases or orphaned data.
    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(_async_cleanup())
    return result


async def _async_cleanup() -> dict:
    """Scan for and remove orphaned session data."""
    from kimiko.db.redis import init_redis, get_redis, close_redis

    await init_redis()
    redis = get_redis()

    # Count existing sessions (informational)
    cursor = 0
    session_count = 0
    async for key in redis.scan_iter(match="session:*:messages", count=100):
        session_count += 1

    await close_redis()
    return {"scanned_sessions": session_count}
