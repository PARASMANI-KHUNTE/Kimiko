"""Chat endpoint — POST /v1/chat, POST /v1/chat/stream, GET /v1/chat/history/{session_id}."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession

import structlog
from kimiko.api.deps import get_db_session, get_orchestrator
from kimiko.api.middleware.auth import verify_api_key
from kimiko.api.middleware.rate_limit import rate_limit_middleware
from kimiko.core.orchestrator import RequestOrchestrator
from kimiko.memory.short_term import ShortTermMemory
from kimiko.models.schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/history/{session_id}")
async def get_chat_history(
    session_id: str,
    _auth: dict = Depends(verify_api_key),
) -> dict[str, Any]:
    """Return the conversation history for a given session (from Redis short-term memory)."""
    stm = ShortTermMemory()
    messages = await stm.get_messages(session_id)
    return {
        "session_id": session_id,
        "messages": [
            {
                "role": msg.role.value if hasattr(msg.role, "value") else msg.role,
                "content": msg.content,
                "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
            }
            for msg in messages
        ],
    }



@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    orchestrator: RequestOrchestrator = Depends(get_orchestrator),
    db: AsyncSession = Depends(get_db_session),
    _auth: dict = Depends(verify_api_key),
    _rate: None = Depends(rate_limit_middleware),
) -> ChatResponse:
    """Process a chat request. Returns complete response."""
    # If stream flag is set, redirect to streaming
    if request.stream:
        # Return a hint to use the stream endpoint
        request.stream = False

    request_id = structlog.contextvars.get_contextvars().get("request_id")
    return await orchestrator.process(request, db=db, request_id=request_id)


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    http_request: Request,
    orchestrator: RequestOrchestrator = Depends(get_orchestrator),
    db: AsyncSession = Depends(get_db_session),
    _auth: dict = Depends(verify_api_key),
    _rate: None = Depends(rate_limit_middleware),
) -> EventSourceResponse:
    """Stream a chat response via Server-Sent Events.

    Supports backpressure: stops generation if client disconnects.
    """
    disconnect_event = asyncio.Event()

    async def check_disconnect():
        """Monitor for client disconnect."""
        while not disconnect_event.is_set():
            if await http_request.is_disconnected():
                disconnect_event.set()
                return
            await asyncio.sleep(0.5)

    # Start disconnect monitor
    asyncio.create_task(check_disconnect())

    async def event_generator():
        request_id = structlog.contextvars.get_contextvars().get("request_id")
        async for sse_event in orchestrator.process_stream(
            request, db=db, request_id=request_id, disconnect_event=disconnect_event
        ):
            if disconnect_event.is_set():
                break
            yield sse_event

    return EventSourceResponse(event_generator())
