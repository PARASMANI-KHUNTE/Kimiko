"""Embedding worker — async embedding generation and Qdrant indexing."""

from __future__ import annotations

from kimiko.workers import celery_app
from kimiko.workers.async_runner import run_async


@celery_app.task(name="kimiko.embed_and_index", bind=True, max_retries=3)
def embed_and_index(
    self,
    text: str,
    user_id: str,
    tags: list[str] | None = None,
    memory_type: str = "general",
    request_id: str | None = None,
) -> dict:
    """Generate embedding and index in Qdrant (runs in background)."""
    try:
        import structlog
        structlog.contextvars.bind_contextvars(request_id=request_id)
        return run_async(
            _async_embed_and_index(text, user_id, tags, memory_type, request_id)
        )
    except Exception as exc:
        self.retry(exc=exc, countdown=2**self.request.retries)


async def _async_embed_and_index(
    text: str,
    user_id: str,
    tags: list[str] | None,
    memory_type: str,
    request_id: str | None = None,
) -> dict:
    """Async embedding + indexing logic.

    Service singletons are initialized idempotently and intentionally left open
    so the worker reuses connection pools across tasks.
    """
    from kimiko.db.qdrant import init_qdrant
    from kimiko.memory.semantic import SemanticMemory
    from kimiko.services.embedding import init_embedding_service

    init_embedding_service()
    await init_qdrant()

    semantic = SemanticMemory()
    point_id = await semantic.index(
        text=text,
        user_id=user_id,
        tags=tags,
        memory_type=memory_type,
        request_id=request_id,
    )

    return {"point_id": point_id, "status": "indexed"}
