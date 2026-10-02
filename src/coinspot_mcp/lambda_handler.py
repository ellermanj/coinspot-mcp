"""AWS Lambda entrypoint for Streamable HTTP MCP transport."""

from __future__ import annotations

import json
import os
from typing import Any

from mangum import Mangum
from mcp.server.transport_security import TransportSecuritySettings

from coinspot_mcp.server import apply_tool_exposure_policy, mcp

_SECRET_LOADED = False


def _load_coinspot_secret_into_env() -> None:
    """Load CoinSpot credentials from Secrets Manager when configured.

    Expected secret JSON: {"api_key": "...", "api_secret": "..."}
    """
    global _SECRET_LOADED
    if _SECRET_LOADED:
        return
    secret_arn = os.getenv("COINSPOT_SECRET_ARN", "").strip()
    if not secret_arn:
        _SECRET_LOADED = True
        return
    # Env vars win if already provided (local overrides / tests).
    if os.getenv("COINSPOT_API_KEY") and os.getenv("COINSPOT_API_SECRET"):
        _SECRET_LOADED = True
        return

    import boto3

    client = boto3.client("secretsmanager")
    payload = client.get_secret_value(SecretId=secret_arn)["SecretString"]
    data = json.loads(payload)
    api_key = data.get("api_key") or data.get("COINSPOT_API_KEY")
    api_secret = data.get("api_secret") or data.get("COINSPOT_API_SECRET")
    if not api_key or not api_secret:
        raise RuntimeError(
            "CoinSpot secret must include api_key and api_secret fields."
        )
    os.environ["COINSPOT_API_KEY"] = str(api_key)
    os.environ["COINSPOT_API_SECRET"] = str(api_secret)
    _SECRET_LOADED = True


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
    """Optional shared-token gate for public Function URLs."""
    expected = os.getenv("COINSPOT_MCP_AUTH_TOKEN", "").strip()
    if not expected:
        return None
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

    _load_coinspot_secret_into_env()
    app = create_asgi_app()
    asgi_handler = Mangum(app, lifespan="auto")
    return asgi_handler(event, context)
