"""Structured request/response logging middleware using structlog."""

from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from kimiko.core.observability import HTTP_REQUEST_DURATION, HTTP_REQUESTS_TOTAL

logger = structlog.get_logger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Logs every request/response with structured fields and Prometheus metrics."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = str(uuid.uuid4())[:8]
        start_time = time.time()

        # Bind request context to structlog
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        logger.info(
            "request_started",
            client=request.client.host if request.client else "unknown",
            query=str(request.query_params) if request.query_params else None,
        )

        try:
            response = await call_next(request)
            duration = time.time() - start_time

            # Prometheus metrics
            HTTP_REQUEST_DURATION.labels(
                method=request.method,
                endpoint=request.url.path,
                status_code=response.status_code,
            ).observe(duration)

            HTTP_REQUESTS_TOTAL.labels(
                method=request.method,
                endpoint=request.url.path,
                status_code=response.status_code,
            ).inc()

            logger.info(
                "request_complete",
                status_code=response.status_code,
                duration=f"{duration:.3f}s",
            )

            # Add request ID header
            response.headers["X-Request-ID"] = request_id
            return response

        except Exception as e:
            duration = time.time() - start_time
            logger.error(
                "request_failed",
                error=str(e),
                duration=f"{duration:.3f}s",
            )
            raise

        finally:
            structlog.contextvars.unbind_contextvars("request_id", "method", "path")
