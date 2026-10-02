"""CoinSpot MCP server exposing public, read-only, and trading tools."""

from __future__ import annotations

import json
from collections.abc import Awaitable
from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from coinspot_mcp.client import CoinspotClient, CoinspotError
from coinspot_mcp.security import (
    audit_event,
    enforce_order_amount,
    enforce_withdraw_address,
    enforce_withdraw_amount,
    require_destructive_confirmation,
    sanitize_error_message,
    trading_enabled,
    withdrawals_enabled,
)

mcp = MCPServer(
    name="coinspot",
    title="CoinSpot Australia",
    description="Access the CoinSpot Australia cryptocurrency exchange API (v2).",
    instructions=(
        "Use public tools for market prices and order books without credentials. "
        "Use read-only tools for balances and account history when COINSPOT_API_KEY "
        "and COINSPOT_API_SECRET are configured. Trading and withdrawal tools are only "
        "registered when COINSPOT_ALLOW_TRADING / COINSPOT_ALLOW_WITHDRAWALS are enabled, "
        "and may require COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN plus amount/address limits."
    ),
    website_url="https://www.coinspot.com.au/v2/api",
    version="0.2.0",
)

_READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=True)
_DESTRUCTIVE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=True,
    open_world_hint=True,
)

TRADING_TOOL_NAMES = (
    "place_buy_order",
    "edit_buy_order",
    "place_buy_now",
    "place_sell_order",
    "edit_sell_order",
    "place_sell_now",
    "place_swap_now",
    "cancel_buy_order",
    "cancel_all_buy_orders",
    "cancel_sell_order",
    "cancel_all_sell_orders",
)

WITHDRAWAL_TOOL_NAMES = (
    "get_coin_withdraw_details",
    "withdraw_coin",
)


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)


async def _call(
    tool_name: str,
    coro: Awaitable[Any],
    *,
    params: dict[str, Any] | None = None,
) -> str:
    try:
        result = await coro
    except CoinspotError as exc:
        message = sanitize_error_message(str(exc))
        audit_event(tool_name, outcome="error", params=params, detail=message)
        return _json({"status": "error", "message": message})
    except Exception:
        audit_event(
            tool_name,
            outcome="error",
            params=params,
            detail="Unexpected internal error",
        )
        return _json(
            {
                "status": "error",
                "message": "Unexpected internal error while calling CoinSpot.",
            }
        )

    audit_event(tool_name, outcome="ok", params=params)
    return _json(result)


def get_client() -> CoinspotClient:
    return CoinspotClient()


def _require_trading() -> None:
    if not trading_enabled():
        raise CoinspotError("Trading tools are disabled on this server.")


def _require_withdrawals() -> None:
    if not withdrawals_enabled():
        raise CoinspotError("Withdrawal tools are disabled on this server.")


# ---- Public tools -------------------------------------------------------


@mcp.tool(annotations=_READ_ONLY)
async def get_latest_prices() -> str:
    """Get latest buy/ask/last prices for all CoinSpot markets."""
    async with get_client() as client:
        return await _call("get_latest_prices", client.latest_prices())


@mcp.tool(annotations=_READ_ONLY)
async def get_latest_coin_price(cointype: str, markettype: str | None = None) -> str:
    """Get latest prices for a coin, optionally against a market (e.g. USDT).

    Args:
        cointype: Coin ticker such as BTC, ETH, or DOGE.
        markettype: Optional market ticker such as USDT. Defaults to AUD.
    """
    params = {"cointype": cointype, "markettype": markettype}
    async with get_client() as client:
        return await _call(
            "get_latest_coin_price",
            client.latest_coin_price(cointype, markettype),
            params=params,
        )


@mcp.tool(annotations=_READ_ONLY)
async def get_buy_price(cointype: str, markettype: str | None = None) -> str:
    """Get the latest buy price for a coin.

    Args:
        cointype: Coin ticker such as BTC.
        markettype: Optional market ticker such as USDT.
    """
    params = {"cointype": cointype, "markettype": markettype}
    async with get_client() as client:
        return await _call(
            "get_buy_price", client.buy_price(cointype, markettype), params=params
        )


