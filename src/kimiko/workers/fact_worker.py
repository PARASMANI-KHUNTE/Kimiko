"""Fact worker — async fact extraction and structured memory updates."""

from __future__ import annotations

import asyncio
from typing import List

from kimiko.workers import celery_app


@celery_app.task(name="kimiko.extract_user_facts", bind=True, max_retries=2)
def extract_user_facts(
    self, 
    user_id: str, 
    session_id: str, 
    request_id: str | None = None
) -> dict:
    """Extract facts from recent conversation history in the background."""
    try:
        import structlog
        structlog.contextvars.bind_contextvars(request_id=request_id)
        
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(_async_extract_facts(user_id, session_id, request_id))
        return result
    except Exception as exc:
        self.retry(exc=exc, countdown=10)


async def _async_extract_facts(
    user_id: str, 
    session_id: str, 
    request_id: str | None = None
) -> dict:
    """Async fact extraction logic."""
    from kimiko.db.redis import init_redis
    from kimiko.db.session import init_db, get_db
    from kimiko.services.llm import init_llm_service, close_llm_service
    from kimiko.memory.short_term import ShortTermMemory
    from kimiko.memory.fact_extraction import FactExtractionService
    from kimiko.memory.fact_store import FactStore
    from kimiko.models.schemas import Message

    await init_redis()
    await init_db()
    init_llm_service()

    try:
        short_term = ShortTermMemory()
        extractor = FactExtractionService()
        
        # 1. Get recent messages
        messages = await short_term.get_messages(session_id)
        if not messages:
            return {"status": "skipped", "reason": "no_messages"}

        # 2. Extract facts via LLM
        facts = await extractor.extract(messages)
        if not facts:
            return {"status": "skipped", "reason": "no_facts_extracted"}

        # 3. Store in DB
        async for session in get_db():
            store = FactStore(session)
            count = await store.store_facts(user_id, facts)
            return {"status": "success", "facts_extracted": len(facts), "facts_stored": count}

    finally:
        await close_llm_service()
        # Redis and DB sessions are managed via their context or explicitly closed if needed
        from kimiko.db.redis import close_redis
        await close_redis()

    return {"status": "error", "reason": "unexpected_completion"}
