"""Tests for the Lambda Streamable HTTP entrypoint."""

from __future__ import annotations

import json

import pytest

from coinspot_mcp import lambda_handler
from coinspot_mcp.security import mcp_caller_id, token_fingerprint


def test_unauthorized_when_token_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COINSPOT_MCP_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("COINSPOT_MCP_AUTH_TOKENS", raising=False)
    response = lambda_handler.handler({"headers": {}}, None)
    assert response["statusCode"] == 401
    assert "not configured" in json.loads(response["body"])["message"]


def test_unauthorized_without_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COINSPOT_MCP_AUTH_TOKEN", "expected-token-value-32chars!!!!!")
    monkeypatch.delenv("COINSPOT_MCP_AUTH_TOKENS", raising=False)
    response = lambda_handler.handler({"headers": {}}, None)
    assert response["statusCode"] == 401
    body = json.loads(response["body"])
    assert body["status"] == "error"


def test_authorized_token_reaches_mangum(monkeypatch: pytest.MonkeyPatch) -> None:
    token = "expected-token-value-32chars!!!!!"
    monkeypatch.setenv("COINSPOT_MCP_AUTH_TOKEN", token)
    monkeypatch.delenv("COINSPOT_MCP_AUTH_TOKENS", raising=False)

    called = {}

    def fake_mangum(app, lifespan="auto"):
        def _inner(event, context):
            called["ok"] = True
            called["caller"] = mcp_caller_id.get()
            called["path"] = event.get("rawPath")
            return {"statusCode": 200, "body": "ok"}

        return _inner

    monkeypatch.setattr(lambda_handler, "Mangum", fake_mangum)
    monkeypatch.setattr(lambda_handler, "create_asgi_app", lambda: object())

    response = lambda_handler.handler(
        {
            "headers": {"authorization": f"Bearer {token}"},
            "rawPath": "/mcp",
            "requestContext": {"http": {"sourceIp": "203.0.113.10"}},
        },
        None,
    )
    assert response["statusCode"] == 200
    assert called["ok"] is True
    assert called["caller"] == token_fingerprint(token)


def test_transport_security_uses_allowed_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COINSPOT_MCP_ALLOWED_HOSTS", "abc.lambda-url.ap-southeast-2.on.aws")
    settings = lambda_handler._transport_security_settings()
    assert settings.enable_dns_rebinding_protection is True
    assert "abc.lambda-url.ap-southeast-2.on.aws" in settings.allowed_hosts


def test_create_asgi_app_stateless() -> None:
    app = lambda_handler.create_asgi_app()
    assert app is not None
