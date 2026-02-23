from __future__ import annotations

import logging
from time import perf_counter

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from src.ops.events import (
    CORRELATION_ID_HEADER,
    new_correlation_id,
    reset_correlation_id,
    set_correlation_id,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        correlation_id = request.headers.get(CORRELATION_ID_HEADER) or new_correlation_id()
        token = set_correlation_id(correlation_id)
        request.state.correlation_id = correlation_id
        start = perf_counter()

        try:
            response: Response = await call_next(request)
        except Exception:
            duration_ms = int((perf_counter() - start) * 1000)
            logger.exception(
                "Request failed %s %s",
                request.method,
                request.url.path,
                extra={
                    "event_type": "api.request.failed",
                    "correlation_id": correlation_id,
                    "ops_payload": {
                        "method": request.method,
                        "path": request.url.path,
                        "duration_ms": duration_ms,
                    },
                },
            )
            raise
        else:
            duration_ms = int((perf_counter() - start) * 1000)
            response.headers["X-Request-Id"] = correlation_id
            logger.info(
                "Request completed %s %s (%dms)",
                request.method,
                request.url.path,
                duration_ms,
                extra={
                    "event_type": "api.request.completed",
                    "correlation_id": correlation_id,
                    "ops_payload": {
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": response.status_code,
                        "duration_ms": duration_ms,
                    },
                },
            )
            return response
        finally:
            reset_correlation_id(token)