@mcp.tool(annotations=_READ_ONLY)
async def get_sell_price(cointype: str, markettype: str | None = None) -> str:
    """Get the latest sell price for a coin.

    Args:
        cointype: Coin ticker such as BTC.
        markettype: Optional market ticker such as USDT.
    """
    params = {"cointype": cointype, "markettype": markettype}
    async with get_client() as client:
        return await _call(
            "get_sell_price", client.sell_price(cointype, markettype), params=params
        )


@mcp.tool(annotations=_READ_ONLY)
async def get_open_orders(cointype: str, markettype: str | None = None) -> str:
    """List public open buy/sell orders for a coin market.

    Args:
        cointype: Coin ticker such as BTC.
        markettype: Optional market ticker such as USDT.
    """
    params = {"cointype": cointype, "markettype": markettype}
    async with get_client() as client:
        return await _call(
            "get_open_orders", client.open_orders(cointype, markettype), params=params
        )


@mcp.tool(annotations=_READ_ONLY)
async def get_completed_orders(cointype: str, markettype: str | None = None) -> str:
    """List recent completed public buy/sell orders for a coin market.

    Args:
        cointype: Coin ticker such as BTC.
        markettype: Optional market ticker such as USDT.
    """
    params = {"cointype": cointype, "markettype": markettype}
    async with get_client() as client:
        return await _call(
            "get_completed_orders",
            client.completed_orders(cointype, markettype),
            params=params,
        )


@mcp.tool(annotations=_READ_ONLY)
async def get_completed_orders_summary(
    cointype: str, markettype: str | None = None
) -> str:
    """List recent completed public orders as a combined summary.

    Args:
        cointype: Coin ticker such as BTC.
        markettype: Optional market ticker such as USDT.
    """
    params = {"cointype": cointype, "markettype": markettype}
    async with get_client() as client:
        return await _call(
            "get_completed_orders_summary",
            client.completed_orders_summary(cointype, markettype),
            params=params,
        )


# ---- Read-only account tools --------------------------------------------


@mcp.tool(annotations=_READ_ONLY)
async def check_readonly_status() -> str:
    """Check that the configured read-only/full API credentials are working."""
    async with get_client() as client:
        return await _call("check_readonly_status", client.ro_status())


@mcp.tool(annotations=_READ_ONLY)
async def get_my_balances() -> str:
    """List all coin balances with AUD value and rate."""
    async with get_client() as client:
        return await _call("get_my_balances", client.my_balances())


@mcp.tool(annotations=_READ_ONLY)
async def get_my_balance(cointype: str, available: bool = False) -> str:
    """Get balance details for a single coin.

    Args:
        cointype: Coin ticker such as BTC or AUD.
        available: If true, also return the available (unlocked) balance.
    """
    params = {"cointype": cointype, "available": available}
    async with get_client() as client:
        return await _call(
            "get_my_balance",
            client.my_balance(cointype, available=available),
            params=params,
        )


@mcp.tool(annotations=_READ_ONLY)
async def get_my_open_market_orders(
    cointype: str | None = None, markettype: str | None = None
) -> str:
    """List your open market orders.

    Args:
        cointype: Optional coin ticker filter.
        markettype: Optional market ticker filter such as AUD or USDT.
    """
    params = {"cointype": cointype, "markettype": markettype}
    async with get_client() as client:
        return await _call(
            "get_my_open_market_orders",
            client.my_open_market_orders(cointype, markettype),
            params=params,
        )


@mcp.tool(annotations=_READ_ONLY)
async def get_my_open_limit_orders(cointype: str | None = None) -> str:
    """List your open limit/stop orders.

    Args:
        cointype: Optional coin ticker filter.
    """
    params = {"cointype": cointype}
    async with get_client() as client:
        return await _call(
            "get_my_open_limit_orders",
            client.my_open_limit_orders(cointype),
            params=params,
        )


