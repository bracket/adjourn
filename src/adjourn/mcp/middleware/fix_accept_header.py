"""Middleware to normalize wildcard ``Accept`` headers for MCP clients."""

from starlette.types import ASGIApp, Receive, Scope, Send


class FixAcceptHeaderMiddleware:
    """Middleware that normalises wildcard Accept headers for MCP clients."""

    def __init__(self, app: ASGIApp) -> None:
        """Initialise with the wrapped ASGI application."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process the request, replacing '*/*' Accept with a concrete value."""
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            if headers.get(b"accept") == b"*/*":
                scope["headers"] = [
                    (b"accept", b"application/json, text/event-stream")
                    if k == b"accept"
                    else (k, v)
                    for k, v in scope["headers"]
                ]
        await self.app(scope, receive, send)
