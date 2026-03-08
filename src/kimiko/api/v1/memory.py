"""Memory endpoint — CRUD for persistent memories."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from kimiko.api.deps import get_db_session, get_orchestrator
from kimiko.api.middleware.auth import verify_api_key
from kimiko.core.orchestrator import RequestOrchestrator
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
    memory_id = await orchestrator.memory.store_memory(
        db=db,
        user_id=body.user_id,
        text=body.text,
        tags=body.tags,
        memory_type=body.memory_type,
        importance=body.importance,
    )
    return {"id": memory_id, "status": "created"}


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
    return await orchestrator.memory.retrieve_memories(
        db=db, user_id=user_id, limit=limit, memory_type=memory_type
    )


@router.post("/search", response_model=list[dict])
async def search_memories(
    body: MemorySearchRequest,
    orchestrator: RequestOrchestrator = Depends(get_orchestrator),
    _auth: dict = Depends(verify_api_key),
) -> list[dict]:
    """Semantic search across memories."""
    return await orchestrator.memory.search(
        query=body.query, user_id=body.user_id, top_k=body.top_k
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