@mcp.tool(annotations=_READ_ONLY)
async def get_my_order_history(
    cointype: str | None = None,
    markettype: str | None = None,
    startdate: str | None = None,
    enddate: str | None = None,
    limit: int | None = None,
) -> str:
    """List your completed order history.

    Args:
        cointype: Optional coin ticker filter.
        markettype: Optional market ticker filter.
        startdate: Optional UTC start date YYYY-MM-DD or UNIX epoch.
        enddate: Optional UTC end date YYYY-MM-DD or UNIX epoch.
        limit: Optional max records (default 200, max 500).
    """
    params = {
        "cointype": cointype,
        "markettype": markettype,
        "startdate": startdate,
        "enddate": enddate,
        "limit": limit,
    }
    async with get_client() as client:
        return await _call(
            "get_my_order_history",
            client.my_order_history(cointype, markettype, startdate, enddate, limit),
            params=params,
        )


@mcp.tool(annotations=_READ_ONLY)
async def get_my_market_order_history(
    cointype: str | None = None,
    markettype: str | None = None,
    startdate: str | None = None,
    enddate: str | None = None,
    limit: int | None = None,
) -> str:
    """List your completed market order history.

    Args:
        cointype: Optional coin ticker filter.
        markettype: Optional market ticker filter.
        startdate: Optional UTC start date YYYY-MM-DD or UNIX epoch.
        enddate: Optional UTC end date YYYY-MM-DD or UNIX epoch.
        limit: Optional max records (default 200, max 500).
    """
    params = {
        "cointype": cointype,
        "markettype": markettype,
        "startdate": startdate,
        "enddate": enddate,
        "limit": limit,
    }
    async with get_client() as client:
        return await _call(
            "get_my_market_order_history",
            client.my_market_order_history(
                cointype, markettype, startdate, enddate, limit
            ),
            params=params,
        )


@mcp.tool(annotations=_READ_ONLY)
async def get_my_send_receive_history() -> str:
    """List your coin send and receive transaction history."""
    async with get_client() as client:
        return await _call("get_my_send_receive_history", client.my_send_receive())


@mcp.tool(annotations=_READ_ONLY)
async def get_my_deposits(startdate: str | None = None, enddate: str | None = None) -> str:
    """List your AUD deposit history.

    Args:
        startdate: Optional UTC start date YYYY-MM-DD or UNIX epoch.
        enddate: Optional UTC end date YYYY-MM-DD or UNIX epoch.
    """
    params = {"startdate": startdate, "enddate": enddate}
    async with get_client() as client:
        return await _call(
            "get_my_deposits", client.my_deposits(startdate, enddate), params=params
        )


@mcp.tool(annotations=_READ_ONLY)
async def get_my_withdrawals(
    startdate: str | None = None, enddate: str | None = None
) -> str:
    """List your AUD withdrawal history.

    Args:
        startdate: Optional UTC start date YYYY-MM-DD or UNIX epoch.
        enddate: Optional UTC end date YYYY-MM-DD or UNIX epoch.
    """
    params = {"startdate": startdate, "enddate": enddate}
    async with get_client() as client:
        return await _call(
            "get_my_withdrawals",
            client.my_withdrawals(startdate, enddate),
            params=params,
        )


@mcp.tool(annotations=_READ_ONLY)
async def get_my_affiliate_payments() -> str:
    """List completed affiliate payments."""
    async with get_client() as client:
        return await _call("get_my_affiliate_payments", client.my_affiliate_payments())


@mcp.tool(annotations=_READ_ONLY)
async def get_my_referral_payments() -> str:
    """List completed referral payments."""
    async with get_client() as client:
        return await _call("get_my_referral_payments", client.my_referral_payments())


