"""Tests for the Lambda Streamable HTTP entrypoint."""

from __future__ import annotations

import json

import pytest

from coinspot_mcp import lambda_handler


def test_unauthorized_without_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COINSPOT_MCP_AUTH_TOKEN", "expected-token")
    response = lambda_handler.handler({"headers": {}}, None)
    assert response["statusCode"] == 401
    body = json.loads(response["body"])
    assert body["status"] == "error"


def test_authorized_token_reaches_mangum(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COINSPOT_MCP_AUTH_TOKEN", "expected-token")
    monkeypatch.delenv("COINSPOT_SECRET_ARN", raising=False)

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


def test_secret_loader_sets_env(monkeypatch: pytest.MonkeyPatch) -> None:
    lambda_handler._SECRET_LOADED = False
    monkeypatch.setenv("COINSPOT_SECRET_ARN", "arn:aws:secretsmanager:ap-southeast-2:123:secret:x")
    monkeypatch.delenv("COINSPOT_API_KEY", raising=False)
    monkeypatch.delenv("COINSPOT_API_SECRET", raising=False)

    class FakeSecrets:
        def get_secret_value(self, SecretId: str):
            assert SecretId.endswith("secret:x")
            return {
                "SecretString": json.dumps(
                    {"api_key": "k123", "api_secret": "s456"}
                )
            }

    class FakeBoto3:
        @staticmethod
        def client(name: str):
            assert name == "secretsmanager"
            return FakeSecrets()

    monkeypatch.setitem(__import__("sys").modules, "boto3", FakeBoto3)
    lambda_handler._load_coinspot_secret_into_env()
    assert lambda_handler.os.environ["COINSPOT_API_KEY"] == "k123"
    assert lambda_handler.os.environ["COINSPOT_API_SECRET"] == "s456"


def test_create_asgi_app_stateless() -> None:
    app = lambda_handler.create_asgi_app()
    assert app is not None
