"""Top-level API router — mounts all v1 endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

from kimiko.api.v1 import agent, audio, chat, documents, memory, models
from kimiko.models.schemas import HealthResponse
from kimiko import __version__

# ── v1 Router ──
v1_router = APIRouter(prefix="/v1")
v1_router.include_router(chat.router)
v1_router.include_router(memory.router)
v1_router.include_router(models.router)
v1_router.include_router(agent.router)
v1_router.include_router(documents.router)
v1_router.include_router(audio.router)

# ── Root Router ──
root_router = APIRouter()


@root_router.get("/health", response_model=HealthResponse, tags=["system"])
async def health_check() -> HealthResponse:
    """System health check."""
    services: dict[str, str] = {}

    # Check Redis
    try:
        from kimiko.db.redis import get_redis
        redis = get_redis()
        await redis.ping()
        services["redis"] = "ok"
    except Exception:
        services["redis"] = "error"

    # Check Ollama
    try:
        from kimiko.services.llm import get_llm_service
        llm = get_llm_service()
        healthy = await llm.health_check()
        services["ollama"] = "ok" if healthy else "error"
    except Exception:
        services["ollama"] = "error"

    # Check Qdrant
    try:
        from kimiko.db.qdrant import get_qdrant
        qdrant = get_qdrant()
        await qdrant.get_collections()
        services["qdrant"] = "ok"
    except Exception:
        services["qdrant"] = "error"

    status = "ok" if all(v == "ok" for v in services.values()) else "degraded"

    return HealthResponse(
        status=status,
        version=__version__,
        services=services,
    )


@root_router.get("/metrics", tags=["system"])
async def metrics() -> Response:
    """Prometheus metrics endpoint."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