@mcp.tool(annotations=_READ_ONLY)
async def get_readonly_market_open_orders(
    cointype: str, markettype: str | None = None
) -> str:
    """List open market orders via the authenticated read-only API.

    Args:
        cointype: Coin ticker such as BTC.
        markettype: Optional market ticker such as AUD or USDT.
    """
    params = {"cointype": cointype, "markettype": markettype}
    async with get_client() as client:
        return await _call(
            "get_readonly_market_open_orders",
            client.ro_market_open_orders(cointype, markettype),
            params=params,
        )


@mcp.tool(annotations=_READ_ONLY)
async def get_readonly_market_completed_orders(
    cointype: str,
    markettype: str | None = None,
    startdate: str | None = None,
    enddate: str | None = None,
    limit: int | None = None,
) -> str:
    """List completed market orders via the authenticated read-only API.

    Args:
        cointype: Coin ticker such as BTC.
        markettype: Optional market ticker such as AUD or USDT.
        startdate: Optional UTC start date YYYY-MM-DD or UNIX epoch.
        enddate: Optional UTC end date YYYY-MM-DD or UNIX epoch.
        limit: Optional max records (default 200, max 500).
    """
    params = {
        "cointype": cointype,
        "markettype": markettype,
        "startdate": startdate,
        "enddate": enddate,
        "limit": limit,
    }
    async with get_client() as client:
        return await _call(
            "get_readonly_market_completed_orders",
            client.ro_market_completed_orders(
                cointype, markettype, startdate, enddate, limit
            ),
            params=params,
        )


# ---- Full-access / quote tools ------------------------------------------


@mcp.tool(annotations=_READ_ONLY)
async def check_full_access_status() -> str:
    """Check that the configured full-access API credentials are working."""
    async with get_client() as client:
        return await _call("check_full_access_status", client.full_status())


@mcp.tool(annotations=_READ_ONLY)
async def get_coin_deposit_address(cointype: str) -> str:
    """Get deposit networks and addresses for a coin.

    Args:
        cointype: Coin ticker such as BTC.
    """
    params = {"cointype": cointype}
    async with get_client() as client:
        return await _call(
            "get_coin_deposit_address",
            client.coin_deposit_address(cointype),
            params=params,
        )


@mcp.tool(annotations=_READ_ONLY)
async def get_buy_now_coin_list() -> str:
    """List coins available for Buy Now."""
    async with get_client() as client:
        return await _call("get_buy_now_coin_list", client.buy_now_coin_list())


@mcp.tool(annotations=_READ_ONLY)
async def get_sell_now_coin_list() -> str:
    """List coins available for Sell/Swap Now."""
    async with get_client() as client:
        return await _call("get_sell_now_coin_list", client.sell_now_coin_list())


@mcp.tool(annotations=_READ_ONLY)
async def quote_buy_now(cointype: str, amount: float, amounttype: str = "coin") -> str:
    """Get a Buy Now quote.

    Args:
        cointype: Coin ticker such as BTC.
        amount: Amount to buy.
        amounttype: Whether amount is 'coin' or 'aud'.
    """
    params = {"cointype": cointype, "amount": amount, "amounttype": amounttype}
    async with get_client() as client:
        return await _call(
            "quote_buy_now",
            client.quote_buy_now(cointype, amount, amounttype),
            params=params,
        )


@mcp.tool(annotations=_READ_ONLY)
async def quote_sell_now(cointype: str, amount: float, amounttype: str = "coin") -> str:
    """Get a Sell Now quote.

    Args:
        cointype: Coin ticker such as BTC.
        amount: Amount to sell.
        amounttype: Whether amount is 'coin' or 'aud'.
    """
    params = {"cointype": cointype, "amount": amount, "amounttype": amounttype}
    async with get_client() as client:
        return await _call(
            "quote_sell_now",
            client.quote_sell_now(cointype, amount, amounttype),
            params=params,
        )


