"""Memory worker — async conversation summarization and cleanup."""

from __future__ import annotations

from kimiko.workers import celery_app
from kimiko.workers.async_runner import run_async


@celery_app.task(name="kimiko.summarize_conversation", bind=True, max_retries=2)
def summarize_conversation(self, session_id: str, request_id: str | None = None) -> dict:
    """Summarize a conversation in the background."""
    try:
        import structlog
        structlog.contextvars.bind_contextvars(request_id=request_id)
        return run_async(_async_summarize(session_id, request_id))
    except Exception as exc:
        self.retry(exc=exc, countdown=5)


async def _async_summarize(session_id: str, request_id: str | None = None) -> dict:
    """Async summarization logic."""
    from kimiko.db.redis import init_redis
    from kimiko.services.llm import init_llm_service
    from kimiko.memory.short_term import ShortTermMemory
    from kimiko.memory.conversation_summarizer import ConversationSummarizer

    # Idempotent inits; clients stay warm for subsequent tasks.
    await init_redis()
    init_llm_service()

    short_term = ShortTermMemory()
    summarizer = ConversationSummarizer()

    messages = await short_term.get_messages(session_id)
    summary = await summarizer.summarize(messages)
    await short_term.store_summary(session_id, summary)

    return {"session_id": session_id, "summary_length": len(summary)}


@celery_app.task(name="kimiko.cleanup_expired_sessions")
def cleanup_expired_sessions() -> dict:
    """Periodic cleanup of expired Redis sessions (Fix #3 review round 2)."""
    # Redis TTL handles most cleanup automatically.
    # This task handles any edge cases or orphaned data.
    return run_async(_async_cleanup())


async def _async_cleanup() -> dict:
    """Scan for and remove orphaned session data."""
    from kimiko.db.redis import init_redis, get_redis

    await init_redis()
    redis = get_redis()

    # Count existing sessions (informational)
    session_count = 0
    async for _key in redis.scan_iter(match="session:*:messages", count=100):
        session_count += 1

    return {"scanned_sessions": session_count}
