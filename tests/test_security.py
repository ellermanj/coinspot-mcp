"""Tests for Salt-aligned security guards and per-user credentials."""

from __future__ import annotations

import json
import logging

import httpx
import pytest
import respx

from coinspot_mcp.client import FULL_BASE, CoinspotClient
from coinspot_mcp.security import (
    enforce_order_amount,
    enforce_withdraw_address,
    enforce_withdraw_amount,
    require_destructive_confirmation,
    sanitize_error_message,
)
from coinspot_mcp.server import (
    apply_tool_exposure_policy,
    get_my_balances,
    mcp,
    place_buy_order,
    withdraw_coin,
)


@pytest.mark.asyncio
async def test_privileged_tools_hidden_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COINSPOT_ALLOW_TRADING", "false")
    monkeypatch.setenv("COINSPOT_ALLOW_WITHDRAWALS", "false")
    apply_tool_exposure_policy()
    names = {tool.name for tool in await mcp.list_tools()}
    assert "get_latest_prices" in names
    assert "get_my_balances" in names
    assert "place_buy_order" not in names
    assert "withdraw_coin" not in names


@pytest.mark.asyncio
async def test_privileged_tools_registered_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COINSPOT_ALLOW_TRADING", "true")
    monkeypatch.setenv("COINSPOT_ALLOW_WITHDRAWALS", "true")
    apply_tool_exposure_policy()
    names = {tool.name for tool in await mcp.list_tools()}
    assert "place_buy_order" in names
    assert "withdraw_coin" in names
    assert "get_coin_withdraw_details" in names


@pytest.mark.asyncio
async def test_authenticated_tool_requires_user_credentials() -> None:
    raw = await get_my_balances("", "")
    data = json.loads(raw)
    assert data["status"] == "error"
    assert "coinspot_api_key" in data["message"]


@pytest.mark.asyncio
async def test_order_amount_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COINSPOT_ALLOW_TRADING", "true")
    monkeypatch.setenv("COINSPOT_MAX_ORDER_AMOUNT", "0.01")
    monkeypatch.delenv("COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN", raising=False)
    raw = await place_buy_order("k", "s", "BTC", 1.0, 100000)
    data = json.loads(raw)
    assert data["status"] == "error"
    assert "COINSPOT_MAX_ORDER_AMOUNT" in data["message"]


@pytest.mark.asyncio
async def test_confirm_token_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COINSPOT_ALLOW_TRADING", "true")
    monkeypatch.setenv("COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN", "correct-token")
    monkeypatch.delenv("COINSPOT_MAX_ORDER_AMOUNT", raising=False)
    denied = json.loads(await place_buy_order("k", "s", "BTC", 0.01, 100000))
    assert denied["status"] == "error"
    assert "confirm_token" in denied["message"]


@pytest.mark.asyncio
@respx.mock
async def test_confirm_token_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COINSPOT_ALLOW_TRADING", "true")
    monkeypatch.setenv("COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN", "correct-token")
    monkeypatch.delenv("COINSPOT_MAX_ORDER_AMOUNT", raising=False)
    respx.post(f"{FULL_BASE}/my/buy").mock(
        return_value=httpx.Response(200, json={"status": "ok", "id": "1"})
    )
    raw = await place_buy_order(
        "k", "s", "BTC", 0.01, 100000, confirm_token="correct-token"
    )
    assert json.loads(raw)["status"] == "ok"


@pytest.mark.asyncio
async def test_withdraw_address_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COINSPOT_ALLOW_WITHDRAWALS", "true")
    monkeypatch.setenv("COINSPOT_WITHDRAW_ADDRESS_ALLOWLIST", "bc1qallowed")
    monkeypatch.delenv("COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN", raising=False)
    monkeypatch.delenv("COINSPOT_MAX_WITHDRAW_AMOUNT", raising=False)
    raw = await withdraw_coin("k", "s", "BTC", 0.01, "bc1qevil")
    data = json.loads(raw)
    assert data["status"] == "error"
    assert "ALLOWLIST" in data["message"]


@pytest.mark.asyncio
@respx.mock
async def test_withdraw_forces_email_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COINSPOT_ALLOW_WITHDRAWALS", "true")
    monkeypatch.setenv("COINSPOT_WITHDRAW_ADDRESS_ALLOWLIST", "bc1qallowed")
    monkeypatch.delenv("COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN", raising=False)
    monkeypatch.delenv("COINSPOT_MAX_WITHDRAW_AMOUNT", raising=False)
    route = respx.post(f"{FULL_BASE}/my/coin/withdraw/send").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )
    raw = await withdraw_coin("k", "s", "BTC", 0.01, "bc1qallowed")
    assert json.loads(raw)["status"] == "ok"
    body = json.loads(route.calls.last.request.content.decode())
    assert body["emailconfirm"] == "YES"


@pytest.mark.asyncio
@respx.mock
async def test_errors_do_not_include_raw_payload() -> None:
    respx.post(f"{FULL_BASE}/status").mock(
        return_value=httpx.Response(500, text="secret-stack-trace api_secret=abc")
    )
    async with CoinspotClient(api_key="k", api_secret="s") as client:
        with pytest.raises(Exception) as excinfo:
            await client.full_status()
    assert "secret-stack-trace" not in str(excinfo.value)
    assert getattr(excinfo.value, "payload", None) is None


def test_sanitize_error_message() -> None:
    assert "REDACTED" in sanitize_error_message("api_secret=supersecret value")


def test_enforce_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COINSPOT_MAX_ORDER_AMOUNT", "1")
    enforce_order_amount(0.5)
    with pytest.raises(Exception, match="COINSPOT_MAX_ORDER_AMOUNT"):
        enforce_order_amount(2)

    monkeypatch.setenv("COINSPOT_MAX_WITHDRAW_AMOUNT", "1")
    enforce_withdraw_amount(0.5)
    with pytest.raises(Exception, match="COINSPOT_MAX_WITHDRAW_AMOUNT"):
        enforce_withdraw_amount(2)

    monkeypatch.setenv("COINSPOT_WITHDRAW_ADDRESS_ALLOWLIST", "addr1,addr2")
    enforce_withdraw_address("addr1")
    with pytest.raises(Exception, match="ALLOWLIST"):
        enforce_withdraw_address("addr3")

    monkeypatch.setenv("COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN", "tok")
    with pytest.raises(Exception, match="confirm_token"):
        require_destructive_confirmation(None)
    require_destructive_confirmation("tok")


@pytest.mark.asyncio
async def test_audit_log_redacts_user_credentials(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("COINSPOT_ALLOW_TRADING", "false")
    with caplog.at_level(logging.INFO, logger="coinspot_mcp.audit"):
        await place_buy_order("super-secret-key", "super-secret-secret", "BTC", 0.01, 1)
    joined = " ".join(record.message for record in caplog.records)
    assert "tool=place_buy_order" in joined
    assert "outcome=denied" in joined
    assert "super-secret-key" not in joined
    assert "super-secret-secret" not in joined
    assert "[REDACTED]" in joined