@mcp.tool(annotations=_READ_ONLY)
async def quote_swap_now(cointypesell: str, cointypebuy: str, amount: float) -> str:
    """Get a Swap Now quote.

    Args:
        cointypesell: Coin ticker to sell/swap from.
        cointypebuy: Coin ticker to receive.
        amount: Amount of the sell coin to swap.
    """
    params = {
        "cointypesell": cointypesell,
        "cointypebuy": cointypebuy,
        "amount": amount,
    }
    async with get_client() as client:
        return await _call(
            "quote_swap_now",
            client.quote_swap_now(cointypesell, cointypebuy, amount),
            params=params,
        )


# ---- Privileged tools (registered only when env flags allow) ------------


async def place_buy_order(
    cointype: str,
    amount: float,
    rate: float,
    markettype: str | None = None,
    confirm_token: str | None = None,
) -> str:
    """Place a limit/market buy order.

    Args:
        cointype: Coin ticker such as BTC.
        amount: Coin amount to buy.
        rate: Limit rate in market currency.
        markettype: Optional market ticker (default AUD).
        confirm_token: Required when COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN is set.
    """
    params = {
        "cointype": cointype,
        "amount": amount,
        "rate": rate,
        "markettype": markettype,
        "confirm_token": confirm_token,
    }
    try:
        _require_trading()
        require_destructive_confirmation(confirm_token)
        enforce_order_amount(amount)
    except CoinspotError as exc:
        message = sanitize_error_message(str(exc))
        audit_event("place_buy_order", outcome="denied", params=params, detail=message)
        return _json({"status": "error", "message": message})
    async with get_client() as client:
        return await _call(
            "place_buy_order",
            client.place_buy_order(cointype, amount, rate, markettype),
            params=params,
        )


async def edit_buy_order(
    cointype: str,
    order_id: str,
    rate: float,
    newrate: float,
    confirm_token: str | None = None,
) -> str:
    """Edit an open buy order rate.

    Args:
        cointype: Coin ticker.
        order_id: Existing buy order id.
        rate: Current order rate.
        newrate: Proposed new rate.
        confirm_token: Required when COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN is set.
    """
    params = {
        "cointype": cointype,
        "order_id": order_id,
        "rate": rate,
        "newrate": newrate,
        "confirm_token": confirm_token,
    }
    try:
        _require_trading()
        require_destructive_confirmation(confirm_token)
    except CoinspotError as exc:
        message = sanitize_error_message(str(exc))
        audit_event("edit_buy_order", outcome="denied", params=params, detail=message)
        return _json({"status": "error", "message": message})
    async with get_client() as client:
        return await _call(
            "edit_buy_order",
            client.edit_buy_order(cointype, order_id, rate, newrate),
            params=params,
        )


async def place_buy_now(
    cointype: str,
    amount: float,
    amounttype: str = "coin",
    rate: float | None = None,
    threshold: float | None = None,
    direction: str | None = None,
    confirm_token: str | None = None,
) -> str:
    """Place a Buy Now (instant) order.

    Args:
        cointype: Coin ticker.
        amount: Amount to buy.
        amounttype: 'coin' or 'aud'.
        rate: Optional quote rate used with threshold.
        threshold: Optional max percent deviation from rate.
        direction: Optional UP, DOWN, or BOTH.
        confirm_token: Required when COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN is set.
    """
    params = {
        "cointype": cointype,
        "amount": amount,
        "amounttype": amounttype,
        "rate": rate,
        "threshold": threshold,
        "direction": direction,
        "confirm_token": confirm_token,
    }
    try:
        _require_trading()
        require_destructive_confirmation(confirm_token)
        enforce_order_amount(amount)
    except CoinspotError as exc:
        message = sanitize_error_message(str(exc))
        audit_event("place_buy_now", outcome="denied", params=params, detail=message)
        return _json({"status": "error", "message": message})
    async with get_client() as client:
        return await _call(
            "place_buy_now",
            client.place_buy_now(cointype, amount, amounttype, rate, threshold, direction),
            params=params,
        )


