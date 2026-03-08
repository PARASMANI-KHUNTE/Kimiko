"""API dependencies — shared FastAPI dependency injection."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from kimiko.api.middleware.auth import verify_api_key
from kimiko.api.middleware.rate_limit import rate_limit_middleware
from kimiko.core.orchestrator import RequestOrchestrator
from kimiko.db.session import get_db

# Shared orchestrator instance
_orchestrator: RequestOrchestrator | None = None


def get_orchestrator() -> RequestOrchestrator:
    """Get the shared orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = RequestOrchestrator()
    return _orchestrator


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session (convenience wrapper)."""
    async for session in get_db():
        yield session
