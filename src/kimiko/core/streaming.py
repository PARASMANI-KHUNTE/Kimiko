"""Streaming engine — SSE stream management with backpressure and disconnect detection.

Handles client disconnects to avoid wasted GPU cycles (Fix #6 review round 2).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import structlog

from kimiko.core.observability import LLM_TOKENS_GENERATED, STREAM_CONNECTIONS
from kimiko.models.schemas import StreamEvent, StreamEventType

logger = structlog.get_logger(__name__)


class StreamingEngine:
    """Wraps LLM token streams into SSE events with backpressure handling."""

    async def stream_response(
        self,
        token_stream: AsyncIterator[str],
        model: str,
        *,
        check_disconnected: asyncio.Event | None = None,
    ) -> AsyncIterator[str]:
        """Convert an LLM token stream into SSE-formatted events.

        Yields SSE-formatted strings: `data: {...}\n\n`

        If check_disconnected is set, generation stops early to avoid
        wasting GPU cycles on disconnected clients.
        """
        STREAM_CONNECTIONS.inc()
        token_count = 0

        try:
            async for token in token_stream:
                # Backpressure: check if client disconnected
                if check_disconnected and check_disconnected.is_set():
                    logger.info("stream_client_disconnected", tokens_sent=token_count)
                    break

                event = StreamEvent(
                    event=StreamEventType.TOKEN,
                    data=token,
                )
                yield f"data: {event.model_dump_json()}\n\n"
                token_count += 1
                LLM_TOKENS_GENERATED.labels(model=model).inc()

            # Send done event
            done_event = StreamEvent(
                event=StreamEventType.DONE,
                data="",
                metadata={"total_tokens": token_count},
            )
            yield f"data: {done_event.model_dump_json()}\n\n"

        except Exception as e:
            logger.error("stream_error", error=str(e), tokens_sent=token_count)
            error_event = StreamEvent(
                event=StreamEventType.ERROR,
                data=str(e),
            )
            yield f"data: {error_event.model_dump_json()}\n\n"

        finally:
            STREAM_CONNECTIONS.dec()
            logger.debug(
                "stream_complete",
                model=model,
                total_tokens=token_count,
            )