async def place_sell_order(
    cointype: str,
    amount: float,
    rate: float,
    markettype: str | None = None,
    confirm_token: str | None = None,
) -> str:
    """Place a limit/market sell order.

    Args:
        cointype: Coin ticker.
        amount: Coin amount to sell.
        rate: Limit rate in market currency.
        markettype: Optional market ticker (default AUD).
        confirm_token: Required when COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN is set.
    """
    params = {
        "cointype": cointype,
        "amount": amount,
        "rate": rate,
        "markettype": markettype,
        "confirm_token": confirm_token,
    }
    try:
        _require_trading()
        require_destructive_confirmation(confirm_token)
        enforce_order_amount(amount)
    except CoinspotError as exc:
        message = sanitize_error_message(str(exc))
        audit_event("place_sell_order", outcome="denied", params=params, detail=message)
        return _json({"status": "error", "message": message})
    async with get_client() as client:
        return await _call(
            "place_sell_order",
            client.place_sell_order(cointype, amount, rate, markettype),
            params=params,
        )


async def edit_sell_order(
    cointype: str,
    order_id: str,
    rate: float,
    newrate: float,
    confirm_token: str | None = None,
) -> str:
    """Edit an open sell order rate.

    Args:
        cointype: Coin ticker.
        order_id: Existing sell order id.
        rate: Current order rate.
        newrate: Proposed new rate.
        confirm_token: Required when COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN is set.
    """
    params = {
        "cointype": cointype,
        "order_id": order_id,
        "rate": rate,
        "newrate": newrate,
        "confirm_token": confirm_token,
    }
    try:
        _require_trading()
        require_destructive_confirmation(confirm_token)
    except CoinspotError as exc:
        message = sanitize_error_message(str(exc))
        audit_event("edit_sell_order", outcome="denied", params=params, detail=message)
        return _json({"status": "error", "message": message})
    async with get_client() as client:
        return await _call(
            "edit_sell_order",
            client.edit_sell_order(cointype, order_id, rate, newrate),
            params=params,
        )


async def place_sell_now(
    cointype: str,
    amount: float,
    amounttype: str = "coin",
    rate: float | None = None,
    threshold: float | None = None,
    direction: str | None = None,
    confirm_token: str | None = None,
) -> str:
    """Place a Sell Now (instant) order.

    Args:
        cointype: Coin ticker.
        amount: Amount to sell.
        amounttype: 'coin' or 'aud'.
        rate: Optional quote rate used with threshold.
        threshold: Optional max percent deviation from rate.
        direction: Optional UP, DOWN, or BOTH.
        confirm_token: Required when COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN is set.
    """
    params = {
        "cointype": cointype,
        "amount": amount,
        "amounttype": amounttype,
        "rate": rate,
        "threshold": threshold,
        "direction": direction,
        "confirm_token": confirm_token,
    }
    try:
        _require_trading()
        require_destructive_confirmation(confirm_token)
        enforce_order_amount(amount)
    except CoinspotError as exc:
        message = sanitize_error_message(str(exc))
        audit_event("place_sell_now", outcome="denied", params=params, detail=message)
        return _json({"status": "error", "message": message})
    async with get_client() as client:
        return await _call(
            "place_sell_now",
            client.place_sell_now(
                cointype, amount, amounttype, rate, threshold, direction
            ),
            params=params,
        )


