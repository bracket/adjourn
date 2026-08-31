"""Debug logging middleware for MCP HTTP traffic."""


class DebugMiddleware:
    """Middleware that prints request/response details to stdout for debugging."""

    def __init__(self, app: object) -> None:
        """Initialise with the wrapped ASGI application."""
        self.app = app

    async def __call__(self, scope: dict, receive: object, send: object) -> None:
        """Log request and response details then forward to the application."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "?")
        path = scope.get("path", "?")
        headers = {k.decode(): v.decode() for k, v in scope.get("headers", [])}
        print(f">>> {method} {path}")
        print(f"    Request headers: {headers}")

        request_body = b""

        async def capture_receive() -> dict:
            nonlocal request_body
            message = await receive()
            if message.get("type") == "http.request":
                request_body += message.get("body", b"")
            return message

        status_code = None
        response_headers: dict = {}
        response_body = b""

        async def capture_send(message: dict) -> None:
            nonlocal status_code, response_headers, response_body
            if message.get("type") == "http.response.start":
                status_code = message.get("status")
                response_headers = {
                    k.decode(): v.decode()
                    for k, v in message.get("headers", [])
                }
            elif message.get("type") == "http.response.body":
                response_body += message.get("body", b"")
            await send(message)

        await self.app(scope, capture_receive, capture_send)

        print(f"    Request body: {request_body.decode(errors='replace')}")
        print(f"<<< {status_code}")
        print(f"    Response headers: {response_headers}")
        print(f"    Response body: {response_body.decode(errors='replace')}")
        print()
