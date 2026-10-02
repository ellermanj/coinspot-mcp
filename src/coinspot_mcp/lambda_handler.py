"""AWS Lambda entrypoint for Streamable HTTP MCP transport."""

from __future__ import annotations

import json
import os
from typing import Any

from mangum import Mangum
from mcp.server.transport_security import TransportSecuritySettings

from coinspot_mcp.server import apply_tool_exposure_policy, mcp


def _unauthorized(message: str = "Unauthorized") -> dict[str, Any]:
    return {
        "statusCode": 401,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"status": "error", "message": message}),
    }


def _extract_bearer_token(event: dict[str, Any]) -> str | None:
    headers = event.get("headers") or {}
    # API Gateway / Function URL headers may be lower-cased.
    auth = None
    for key, value in headers.items():
        if key.lower() == "authorization":
            auth = value
            break
    if not auth:
        return None
    parts = str(auth).split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return str(auth).strip()


def _check_mcp_auth(event: dict[str, Any]) -> dict[str, Any] | None:
    """Require a bearer token for every MCP connection/request."""
    expected = os.getenv("COINSPOT_MCP_AUTH_TOKEN", "").strip()
    if not expected:
        return _unauthorized(
            "MCP bearer auth is not configured (COINSPOT_MCP_AUTH_TOKEN)."
        )
    provided = _extract_bearer_token(event)
    if not provided or provided != expected:
        return _unauthorized("Missing or invalid bearer token")
    return None


def create_asgi_app():
    """Build a fresh Streamable HTTP ASGI app for this invocation."""
    apply_tool_exposure_policy()
    return mcp.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            # Function URLs use changing hosts; rely on bearer token instead.
            enable_dns_rebinding_protection=False,
        ),
    )


def handler(event: dict[str, Any], context: Any) -> Any:
    """Lambda Function URL / API Gateway handler."""
    auth_error = _check_mcp_auth(event)
    if auth_error is not None:
        return auth_error

    app = create_asgi_app()
    asgi_handler = Mangum(app, lifespan="auto")
    return asgi_handler(event, context)
