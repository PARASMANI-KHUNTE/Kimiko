"""Chat endpoint — POST /v1/chat and POST /v1/chat/stream."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession

from kimiko.api.deps import get_db_session, get_orchestrator
from kimiko.api.middleware.auth import verify_api_key
from kimiko.api.middleware.rate_limit import rate_limit_middleware
from kimiko.core.orchestrator import RequestOrchestrator
from kimiko.models.schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])


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

    return await orchestrator.process(request, db=db)


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
        async for sse_event in orchestrator.process_stream(
            request, db=db, disconnect_event=disconnect_event
        ):
            if disconnect_event.is_set():
                break
            yield sse_event

    return EventSourceResponse(event_generator())
