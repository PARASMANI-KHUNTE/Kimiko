"""Memory endpoint — CRUD for persistent memories."""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kimiko.api.deps import get_db_session, get_orchestrator
from kimiko.api.middleware.auth import verify_api_key
from kimiko.core.orchestrator import RequestOrchestrator
from kimiko.db.bootstrap import resolve_user_id
from kimiko.models.database import User
from kimiko.models.schemas import MemoryCreate, MemoryResponse, MemorySearchRequest

router = APIRouter(prefix="/memory", tags=["memory"])


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_memory(
    body: MemoryCreate,
    orchestrator: RequestOrchestrator = Depends(get_orchestrator),
    db: AsyncSession = Depends(get_db_session),
    _auth: dict = Depends(verify_api_key),
) -> dict:
    """Store a new persistent memory."""
    request_id = structlog.contextvars.get_contextvars().get("request_id")
    memory_id = await orchestrator.memory.store_memory(
        db=db,
        user_id=resolve_user_id(body.user_id),
        text=body.text,
        tags=body.tags,
        memory_type=body.memory_type,
        importance=body.importance,
        request_id=request_id,
    )
    return {"id": memory_id, "status": "created"}


async def _resolve_user_uuid(db: AsyncSession, user_id: str) -> uuid.UUID | None:
    """Resolve a user reference to a UUID.

    ``user_id`` may already be a UUID, or it may be a friendly username such as
    the ``"default"`` value used by the CLI and web dashboard. Unknown values
    resolve to ``None`` instead of raising, so listing facts stays a safe,
    read-only operation.
    """
    try:
        return uuid.UUID(str(user_id))
    except (ValueError, AttributeError, TypeError):
        pass

    result = await db.execute(select(User.id).where(User.username == user_id))
    return result.scalar_one_or_none()


@router.get("/facts")
async def get_user_facts(
    user_id: str = "default",
    category: str | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db_session),
    _auth: dict = Depends(verify_api_key),
) -> dict[str, Any]:
    """Return structured long-term facts for a user.

    Declared before ``GET /memory/{user_id}`` so the literal ``facts`` path is
    not swallowed by the dynamic route.
    """
    from kimiko.memory.fact_store import FactStore

    user_uuid = await _resolve_user_uuid(db, user_id)
    if user_uuid is None:
        return {"facts": []}

    facts = await FactStore(db).get_facts(
        str(user_uuid), category=category, limit=limit
    )
    return {
        "facts": [
            {
                "id": str(fact.id),
                "category": fact.category,
                "fact": fact.fact,
                "confidence": fact.confidence_score,
                "importance": fact.importance,
                "verification_count": fact.verification_count,
                "last_seen": fact.last_seen.isoformat() if fact.last_seen else None,
                "created_at": fact.created_at.isoformat() if fact.created_at else None,
                "updated_at": fact.updated_at.isoformat() if fact.updated_at else None,
            }
            for fact in facts
        ]
    }


@router.get("/{user_id}", response_model=list[MemoryResponse])
async def get_memories(
    user_id: str,
    memory_type: str | None = None,
    limit: int = 20,
    orchestrator: RequestOrchestrator = Depends(get_orchestrator),
    db: AsyncSession = Depends(get_db_session),
    _auth: dict = Depends(verify_api_key),
) -> list[dict]:
    """Retrieve memories for a user."""
    user_uuid = await _resolve_user_uuid(db, user_id)
    if user_uuid is None:
        return []
    return await orchestrator.memory.retrieve_memories(
        db=db, user_id=str(user_uuid), limit=limit, memory_type=memory_type
    )


@router.post("/search", response_model=list[dict])
async def search_memories(
    body: MemorySearchRequest,
    orchestrator: RequestOrchestrator = Depends(get_orchestrator),
    _auth: dict = Depends(verify_api_key),
) -> list[dict]:
    """Semantic search across memories."""
    request_id = structlog.contextvars.get_contextvars().get("request_id")
    return await orchestrator.memory.search(
        query=body.query, user_id=body.user_id, top_k=body.top_k, request_id=request_id
    )


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    memory_id: str,
    orchestrator: RequestOrchestrator = Depends(get_orchestrator),
    db: AsyncSession = Depends(get_db_session),
    _auth: dict = Depends(verify_api_key),
) -> None:
    """Delete a memory."""
    deleted = await orchestrator.memory.delete_memory(db=db, memory_id=memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")
