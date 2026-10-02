"""AWS Lambda entrypoint for Streamable HTTP MCP transport."""

from __future__ import annotations

import json
import os
from typing import Any

from mangum import Mangum
from mcp.server.transport_security import TransportSecuritySettings

from coinspot_mcp.security import (
    audit_event,
    configure_audit_logging,
    configured_mcp_auth_tokens,
    mcp_caller_id,
    mcp_source_ip,
    verify_mcp_bearer_token,
)
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


def _extract_source_ip(event: dict[str, Any]) -> str | None:
    req_ctx = event.get("requestContext") or {}
    http = req_ctx.get("http") or {}
    return http.get("sourceIp") or req_ctx.get("identity", {}).get("sourceIp")


def _check_mcp_auth(event: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """Require a bearer token for every MCP connection/request.

    Returns (error_response_or_none, caller_fingerprint_or_none).
    """
    configure_audit_logging()
    provided = _extract_bearer_token(event)
    if not configured_mcp_auth_tokens():
        return (
            _unauthorized(
                "MCP bearer auth is not configured "
                "(COINSPOT_MCP_AUTH_TOKEN or COINSPOT_MCP_AUTH_TOKENS)."
            ),
            None,
        )
    fingerprint = verify_mcp_bearer_token(provided)
    if fingerprint is None:
        audit_event(
            "mcp_auth",
            outcome="denied",
            params={},
            detail="Missing or invalid bearer token",
        )
        return _unauthorized("Missing or invalid bearer token"), None
    return None, fingerprint


def _transport_security_settings() -> TransportSecuritySettings:
    raw_hosts = os.getenv("COINSPOT_MCP_ALLOWED_HOSTS", "").strip()
    allowed_hosts = [item.strip() for item in raw_hosts.split(",") if item.strip()]
    if allowed_hosts:
        return TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=allowed_hosts,
        )
    # Function URL host is unknown until deploy; set COINSPOT_MCP_ALLOWED_HOSTS after.
    return TransportSecuritySettings(enable_dns_rebinding_protection=False)


def create_asgi_app():
    """Build a fresh Streamable HTTP ASGI app for this invocation."""
    apply_tool_exposure_policy()
    return mcp.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        transport_security=_transport_security_settings(),
    )


def handler(event: dict[str, Any], context: Any) -> Any:
    """Lambda Function URL / API Gateway handler."""
    caller_token = mcp_caller_id.set(None)
    source_token = mcp_source_ip.set(_extract_source_ip(event))
    try:
        auth_error, fingerprint = _check_mcp_auth(event)
        if auth_error is not None:
            return auth_error

        mcp_caller_id.set(fingerprint)
        app = create_asgi_app()
        asgi_handler = Mangum(app, lifespan="auto")
        return asgi_handler(event, context)
    finally:
        mcp_caller_id.reset(caller_token)
        mcp_source_ip.reset(source_token)
