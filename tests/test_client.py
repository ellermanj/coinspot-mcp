"""Unit tests for the CoinSpot API client."""

from __future__ import annotations

import hashlib
import hmac
import json

import httpx
import pytest
import respx

from coinspot_mcp.client import (
    FULL_BASE,
    PUBLIC_BASE,
    READONLY_BASE,
    CoinspotClient,
    CoinspotError,
    env_flag,
)


@pytest.mark.asyncio
@respx.mock
async def test_latest_prices_public_get() -> None:
    route = respx.get(f"{PUBLIC_BASE}/latest").mock(
        return_value=httpx.Response(200, json={"status": "ok", "prices": {"btc": {"last": 1}}})
    )
    async with CoinspotClient(api_key="k", api_secret="s") as client:
        data = await client.latest_prices()
    assert route.called
    assert data["prices"]["btc"]["last"] == 1


@pytest.mark.asyncio
@respx.mock
async def test_authenticated_post_signs_compact_json_body() -> None:
    route = respx.post(f"{READONLY_BASE}/my/balances").mock(
        return_value=httpx.Response(200, json={"status": "ok", "balances": []})
    )
    secret = "supersecret"
    async with CoinspotClient(api_key="apikey", api_secret=secret) as client:
        data = await client.my_balances()

    assert data["status"] == "ok"
    assert route.called
    request = route.calls.last.request
    body = request.content.decode("utf-8")
    payload = json.loads(body)
    assert "nonce" in payload
    assert request.headers["key"] == "apikey"
    expected = hmac.new(secret.encode(), body.encode(), hashlib.sha512).hexdigest()
    assert request.headers["sign"] == expected
    # Compact separators are required for CoinSpot HMAC validation.
    assert body == json.dumps(payload, separators=(",", ":"))


@pytest.mark.asyncio
@respx.mock
async def test_api_error_status_raises() -> None:
    respx.post(f"{FULL_BASE}/status").mock(
        return_value=httpx.Response(
            200, json={"status": "error", "message": "Invalid key"}
        )
    )
    async with CoinspotClient(api_key="bad", api_secret="bad") as client:
        with pytest.raises(CoinspotError, match="Invalid key"):
            await client.full_status()


@pytest.mark.asyncio
async def test_missing_credentials_raise() -> None:
    async with CoinspotClient(api_key="", api_secret="") as client:
        with pytest.raises(CoinspotError, match="Missing CoinSpot credentials"):
            await client.my_balances()


@pytest.mark.asyncio
@respx.mock
async def test_nonce_is_monotonic() -> None:
    route = respx.post(url__startswith=READONLY_BASE).mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )
    async with CoinspotClient(api_key="k", api_secret="s") as client:
        await client.ro_status()
        await client.ro_status()
    first = json.loads(route.calls[0].request.content.decode())["nonce"]
    second = json.loads(route.calls[1].request.content.decode())["nonce"]
    assert second > first


def test_env_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COINSPOT_ALLOW_TRADING", raising=False)
    assert env_flag("COINSPOT_ALLOW_TRADING") is False
    monkeypatch.setenv("COINSPOT_ALLOW_TRADING", "true")
    assert env_flag("COINSPOT_ALLOW_TRADING") is True
