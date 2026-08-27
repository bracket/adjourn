"""OAuth 2.1 bearer-token middleware for MCP."""

from __future__ import annotations

import json
import os
from urllib.parse import urlsplit, urlunsplit

import jwt


def _default_host() -> str:
    return os.environ.get("CONSTRAINT_MCP_HOST", "localhost")


def _default_port() -> str:
    return os.environ.get("CONSTRAINT_MCP_PORT", "8080")


class OAuthMiddleware:
    """Validate OAuth 2.1 bearer tokens for MCP requests."""

    def __init__(self, app: object, auth0_domain: str, audience: str) -> None:
        """Initialise middleware with Auth0 domain, audience, and JWKS client."""
        self.app = app
        normalized_domain = auth0_domain.removeprefix("https://").removeprefix("http://").rstrip("/")
        self._issuer = f"https://{normalized_domain}/"
        self._audience = audience
        self._resource = audience
        self._authorization_server = self._issuer
        self._jwks_client = jwt.PyJWKClient(
            f"{self._issuer}.well-known/jwks.json",
            cache_keys=True,
        )

    async def __call__(self, scope: dict, receive: object, send: object) -> None:
        """Serve metadata and enforce bearer-token validation for protected paths."""
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = str(scope.get("method", "")).upper()
        if path.startswith("/.well-known/"):
            if path == "/.well-known/oauth-protected-resource" and method == "GET":
                await self._send_json(
                    send,
                    status=200,
                    payload={
                        "resource": self._metadata_resource(scope),
                        "authorization_servers": [self._authorization_server],
                    },
                )
                return
            await self.app(scope, receive, send)
            return

        if method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        if path == "/health":
            await self.app(scope, receive, send)
            return

        authorization = self._header_value(scope, b"authorization")
        token = self._extract_bearer_token(authorization)
        if token is None:
            await self._send_unauthorized(
                scope,
                send,
                reason="Missing bearer token",
            )
            return

        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
            )
        except jwt.PyJWTError as exc:
            await self._send_unauthorized(
                scope,
                send,
                reason=f"Invalid bearer token: {exc}",
            )
            return

        await self.app(scope, receive, send)

    async def _send_json(self, send: object, status: int, payload: dict) -> None:
        """Send a JSON response through ASGI ``send``."""
        body = json.dumps(payload).encode()
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ]
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})

    async def _send_unauthorized(self, scope: dict, send: object, reason: str) -> None:
        """Send a 401 response with the MCP-required WWW-Authenticate header."""
        metadata_url = self._resource_metadata_url(scope)
        authenticate = (
            f'Bearer realm="constraint", resource_metadata="{metadata_url}"'
        ).encode()
        payload = {"error": "unauthorized", "error_description": reason}
        body = json.dumps(payload).encode()
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
            (b"www-authenticate", authenticate),
        ]
        await send({"type": "http.response.start", "status": 401, "headers": headers})
        await send({"type": "http.response.body", "body": body})

    def _resource_metadata_url(self, scope: dict) -> str:
        """Return the absolute URL for the protected-resource metadata endpoint."""
        return f"{self._base_url(scope)}/.well-known/oauth-protected-resource"

    def _metadata_resource(self, scope: dict) -> str:
        """Return the resource value for protected-resource metadata responses."""
        if "://" not in self._resource:
            return self._resource
        forwarded_proto = self._header_value(scope, b"x-forwarded-proto")
        if not forwarded_proto:
            return self._resource

        split = urlsplit(self._resource)
        return urlunsplit(
            (
                self._request_scheme(scope),
                split.netloc,
                split.path,
                split.query,
                split.fragment,
            )
        )

    def _base_url(self, scope: dict) -> str:
        """Return the request base URL, honoring reverse-proxy protocol headers."""
        configured = os.environ.get("CONSTRAINT_MCP_URL")
        if configured:
            split = urlsplit(configured.rstrip("/"))
            if split.netloc:
                return urlunsplit(
                    (
                        self._request_scheme(scope),
                        split.netloc,
                        split.path,
                        split.query,
                        split.fragment,
                    )
                ).rstrip("/")

        host = self._header_value(scope, b"host") or f"{_default_host()}:{_default_port()}"
        return f"{self._request_scheme(scope)}://{host}"

    def _request_scheme(self, scope: dict) -> str:
        """Return request scheme, preferring ``X-Forwarded-Proto`` when present."""
        forwarded_proto = self._header_value(scope, b"x-forwarded-proto")
        if forwarded_proto:
            proto = forwarded_proto.split(",")[0].strip().lower()
            if proto in {"http", "https"}:
                return proto
        scope_scheme = str(scope.get("scheme", "http")).lower()
        return scope_scheme if scope_scheme in {"http", "https"} else "http"

    @staticmethod
    def _header_value(scope: dict, key: bytes) -> str | None:
        """Extract a decoded HTTP header value from ASGI scope."""
        for header_key, header_value in scope.get("headers", []):
            if header_key == key:
                return header_value.decode()
        return None

    @staticmethod
    def _extract_bearer_token(authorization: str | None) -> str | None:
        """Extract bearer token from ``Authorization`` header value."""
        if authorization is None:
            return None
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return None
        return token
