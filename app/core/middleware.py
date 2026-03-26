"""Request/response middleware for ID propagation, timing, and correlation logging."""

import json
import time
import uuid
from collections.abc import MutableMapping
from typing import Any

import structlog
from starlette.types import ASGIApp, Receive, Scope, Send

logger = structlog.stdlib.get_logger(__name__)


class RequestContextMiddleware:
    """
    Pure ASGI middleware for request ID propagation, timing, and unhandled error safety.

    Reads an incoming X-Request-ID header or generates a new UUID.
    Binds request_id to structlog contextvars so all downstream log
    entries include it, logs the completed request with duration, and
    catches unhandled exceptions that escape the Starlette exception
    handler middleware to return a safe JSON 500.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process ASGI request with ID propagation and timing."""
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        request_id = (
            headers.get(b"x-request-id", b"").decode() or str(uuid.uuid4())
        )

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: MutableMapping[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_headers: list[tuple[bytes, bytes]] = list(
                    message.get("headers", [])
                )
                response_headers.append(
                    (b"x-request-id", request_id.encode())
                )
                message["headers"] = response_headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            logger.exception(
                "unhandled_exception",
                method=scope.get("method", ""),
                path=scope.get("path", ""),
            )
            error_body = json.dumps(
                {"error": "internal_error", "code": "internal_error"}
            ).encode()
            await send({"type": "http.response.start", "status": 500, "headers": [
                (b"content-type", b"application/json"),
                (b"x-request-id", request_id.encode()),
            ]})
            await send({"type": "http.response.body", "body": error_body})
            status_code = 500

        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        logger.info(
            "request_completed",
            method=scope.get("method", ""),
            path=scope.get("path", ""),
            status_code=status_code,
            duration_ms=duration_ms,
        )
