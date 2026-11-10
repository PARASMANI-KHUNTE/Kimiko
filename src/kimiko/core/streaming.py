"""Streaming engine — SSE stream management with backpressure and disconnect detection.

Handles client disconnects to avoid wasted GPU cycles (Fix #6 review round 2).

Performance: the previous implementation constructed and validated a Pydantic
``StreamEvent`` for every single token and called ``model_dump_json`` on it.
For a 500-token answer that is 500 model instantiations + serializations in the
hottest loop in the app. We now emit compact JSON directly and cache the
Prometheus child counter outside the loop.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from json.encoder import encode_basestring

import structlog

from kimiko.core.observability import LLM_TOKENS_GENERATED, STREAM_CONNECTIONS

logger = structlog.get_logger(__name__)

_JSON_SEPARATORS = (",", ":")


def _sse(payload: dict) -> dict[str, str]:
    """Return an sse-starlette event mapping with a compact JSON payload.

    ``EventSourceResponse`` adds the ``data:`` prefix and framing, so we yield
    mappings instead of pre-framed strings (which would be double-prefixed).
    """
    return {"data": json.dumps(payload, ensure_ascii=False, separators=_JSON_SEPARATORS)}


class StreamingEngine:
    """Wraps LLM token streams into SSE events with backpressure handling."""

    async def stream_response(
        self,
        token_stream: AsyncIterator[str],
        model: str,
        *,
        check_disconnected: asyncio.Event | None = None,
    ) -> AsyncIterator[dict[str, str]]:
        """Convert an LLM token stream into SSE event mappings.

        Yields mappings like ``{"data": '{"event":"token","data":"..."}'}``;
        ``EventSourceResponse`` performs the actual SSE framing.

        If check_disconnected is set, generation stops early to avoid
        wasting GPU cycles on disconnected clients.
        """
        STREAM_CONNECTIONS.inc()
        token_count = 0
        # Resolve the labeled counter once instead of per token.
        token_counter = LLM_TOKENS_GENERATED.labels(model=model)

        try:
            async for token in token_stream:
                # Backpressure: check if client disconnected
                if check_disconnected is not None and check_disconnected.is_set():
                    logger.info("stream_client_disconnected", tokens_sent=token_count)
                    break

                yield {
                    "data": '{"event":"token","data":'
                    + encode_basestring(token)
                    + "}"
                }
                token_count += 1
                token_counter.inc()

            # Send done event
            yield _sse(
                {
                    "event": "done",
                    "data": "",
                    "metadata": {"total_tokens": token_count},
                }
            )

        except Exception as e:
            logger.error("stream_error", error=str(e), tokens_sent=token_count)
            yield _sse({"event": "error", "data": str(e)})

        finally:
            STREAM_CONNECTIONS.dec()
            logger.debug(
                "stream_complete",
                model=model,
                total_tokens=token_count,
            )