async def place_swap_now(
    cointypesell: str,
    cointypebuy: str,
    amount: float,
    rate: float | None = None,
    threshold: float | None = None,
    direction: str | None = None,
    confirm_token: str | None = None,
) -> str:
    """Place a Swap Now order.

    Args:
        cointypesell: Coin ticker to sell/swap from.
        cointypebuy: Coin ticker to receive.
        amount: Amount of sell coin.
        rate: Optional quote rate used with threshold.
        threshold: Optional max percent deviation from rate.
        direction: Optional UP, DOWN, or BOTH.
        confirm_token: Required when COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN is set.
    """
    params = {
        "cointypesell": cointypesell,
        "cointypebuy": cointypebuy,
        "amount": amount,
        "rate": rate,
        "threshold": threshold,
        "direction": direction,
        "confirm_token": confirm_token,
    }
    try:
        _require_trading()
        require_destructive_confirmation(confirm_token)
        enforce_order_amount(amount)
    except CoinspotError as exc:
        message = sanitize_error_message(str(exc))
        audit_event("place_swap_now", outcome="denied", params=params, detail=message)
        return _json({"status": "error", "message": message})
    async with get_client() as client:
        return await _call(
            "place_swap_now",
            client.place_swap_now(
                cointypesell, cointypebuy, amount, rate, threshold, direction
            ),
            params=params,
        )


async def cancel_buy_order(order_id: str, confirm_token: str | None = None) -> str:
    """Cancel an open buy order.

    Args:
        order_id: Buy order id to cancel.
        confirm_token: Required when COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN is set.
    """
    params = {"order_id": order_id, "confirm_token": confirm_token}
    try:
        _require_trading()
        require_destructive_confirmation(confirm_token)
    except CoinspotError as exc:
        message = sanitize_error_message(str(exc))
        audit_event("cancel_buy_order", outcome="denied", params=params, detail=message)
        return _json({"status": "error", "message": message})
    async with get_client() as client:
        return await _call(
            "cancel_buy_order", client.cancel_buy_order(order_id), params=params
        )


async def cancel_all_buy_orders(
    coin: str | None = None, confirm_token: str | None = None
) -> str:
    """Cancel all open buy orders, optionally filtered by coin.

    Args:
        coin: Optional coin ticker filter.
        confirm_token: Required when COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN is set.
    """
    params = {"coin": coin, "confirm_token": confirm_token}
    try:
        _require_trading()
        require_destructive_confirmation(confirm_token)
    except CoinspotError as exc:
        message = sanitize_error_message(str(exc))
        audit_event(
            "cancel_all_buy_orders", outcome="denied", params=params, detail=message
        )
        return _json({"status": "error", "message": message})
    async with get_client() as client:
        return await _call(
            "cancel_all_buy_orders",
            client.cancel_all_buy_orders(coin),
            params=params,
        )


async def cancel_sell_order(order_id: str, confirm_token: str | None = None) -> str:
    """Cancel an open sell order.

    Args:
        order_id: Sell order id to cancel.
        confirm_token: Required when COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN is set.
    """
    params = {"order_id": order_id, "confirm_token": confirm_token}
    try:
        _require_trading()
        require_destructive_confirmation(confirm_token)
    except CoinspotError as exc:
        message = sanitize_error_message(str(exc))
        audit_event("cancel_sell_order", outcome="denied", params=params, detail=message)
        return _json({"status": "error", "message": message})
    async with get_client() as client:
        return await _call(
            "cancel_sell_order", client.cancel_sell_order(order_id), params=params
        )


async def cancel_all_sell_orders(
    coin: str | None = None, confirm_token: str | None = None
) -> str:
    """Cancel all open sell orders, optionally filtered by coin.

    Args:
        coin: Optional coin ticker filter.
        confirm_token: Required when COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN is set.
    """
    params = {"coin": coin, "confirm_token": confirm_token}
    try:
        _require_trading()
        require_destructive_confirmation(confirm_token)
    except CoinspotError as exc:
        message = sanitize_error_message(str(exc))
        audit_event(
            "cancel_all_sell_orders", outcome="denied", params=params, detail=message
        )
        return _json({"status": "error", "message": message})
    async with get_client() as client:
        return await _call(
            "cancel_all_sell_orders",
            client.cancel_all_sell_orders(coin),
            params=params,
        )


