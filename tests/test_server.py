"""Tests for MCP read-only tools and baseline registration."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from coinspot_mcp.client import PUBLIC_BASE
from coinspot_mcp.server import apply_tool_exposure_policy, get_latest_prices, mcp


@pytest.mark.asyncio
async def test_public_and_readonly_tools_registered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COINSPOT_ALLOW_TRADING", "false")
    monkeypatch.setenv("COINSPOT_ALLOW_WITHDRAWALS", "false")
    apply_tool_exposure_policy()
    names = {tool.name for tool in await mcp.list_tools()}
    assert "get_latest_prices" in names
    assert "get_my_balances" in names
    assert "quote_buy_now" in names


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
