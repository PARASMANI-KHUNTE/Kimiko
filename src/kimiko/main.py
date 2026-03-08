"""Kimiko AI — FastAPI application entry point.

Lifespan manages startup/shutdown of all services:
Redis, PostgreSQL, Qdrant, Ollama, and observability.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from kimiko import __version__
from kimiko.api.middleware.logging import LoggingMiddleware
from kimiko.api.router import root_router, v1_router
from kimiko.config import get_settings
from kimiko.core.observability import init_metrics

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle — initialize and tear down all services."""
    settings = get_settings()
    logger.info("kimiko_starting", version=__version__, env=settings.env.value)

    # ── Startup ──

    # 1. Redis
    from kimiko.db.redis import init_redis
    await init_redis()
    logger.info("redis_connected")

    # 2. PostgreSQL
    from kimiko.db.session import init_db
    await init_db()
    logger.info("postgres_connected")

    # 3. Qdrant
    from kimiko.db.qdrant import init_qdrant
    await init_qdrant()
    logger.info("qdrant_connected")

    # 4. LLM Service (Ollama)
    from kimiko.services.llm import init_llm_service
    init_llm_service()
    logger.info("llm_service_initialized", url=settings.ollama_base_url)

    # 5. Embedding Service
    from kimiko.services.embedding import init_embedding_service
    init_embedding_service()
    logger.info("embedding_service_initialized", model=settings.embedding_model)

    # 6. Metrics
    init_metrics()
    logger.info("metrics_initialized")

    # 7. GPU Monitor (Phase 5 — background telemetry)
    from kimiko.observability.gpu_monitor import gpu_monitor_loop
    gpu_task = asyncio.create_task(gpu_monitor_loop(interval_seconds=5))
    logger.info("gpu_monitor_started")

    logger.info("kimiko_ready", port=settings.api_port)

    yield

    # ── Shutdown ──
    logger.info("kimiko_shutting_down")

    # Cancel GPU monitor
    gpu_task.cancel()
    try:
        await gpu_task
    except asyncio.CancelledError:
        pass

    from kimiko.services.llm import close_llm_service
    from kimiko.services.embedding import close_embedding_service
    from kimiko.db.redis import close_redis
    from kimiko.db.session import close_db
    from kimiko.db.qdrant import close_qdrant

    await close_llm_service()
    await close_embedding_service()
    await close_qdrant()
    await close_redis()
    await close_db()

    logger.info("kimiko_stopped")


def create_app() -> FastAPI:
    """FastAPI application factory."""
    settings = get_settings()

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer() if settings.is_development
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(0),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    app = FastAPI(
        title="Kimiko AI",
        description="Intelligent AI middleware platform",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
    )

    # ── Middleware (order matters: last added = first executed) ──

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.is_development else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Structured logging + metrics
    app.add_middleware(LoggingMiddleware)

    # ── Routes ──
    app.include_router(root_router)
    app.include_router(v1_router)

    return app


# Module-level app for uvicorn
app = create_app()
