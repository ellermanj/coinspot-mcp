"""Tests for MCP tool registration and safety gates."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from coinspot_mcp.client import PUBLIC_BASE
from coinspot_mcp.server import get_latest_prices, place_buy_order, withdraw_coin


@pytest.mark.asyncio
async def test_tools_are_registered() -> None:
    from coinspot_mcp.server import mcp

    tools = await mcp.list_tools()
    names = {tool.name for tool in tools}
    assert "get_latest_prices" in names
    assert "get_my_balances" in names
    assert "place_buy_order" in names
    assert "withdraw_coin" in names


@pytest.mark.asyncio
@respx.mock
async def test_public_tool_returns_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COINSPOT_API_KEY", raising=False)
    monkeypatch.delenv("COINSPOT_API_SECRET", raising=False)
    respx.get(f"{PUBLIC_BASE}/latest").mock(
        return_value=httpx.Response(
            200, json={"status": "ok", "prices": {"btc": {"last": 100}}}
        )
    )
    raw = await get_latest_prices()
    data = json.loads(raw)
    assert data["status"] == "ok"
    assert data["prices"]["btc"]["last"] == 100


@pytest.mark.asyncio
async def test_trading_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COINSPOT_ALLOW_TRADING", "false")
    raw = await place_buy_order("BTC", 0.01, 100000)
    data = json.loads(raw)
    assert data["status"] == "error"
    assert "COINSPOT_ALLOW_TRADING" in data["message"]


@pytest.mark.asyncio
async def test_withdrawal_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COINSPOT_ALLOW_WITHDRAWALS", "false")
    raw = await withdraw_coin("BTC", 0.01, "bc1qexample")
    data = json.loads(raw)
    assert data["status"] == "error"
    assert "COINSPOT_ALLOW_WITHDRAWALS" in data["message"]
