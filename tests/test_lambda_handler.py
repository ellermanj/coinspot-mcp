"""Tests for the Lambda Streamable HTTP entrypoint."""

from __future__ import annotations

import json

import pytest

from coinspot_mcp import lambda_handler


def test_unauthorized_when_token_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COINSPOT_MCP_AUTH_TOKEN", raising=False)
    response = lambda_handler.handler({"headers": {}}, None)
    assert response["statusCode"] == 401
    assert "not configured" in json.loads(response["body"])["message"]


def test_unauthorized_without_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COINSPOT_MCP_AUTH_TOKEN", "expected-token")
    response = lambda_handler.handler({"headers": {}}, None)
    assert response["statusCode"] == 401
    body = json.loads(response["body"])
    assert body["status"] == "error"


def test_authorized_token_reaches_mangum(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COINSPOT_MCP_AUTH_TOKEN", "expected-token")

    called = {}

    def fake_mangum(app, lifespan="auto"):
        def _inner(event, context):
            called["ok"] = True
            called["path"] = event.get("rawPath")
            return {"statusCode": 200, "body": "ok"}

        return _inner

    monkeypatch.setattr(lambda_handler, "Mangum", fake_mangum)
    monkeypatch.setattr(lambda_handler, "create_asgi_app", lambda: object())

    response = lambda_handler.handler(
        {
            "headers": {"authorization": "Bearer expected-token"},
            "rawPath": "/mcp",
        },
        None,
    )
    assert response["statusCode"] == 200
    assert called["ok"] is True


def test_create_asgi_app_stateless() -> None:
    app = lambda_handler.create_asgi_app()
    assert app is not None
