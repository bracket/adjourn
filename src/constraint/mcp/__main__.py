"""Entry point for the constraint MCP server.

Run with:
    python -m constraint.mcp

The server uses streamable-HTTP transport and listens on the host and port
configured via the CONSTRAINT_MCP_HOST and CONSTRAINT_MCP_PORT environment
variables (defaults: localhost:8080).  The MCP endpoint is available at /mcp.
"""

import os

import uvicorn
from starlette.middleware.cors import CORSMiddleware

from . import MCP_HOST, MCP_PORT, mcp
from .middleware import (
    DebugMiddleware,
    FixAcceptHeaderMiddleware,
    HealthMiddleware,
    OAuthMiddleware,
)


def _is_truthy(value: str | None) -> bool:
    """Return ``True`` when *value* is one of: ``1``, ``true``, ``yes``, ``on``."""
    return (value or "").lower() in ("1", "true", "yes", "on")


def main() -> None:
    """Build the ASGI application stack and start the uvicorn server."""
    auth_disabled = _is_truthy(os.environ.get("CONSTRAINT_MCP_AUTH_DISABLED"))
    auth0_domain = os.environ.get("CONSTRAINT_MCP_AUTH0_DOMAIN")
    audience = os.environ.get("CONSTRAINT_MCP_AUTH0_AUDIENCE")

    app = mcp.http_app(path="/mcp")
    app = FixAcceptHeaderMiddleware(app)
    app = HealthMiddleware(app)

    if not auth_disabled:
        if auth0_domain is None or not auth0_domain.strip():
            raise ValueError(
                "CONSTRAINT_MCP_AUTH0_DOMAIN must be set unless CONSTRAINT_MCP_AUTH_DISABLED is enabled."
            )
        if audience is None or not audience.strip():
            raise ValueError(
                "CONSTRAINT_MCP_AUTH0_AUDIENCE must be set unless CONSTRAINT_MCP_AUTH_DISABLED is enabled."
            )
        app = OAuthMiddleware(app, auth0_domain=auth0_domain, audience=audience)

    app = CORSMiddleware(
        app,
        allow_origin_regex=".*",
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        allow_credentials=True,
    )

    if _is_truthy(os.environ.get("CONSTRAINT_MCP_DEBUG")):
        app = DebugMiddleware(app)

    uvicorn.run(app, host=MCP_HOST, port=MCP_PORT, ws="none")


if __name__ == "__main__":
    main()