async def get_coin_withdraw_details(cointype: str) -> str:
    """Get withdrawal networks, fees, and minimums for a coin.

    Args:
        cointype: Coin ticker such as BTC.
    """
    params = {"cointype": cointype}
    try:
        _require_withdrawals()
    except CoinspotError as exc:
        message = sanitize_error_message(str(exc))
        audit_event(
            "get_coin_withdraw_details",
            outcome="denied",
            params=params,
            detail=message,
        )
        return _json({"status": "error", "message": message})
    async with get_client() as client:
        return await _call(
            "get_coin_withdraw_details",
            client.coin_withdraw_details(cointype),
            params=params,
        )


async def withdraw_coin(
    cointype: str,
    amount: float,
    address: str,
    network: str | None = None,
    paymentid: str | None = None,
    confirm_token: str | None = None,
) -> str:
    """Withdraw coins to an external address.

    Always requests CoinSpot email confirmation (emailconfirm=YES). Callers cannot
    disable that safeguard. Requires COINSPOT_ALLOW_WITHDRAWALS=true.

    Args:
        cointype: Coin ticker.
        amount: Amount to withdraw.
        address: Destination address.
        network: Optional network such as ETH or BSC.
        paymentid: Optional memo/payment id where required.
        confirm_token: Required when COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN is set.
    """
    params = {
        "cointype": cointype,
        "amount": amount,
        "address": address,
        "network": network,
        "paymentid": paymentid,
        "confirm_token": confirm_token,
    }
    try:
        _require_withdrawals()
        require_destructive_confirmation(confirm_token)
        enforce_withdraw_amount(amount)
        enforce_withdraw_address(address)
    except CoinspotError as exc:
        message = sanitize_error_message(str(exc))
        audit_event("withdraw_coin", outcome="denied", params=params, detail=message)
        return _json({"status": "error", "message": message})
    async with get_client() as client:
        return await _call(
            "withdraw_coin",
            client.coin_withdraw(
                cointype,
                amount,
                address,
                network=network,
                paymentid=paymentid,
            ),
            params=params,
        )


_PRIVILEGED_TOOLS: dict[str, Any] = {
    "place_buy_order": place_buy_order,
    "edit_buy_order": edit_buy_order,
    "place_buy_now": place_buy_now,
    "place_sell_order": place_sell_order,
    "edit_sell_order": edit_sell_order,
    "place_sell_now": place_sell_now,
    "place_swap_now": place_swap_now,
    "cancel_buy_order": cancel_buy_order,
    "cancel_all_buy_orders": cancel_all_buy_orders,
    "cancel_sell_order": cancel_sell_order,
    "cancel_all_sell_orders": cancel_all_sell_orders,
    "get_coin_withdraw_details": get_coin_withdraw_details,
    "withdraw_coin": withdraw_coin,
}


def _safe_remove_tool(name: str) -> None:
    try:
        mcp.remove_tool(name)
    except Exception:
        # Tool may already be absent depending on prior policy application.
        pass


def apply_tool_exposure_policy() -> None:
    """Register destructive tools only when corresponding env flags are enabled."""
    for name in TRADING_TOOL_NAMES + WITHDRAWAL_TOOL_NAMES:
        _safe_remove_tool(name)

    if trading_enabled():
        for name in TRADING_TOOL_NAMES:
            mcp.add_tool(_PRIVILEGED_TOOLS[name], name=name, annotations=_DESTRUCTIVE)

    if withdrawals_enabled():
        mcp.add_tool(
            get_coin_withdraw_details,
            name="get_coin_withdraw_details",
            annotations=_READ_ONLY,
        )
        mcp.add_tool(withdraw_coin, name="withdraw_coin", annotations=_DESTRUCTIVE)


# Apply least-privilege tool exposure at import time (stdio server startup).
apply_tool_exposure_policy()


def run() -> None:
    """Run the MCP server over stdio."""
    apply_tool_exposure_policy()
    mcp.run(transport="stdio")
