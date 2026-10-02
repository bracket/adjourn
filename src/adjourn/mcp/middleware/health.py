"""Unauthenticated health endpoint middleware."""

from __future__ import annotations

import json

from starlette.types import ASGIApp, Receive, Scope, Send


class HealthMiddleware:
    """Serve a lightweight unauthenticated health endpoint."""

    def __init__(self, app: ASGIApp) -> None:
        """Initialise with the wrapped ASGI application."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Return ``200 {"status":"ok"}`` for ``GET /health`` and pass through otherwise."""
        if (
            scope.get("type") == "http"
            and scope.get("method") == "GET"
            and scope.get("path") == "/health"
        ):
            body = json.dumps({"status": "ok"}).encode()
            headers = [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ]
            await send({"type": "http.response.start", "status": 200, "headers": headers})
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)
