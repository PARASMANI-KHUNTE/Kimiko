"""Async SQLAlchemy session factory and dependency."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from kimiko.config import get_settings

logger = structlog.get_logger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_db() -> AsyncEngine:
    """Initialize the async database engine and session factory (idempotent)."""
    global _engine, _session_factory
    if _engine is not None:
        return _engine
    settings = get_settings()

    _engine = create_async_engine(
        settings.database_url,
        echo=settings.db_echo,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_timeout=30,
    )

    _session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    if settings.auto_create_schema:
        await _bootstrap_schema()

    return _engine


async def _bootstrap_schema() -> None:
    """Create missing tables and seed the local default user (idempotent).

    Alembic remains the source of truth for schema evolution, but a fresh dev
    database starts with no tables at all and migrations are not wired into
    container startup. ``create_all`` is ``checkfirst`` by default, so this is
    a no-op once the schema exists.
    """
    if _engine is None or _session_factory is None:
        return

    from kimiko.db.bootstrap import ensure_default_user
    from kimiko.models import database as db_models

    try:
        async with _engine.begin() as conn:
            await conn.run_sync(db_models.Base.metadata.create_all)
        async with _session_factory() as session:
            await ensure_default_user(session)
        logger.info("schema_bootstrapped")
    except Exception as exc:  # pragma: no cover - depends on live database
        # Never block API startup: the health endpoint reports datastore status
        # and callers get a clear error if the schema is genuinely unusable.
        logger.warning("schema_bootstrap_failed", error=str(exc))


async def close_db() -> None:
    """Dispose the database engine."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Transactional session scope usable outside FastAPI (e.g. Celery)."""
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    async with session_scope() as session:
        yield session


def get_engine() -> AsyncEngine:
    """Get the raw engine for migrations etc."""
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _engine
