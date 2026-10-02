"""CoinSpot MCP server exposing public, read-only, and trading tools."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from coinspot_mcp.client import CoinspotClient, CoinspotError
from coinspot_mcp.security import (
    AUDIT_LOGGER,
    audit_event,
    configure_audit_logging,
    destructive_confirm_configured,
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
        "Public market tools do not need CoinSpot credentials. "
        "For any account/trading tool, the calling LLM must supply the end-user's "
        "coinspot_api_key and coinspot_api_secret on every call. "
        "Remote HTTP/Lambda deployments also require a bearer token on the MCP "
        "connection itself (Authorization: Bearer <COINSPOT_MCP_AUTH_TOKEN>). "
        "Trading and withdrawal tools are only registered when "
        "COINSPOT_ALLOW_TRADING / COINSPOT_ALLOW_WITHDRAWALS are enabled."
    ),
    website_url="https://www.coinspot.com.au/v2/api",
    version="0.3.0",
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


def get_client(
    coinspot_api_key: str | None = None,
    coinspot_api_secret: str | None = None,
) -> CoinspotClient:
    """Build a client. Authenticated tools must pass the user's key/secret."""
    return CoinspotClient(
        api_key=coinspot_api_key or "",
        api_secret=coinspot_api_secret or "",
        use_env_fallback=False,
    )


def _require_user_credentials(coinspot_api_key: str, coinspot_api_secret: str) -> None:
    if not coinspot_api_key.strip() or not coinspot_api_secret.strip():
        raise CoinspotError(
            "coinspot_api_key and coinspot_api_secret are required. "
            "Pass the end-user's CoinSpot API credentials on this tool call."
        )


def _require_trading() -> None:
    if not trading_enabled():
        raise CoinspotError("Trading tools are disabled on this server.")


def _require_withdrawals() -> None:
    if not withdrawals_enabled():
        raise CoinspotError("Withdrawal tools are disabled on this server.")


async def _with_user_client(
    tool_name: str,
    coinspot_api_key: str,
    coinspot_api_secret: str,
    params: dict[str, Any],
    operation: Callable[[CoinspotClient], Awaitable[Any]],
    *,
    prechecks: Callable[[], None] | None = None,
) -> str:
    try:
        _require_user_credentials(coinspot_api_key, coinspot_api_secret)
        if prechecks is not None:
            prechecks()
    except CoinspotError as exc:
        message = sanitize_error_message(str(exc))
        audit_event(tool_name, outcome="denied", params=params, detail=message)
        return _json({"status": "error", "message": message})

    async with get_client(coinspot_api_key, coinspot_api_secret) as client:
        return await _call(tool_name, operation(client), params=params)


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


# ---- Authenticated account tools (per-user CoinSpot credentials) --------


@mcp.tool(annotations=_READ_ONLY)
async def check_readonly_status(
    coinspot_api_key: str, coinspot_api_secret: str
) -> str:
    """Check that the supplied CoinSpot credentials work against the read-only API.

    Args:
        coinspot_api_key: End-user CoinSpot API key.
        coinspot_api_secret: End-user CoinSpot API secret.
    """
    params = {
        "coinspot_api_key": coinspot_api_key,
        "coinspot_api_secret": coinspot_api_secret,
    }
    return await _with_user_client(
        "check_readonly_status",
        coinspot_api_key,
        coinspot_api_secret,
        params,
        lambda c: c.ro_status(),
    )


@mcp.tool(annotations=_READ_ONLY)
async def get_my_balances(coinspot_api_key: str, coinspot_api_secret: str) -> str:
    """List all coin balances with AUD value and rate for the given user account.

    Args:
        coinspot_api_key: End-user CoinSpot API key.
        coinspot_api_secret: End-user CoinSpot API secret.
    """
    params = {
        "coinspot_api_key": coinspot_api_key,
        "coinspot_api_secret": coinspot_api_secret,
    }
    return await _with_user_client(
        "get_my_balances",
        coinspot_api_key,
        coinspot_api_secret,
        params,
        lambda c: c.my_balances(),
    )


@mcp.tool(annotations=_READ_ONLY)
async def get_my_balance(
    coinspot_api_key: str,
    coinspot_api_secret: str,
    cointype: str,
    available: bool = False,
) -> str:
    """Get balance details for a single coin for the given user account.

    Args:
        coinspot_api_key: End-user CoinSpot API key.
        coinspot_api_secret: End-user CoinSpot API secret.
        cointype: Coin ticker such as BTC or AUD.
        available: If true, also return the available (unlocked) balance.
    """
    params = {
        "coinspot_api_key": coinspot_api_key,
        "coinspot_api_secret": coinspot_api_secret,
        "cointype": cointype,
        "available": available,
    }
    return await _with_user_client(
        "get_my_balance",
        coinspot_api_key,
        coinspot_api_secret,
        params,
        lambda c: c.my_balance(cointype, available=available),
    )


@mcp.tool(annotations=_READ_ONLY)
async def get_my_open_market_orders(
    coinspot_api_key: str,
    coinspot_api_secret: str,
    cointype: str | None = None,
    markettype: str | None = None,
) -> str:
    """List the user's open market orders.

    Args:
        coinspot_api_key: End-user CoinSpot API key.
        coinspot_api_secret: End-user CoinSpot API secret.
        cointype: Optional coin ticker filter.
        markettype: Optional market ticker filter such as AUD or USDT.
    """
    params = {
        "coinspot_api_key": coinspot_api_key,
        "coinspot_api_secret": coinspot_api_secret,
        "cointype": cointype,
        "markettype": markettype,
    }
    return await _with_user_client(
        "get_my_open_market_orders",
        coinspot_api_key,
        coinspot_api_secret,
        params,
        lambda c: c.my_open_market_orders(cointype, markettype),
    )


@mcp.tool(annotations=_READ_ONLY)
async def get_my_open_limit_orders(
    coinspot_api_key: str,
    coinspot_api_secret: str,
    cointype: str | None = None,
) -> str:
    """List the user's open limit/stop orders.

    Args:
        coinspot_api_key: End-user CoinSpot API key.
        coinspot_api_secret: End-user CoinSpot API secret.
        cointype: Optional coin ticker filter.
    """
    params = {
        "coinspot_api_key": coinspot_api_key,
        "coinspot_api_secret": coinspot_api_secret,
        "cointype": cointype,
    }
    return await _with_user_client(
        "get_my_open_limit_orders",
        coinspot_api_key,
        coinspot_api_secret,
        params,
        lambda c: c.my_open_limit_orders(cointype),
    )


@mcp.tool(annotations=_READ_ONLY)
async def get_my_order_history(
    coinspot_api_key: str,
    coinspot_api_secret: str,
    cointype: str | None = None,
    markettype: str | None = None,
    startdate: str | None = None,
    enddate: str | None = None,
    limit: int | None = None,
) -> str:
    """List the user's completed order history.

    Args:
        coinspot_api_key: End-user CoinSpot API key.
        coinspot_api_secret: End-user CoinSpot API secret.
        cointype: Optional coin ticker filter.
        markettype: Optional market ticker filter.
        startdate: Optional UTC start date YYYY-MM-DD or UNIX epoch.
        enddate: Optional UTC end date YYYY-MM-DD or UNIX epoch.
        limit: Optional max records (default 200, max 500).
    """
    params = {
        "coinspot_api_key": coinspot_api_key,
        "coinspot_api_secret": coinspot_api_secret,
        "cointype": cointype,
        "markettype": markettype,
        "startdate": startdate,
        "enddate": enddate,
        "limit": limit,
    }
    return await _with_user_client(
        "get_my_order_history",
        coinspot_api_key,
        coinspot_api_secret,
        params,
        lambda c: c.my_order_history(cointype, markettype, startdate, enddate, limit),
    )


@mcp.tool(annotations=_READ_ONLY)
async def get_my_market_order_history(
    coinspot_api_key: str,
    coinspot_api_secret: str,
    cointype: str | None = None,
    markettype: str | None = None,
    startdate: str | None = None,
    enddate: str | None = None,
    limit: int | None = None,
) -> str:
    """List the user's completed market order history.

    Args:
        coinspot_api_key: End-user CoinSpot API key.
        coinspot_api_secret: End-user CoinSpot API secret.
        cointype: Optional coin ticker filter.
        markettype: Optional market ticker filter.
        startdate: Optional UTC start date YYYY-MM-DD or UNIX epoch.
        enddate: Optional UTC end date YYYY-MM-DD or UNIX epoch.
        limit: Optional max records (default 200, max 500).
    """
    params = {
        "coinspot_api_key": coinspot_api_key,
        "coinspot_api_secret": coinspot_api_secret,
        "cointype": cointype,
        "markettype": markettype,
        "startdate": startdate,
        "enddate": enddate,
        "limit": limit,
    }
    return await _with_user_client(
        "get_my_market_order_history",
        coinspot_api_key,
        coinspot_api_secret,
        params,
        lambda c: c.my_market_order_history(
            cointype, markettype, startdate, enddate, limit
        ),
    )


@mcp.tool(annotations=_READ_ONLY)
async def get_my_send_receive_history(
    coinspot_api_key: str, coinspot_api_secret: str
) -> str:
    """List the user's coin send and receive transaction history.

    Args:
        coinspot_api_key: End-user CoinSpot API key.
        coinspot_api_secret: End-user CoinSpot API secret.
    """
    params = {
        "coinspot_api_key": coinspot_api_key,
        "coinspot_api_secret": coinspot_api_secret,
    }
    return await _with_user_client(
        "get_my_send_receive_history",
        coinspot_api_key,
        coinspot_api_secret,
        params,
        lambda c: c.my_send_receive(),
    )


@mcp.tool(annotations=_READ_ONLY)
async def get_my_deposits(
    coinspot_api_key: str,
    coinspot_api_secret: str,
    startdate: str | None = None,
    enddate: str | None = None,
) -> str:
    """List the user's AUD deposit history.

    Args:
        coinspot_api_key: End-user CoinSpot API key.
        coinspot_api_secret: End-user CoinSpot API secret.
        startdate: Optional UTC start date YYYY-MM-DD or UNIX epoch.
        enddate: Optional UTC end date YYYY-MM-DD or UNIX epoch.
    """
    params = {
        "coinspot_api_key": coinspot_api_key,
        "coinspot_api_secret": coinspot_api_secret,
        "startdate": startdate,
        "enddate": enddate,
    }
    return await _with_user_client(
        "get_my_deposits",
        coinspot_api_key,
        coinspot_api_secret,
        params,
        lambda c: c.my_deposits(startdate, enddate),
    )


@mcp.tool(annotations=_READ_ONLY)
async def get_my_withdrawals(
    coinspot_api_key: str,
    coinspot_api_secret: str,
    startdate: str | None = None,
    enddate: str | None = None,
) -> str:
    """List the user's AUD withdrawal history.

    Args:
        coinspot_api_key: End-user CoinSpot API key.
        coinspot_api_secret: End-user CoinSpot API secret.
        startdate: Optional UTC start date YYYY-MM-DD or UNIX epoch.
        enddate: Optional UTC end date YYYY-MM-DD or UNIX epoch.
    """
    params = {
        "coinspot_api_key": coinspot_api_key,
        "coinspot_api_secret": coinspot_api_secret,
        "startdate": startdate,
        "enddate": enddate,
    }
    return await _with_user_client(
        "get_my_withdrawals",
        coinspot_api_key,
        coinspot_api_secret,
        params,
        lambda c: c.my_withdrawals(startdate, enddate),
    )


@mcp.tool(annotations=_READ_ONLY)
async def get_my_affiliate_payments(
    coinspot_api_key: str, coinspot_api_secret: str
) -> str:
    """List completed affiliate payments for the user.

    Args:
        coinspot_api_key: End-user CoinSpot API key.
        coinspot_api_secret: End-user CoinSpot API secret.
    """
    params = {
        "coinspot_api_key": coinspot_api_key,
        "coinspot_api_secret": coinspot_api_secret,
    }
    return await _with_user_client(
        "get_my_affiliate_payments",
        coinspot_api_key,
        coinspot_api_secret,
        params,
        lambda c: c.my_affiliate_payments(),
    )


@mcp.tool(annotations=_READ_ONLY)
async def get_my_referral_payments(
    coinspot_api_key: str, coinspot_api_secret: str
) -> str:
    """List completed referral payments for the user.

    Args:
        coinspot_api_key: End-user CoinSpot API key.
        coinspot_api_secret: End-user CoinSpot API secret.
    """
    params = {
        "coinspot_api_key": coinspot_api_key,
        "coinspot_api_secret": coinspot_api_secret,
    }
    return await _with_user_client(
        "get_my_referral_payments",
        coinspot_api_key,
        coinspot_api_secret,
        params,
        lambda c: c.my_referral_payments(),
    )


@mcp.tool(annotations=_READ_ONLY)
async def get_readonly_market_open_orders(
    coinspot_api_key: str,
    coinspot_api_secret: str,
    cointype: str,
    markettype: str | None = None,
) -> str:
    """List open market orders via the authenticated read-only API.

    Args:
        coinspot_api_key: End-user CoinSpot API key.
        coinspot_api_secret: End-user CoinSpot API secret.
        cointype: Coin ticker such as BTC.
        markettype: Optional market ticker such as AUD or USDT.
    """
    params = {
        "coinspot_api_key": coinspot_api_key,
        "coinspot_api_secret": coinspot_api_secret,
        "cointype": cointype,
        "markettype": markettype,
    }
    return await _with_user_client(
        "get_readonly_market_open_orders",
        coinspot_api_key,
        coinspot_api_secret,
        params,
        lambda c: c.ro_market_open_orders(cointype, markettype),
    )


@mcp.tool(annotations=_READ_ONLY)
async def get_readonly_market_completed_orders(
    coinspot_api_key: str,
    coinspot_api_secret: str,
    cointype: str,
    markettype: str | None = None,
    startdate: str | None = None,
    enddate: str | None = None,
    limit: int | None = None,
) -> str:
    """List completed market orders via the authenticated read-only API.

    Args:
        coinspot_api_key: End-user CoinSpot API key.
        coinspot_api_secret: End-user CoinSpot API secret.
        cointype: Coin ticker such as BTC.
        markettype: Optional market ticker such as AUD or USDT.
        startdate: Optional UTC start date YYYY-MM-DD or UNIX epoch.
        enddate: Optional UTC end date YYYY-MM-DD or UNIX epoch.
        limit: Optional max records (default 200, max 500).
    """
    params = {
        "coinspot_api_key": coinspot_api_key,
        "coinspot_api_secret": coinspot_api_secret,
        "cointype": cointype,
        "markettype": markettype,
        "startdate": startdate,
        "enddate": enddate,
        "limit": limit,
    }
    return await _with_user_client(
        "get_readonly_market_completed_orders",
        coinspot_api_key,
        coinspot_api_secret,
        params,
        lambda c: c.ro_market_completed_orders(
            cointype, markettype, startdate, enddate, limit
        ),
    )


@mcp.tool(annotations=_READ_ONLY)
async def check_full_access_status(
    coinspot_api_key: str, coinspot_api_secret: str
) -> str:
    """Check that the supplied credentials work against the full-access API.

    Args:
        coinspot_api_key: End-user CoinSpot API key.
        coinspot_api_secret: End-user CoinSpot API secret.
    """
    params = {
        "coinspot_api_key": coinspot_api_key,
        "coinspot_api_secret": coinspot_api_secret,
    }
    return await _with_user_client(
        "check_full_access_status",
        coinspot_api_key,
        coinspot_api_secret,
        params,
        lambda c: c.full_status(),
    )


@mcp.tool(annotations=_READ_ONLY)
async def get_coin_deposit_address(
    coinspot_api_key: str, coinspot_api_secret: str, cointype: str
) -> str:
    """Get deposit networks and addresses for a coin.

    Args:
        coinspot_api_key: End-user CoinSpot API key.
        coinspot_api_secret: End-user CoinSpot API secret.
        cointype: Coin ticker such as BTC.
    """
    params = {
        "coinspot_api_key": coinspot_api_key,
        "coinspot_api_secret": coinspot_api_secret,
        "cointype": cointype,
    }
    return await _with_user_client(
        "get_coin_deposit_address",
        coinspot_api_key,
        coinspot_api_secret,
        params,
        lambda c: c.coin_deposit_address(cointype),
    )


@mcp.tool(annotations=_READ_ONLY)
async def get_buy_now_coin_list(
    coinspot_api_key: str, coinspot_api_secret: str
) -> str:
    """List coins available for Buy Now.

    Args:
        coinspot_api_key: End-user CoinSpot API key.
        coinspot_api_secret: End-user CoinSpot API secret.
    """
    params = {
        "coinspot_api_key": coinspot_api_key,
        "coinspot_api_secret": coinspot_api_secret,
    }
    return await _with_user_client(
        "get_buy_now_coin_list",
        coinspot_api_key,
        coinspot_api_secret,
        params,
        lambda c: c.buy_now_coin_list(),
    )


@mcp.tool(annotations=_READ_ONLY)
async def get_sell_now_coin_list(
    coinspot_api_key: str, coinspot_api_secret: str
) -> str:
    """List coins available for Sell/Swap Now.

    Args:
        coinspot_api_key: End-user CoinSpot API key.
        coinspot_api_secret: End-user CoinSpot API secret.
    """
    params = {
        "coinspot_api_key": coinspot_api_key,
        "coinspot_api_secret": coinspot_api_secret,
    }
    return await _with_user_client(
        "get_sell_now_coin_list",
        coinspot_api_key,
        coinspot_api_secret,
        params,
        lambda c: c.sell_now_coin_list(),
    )


@mcp.tool(annotations=_READ_ONLY)
async def quote_buy_now(
    coinspot_api_key: str,
    coinspot_api_secret: str,
    cointype: str,
    amount: float,
    amounttype: str = "coin",
) -> str:
    """Get a Buy Now quote.

    Args:
        coinspot_api_key: End-user CoinSpot API key.
        coinspot_api_secret: End-user CoinSpot API secret.
        cointype: Coin ticker such as BTC.
        amount: Amount to buy.
        amounttype: Whether amount is 'coin' or 'aud'.
    """
    params = {
        "coinspot_api_key": coinspot_api_key,
        "coinspot_api_secret": coinspot_api_secret,
        "cointype": cointype,
        "amount": amount,
        "amounttype": amounttype,
    }
    return await _with_user_client(
        "quote_buy_now",
        coinspot_api_key,
        coinspot_api_secret,
        params,
        lambda c: c.quote_buy_now(cointype, amount, amounttype),
    )


@mcp.tool(annotations=_READ_ONLY)
async def quote_sell_now(
    coinspot_api_key: str,
    coinspot_api_secret: str,
    cointype: str,
    amount: float,
    amounttype: str = "coin",
) -> str:
    """Get a Sell Now quote.

    Args:
        coinspot_api_key: End-user CoinSpot API key.
        coinspot_api_secret: End-user CoinSpot API secret.
        cointype: Coin ticker such as BTC.
        amount: Amount to sell.
        amounttype: Whether amount is 'coin' or 'aud'.
    """
    params = {
        "coinspot_api_key": coinspot_api_key,
        "coinspot_api_secret": coinspot_api_secret,
        "cointype": cointype,
        "amount": amount,
        "amounttype": amounttype,
    }
    return await _with_user_client(
        "quote_sell_now",
        coinspot_api_key,
        coinspot_api_secret,
        params,
        lambda c: c.quote_sell_now(cointype, amount, amounttype),
    )


@mcp.tool(annotations=_READ_ONLY)
async def quote_swap_now(
    coinspot_api_key: str,
    coinspot_api_secret: str,
    cointypesell: str,
    cointypebuy: str,
    amount: float,
) -> str:
    """Get a Swap Now quote.

    Args:
        coinspot_api_key: End-user CoinSpot API key.
        coinspot_api_secret: End-user CoinSpot API secret.
        cointypesell: Coin ticker to sell/swap from.
        cointypebuy: Coin ticker to receive.
        amount: Amount of the sell coin to swap.
    """
    params = {
        "coinspot_api_key": coinspot_api_key,
        "coinspot_api_secret": coinspot_api_secret,
        "cointypesell": cointypesell,
        "cointypebuy": cointypebuy,
        "amount": amount,
    }
    return await _with_user_client(
        "quote_swap_now",
        coinspot_api_key,
        coinspot_api_secret,
        params,
        lambda c: c.quote_swap_now(cointypesell, cointypebuy, amount),
    )


# ---- Privileged tools (registered only when env flags allow) ------------


async def place_buy_order(
    coinspot_api_key: str,
    coinspot_api_secret: str,
    cointype: str,
    amount: float,
    rate: float,
    markettype: str | None = None,
    confirm_token: str | None = None,
) -> str:
    """Place a limit/market buy order.

    Args:
        coinspot_api_key: End-user CoinSpot API key.
        coinspot_api_secret: End-user CoinSpot API secret.
        cointype: Coin ticker such as BTC.
        amount: Coin amount to buy.
        rate: Limit rate in market currency.
        markettype: Optional market ticker (default AUD).
        confirm_token: Required confirm token (must match COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN).
    """
    params = {
        "coinspot_api_key": coinspot_api_key,
        "coinspot_api_secret": coinspot_api_secret,
        "cointype": cointype,
        "amount": amount,
        "rate": rate,
        "markettype": markettype,
        "confirm_token": confirm_token,
    }

    def _pre() -> None:
        _require_trading()
        require_destructive_confirmation(confirm_token)
        enforce_order_amount(amount)

    return await _with_user_client(
        "place_buy_order",
        coinspot_api_key,
        coinspot_api_secret,
        params,
        lambda c: c.place_buy_order(cointype, amount, rate, markettype),
        prechecks=_pre,
    )


async def edit_buy_order(
    coinspot_api_key: str,
    coinspot_api_secret: str,
    cointype: str,
    order_id: str,
    rate: float,
    newrate: float,
    confirm_token: str | None = None,
) -> str:
    """Edit an open buy order rate.

    Args:
        coinspot_api_key: End-user CoinSpot API key.
        coinspot_api_secret: End-user CoinSpot API secret.
        cointype: Coin ticker.
        order_id: Existing buy order id.
        rate: Current order rate.
        newrate: Proposed new rate.
        confirm_token: Required confirm token (must match COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN).
    """
    params = {
        "coinspot_api_key": coinspot_api_key,
        "coinspot_api_secret": coinspot_api_secret,
        "cointype": cointype,
        "order_id": order_id,
        "rate": rate,
        "newrate": newrate,
        "confirm_token": confirm_token,
    }

    def _pre() -> None:
        _require_trading()
        require_destructive_confirmation(confirm_token)

    return await _with_user_client(
        "edit_buy_order",
        coinspot_api_key,
        coinspot_api_secret,
        params,
        lambda c: c.edit_buy_order(cointype, order_id, rate, newrate),
        prechecks=_pre,
    )


async def place_buy_now(
    coinspot_api_key: str,
    coinspot_api_secret: str,
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
        coinspot_api_key: End-user CoinSpot API key.
        coinspot_api_secret: End-user CoinSpot API secret.
        cointype: Coin ticker.
        amount: Amount to buy.
        amounttype: 'coin' or 'aud'.
        rate: Optional quote rate used with threshold.
        threshold: Optional max percent deviation from rate.
        direction: Optional UP, DOWN, or BOTH.
        confirm_token: Required confirm token (must match COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN).
    """
    params = {
        "coinspot_api_key": coinspot_api_key,
        "coinspot_api_secret": coinspot_api_secret,
        "cointype": cointype,
        "amount": amount,
        "amounttype": amounttype,
        "rate": rate,
        "threshold": threshold,
        "direction": direction,
        "confirm_token": confirm_token,
    }

    def _pre() -> None:
        _require_trading()
        require_destructive_confirmation(confirm_token)
        enforce_order_amount(amount)

    return await _with_user_client(
        "place_buy_now",
        coinspot_api_key,
        coinspot_api_secret,
        params,
        lambda c: c.place_buy_now(
            cointype, amount, amounttype, rate, threshold, direction
        ),
        prechecks=_pre,
    )


async def place_sell_order(
    coinspot_api_key: str,
    coinspot_api_secret: str,
    cointype: str,
    amount: float,
    rate: float,
    markettype: str | None = None,
    confirm_token: str | None = None,
) -> str:
    """Place a limit/market sell order.

    Args:
        coinspot_api_key: End-user CoinSpot API key.
        coinspot_api_secret: End-user CoinSpot API secret.
        cointype: Coin ticker.
        amount: Coin amount to sell.
        rate: Limit rate in market currency.
        markettype: Optional market ticker (default AUD).
        confirm_token: Required confirm token (must match COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN).
    """
    params = {
        "coinspot_api_key": coinspot_api_key,
        "coinspot_api_secret": coinspot_api_secret,
        "cointype": cointype,
        "amount": amount,
        "rate": rate,
        "markettype": markettype,
        "confirm_token": confirm_token,
    }

    def _pre() -> None:
        _require_trading()
        require_destructive_confirmation(confirm_token)
        enforce_order_amount(amount)

    return await _with_user_client(
        "place_sell_order",
        coinspot_api_key,
        coinspot_api_secret,
        params,
        lambda c: c.place_sell_order(cointype, amount, rate, markettype),
        prechecks=_pre,
    )


async def edit_sell_order(
    coinspot_api_key: str,
    coinspot_api_secret: str,
    cointype: str,
    order_id: str,
    rate: float,
    newrate: float,
    confirm_token: str | None = None,
) -> str:
    """Edit an open sell order rate.

    Args:
        coinspot_api_key: End-user CoinSpot API key.
        coinspot_api_secret: End-user CoinSpot API secret.
        cointype: Coin ticker.
        order_id: Existing sell order id.
        rate: Current order rate.
        newrate: Proposed new rate.
        confirm_token: Required confirm token (must match COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN).
    """
    params = {
        "coinspot_api_key": coinspot_api_key,
        "coinspot_api_secret": coinspot_api_secret,
        "cointype": cointype,
        "order_id": order_id,
        "rate": rate,
        "newrate": newrate,
        "confirm_token": confirm_token,
    }

    def _pre() -> None:
        _require_trading()
        require_destructive_confirmation(confirm_token)

    return await _with_user_client(
        "edit_sell_order",
        coinspot_api_key,
        coinspot_api_secret,
        params,
        lambda c: c.edit_sell_order(cointype, order_id, rate, newrate),
        prechecks=_pre,
    )


async def place_sell_now(
    coinspot_api_key: str,
    coinspot_api_secret: str,
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
        coinspot_api_key: End-user CoinSpot API key.
        coinspot_api_secret: End-user CoinSpot API secret.
        cointype: Coin ticker.
        amount: Amount to sell.
        amounttype: 'coin' or 'aud'.
        rate: Optional quote rate used with threshold.
        threshold: Optional max percent deviation from rate.
        direction: Optional UP, DOWN, or BOTH.
        confirm_token: Required confirm token (must match COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN).
    """
    params = {
        "coinspot_api_key": coinspot_api_key,
        "coinspot_api_secret": coinspot_api_secret,
        "cointype": cointype,
        "amount": amount,
        "amounttype": amounttype,
        "rate": rate,
        "threshold": threshold,
        "direction": direction,
        "confirm_token": confirm_token,
    }

    def _pre() -> None:
        _require_trading()
        require_destructive_confirmation(confirm_token)
        enforce_order_amount(amount)

    return await _with_user_client(
        "place_sell_now",
        coinspot_api_key,
        coinspot_api_secret,
        params,
        lambda c: c.place_sell_now(
            cointype, amount, amounttype, rate, threshold, direction
        ),
        prechecks=_pre,
    )


async def place_swap_now(
    coinspot_api_key: str,
    coinspot_api_secret: str,
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
        coinspot_api_key: End-user CoinSpot API key.
        coinspot_api_secret: End-user CoinSpot API secret.
        cointypesell: Coin ticker to sell/swap from.
        cointypebuy: Coin ticker to receive.
        amount: Amount of sell coin.
        rate: Optional quote rate used with threshold.
        threshold: Optional max percent deviation from rate.
        direction: Optional UP, DOWN, or BOTH.
        confirm_token: Required confirm token (must match COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN).
    """
    params = {
        "coinspot_api_key": coinspot_api_key,
        "coinspot_api_secret": coinspot_api_secret,
        "cointypesell": cointypesell,
        "cointypebuy": cointypebuy,
        "amount": amount,
        "rate": rate,
        "threshold": threshold,
        "direction": direction,
        "confirm_token": confirm_token,
    }

    def _pre() -> None:
        _require_trading()
        require_destructive_confirmation(confirm_token)
        enforce_order_amount(amount)

    return await _with_user_client(
        "place_swap_now",
        coinspot_api_key,
        coinspot_api_secret,
        params,
        lambda c: c.place_swap_now(
            cointypesell, cointypebuy, amount, rate, threshold, direction
        ),
        prechecks=_pre,
    )


async def cancel_buy_order(
    coinspot_api_key: str,
    coinspot_api_secret: str,
    order_id: str,
    confirm_token: str | None = None,
) -> str:
    """Cancel an open buy order.

    Args:
        coinspot_api_key: End-user CoinSpot API key.
        coinspot_api_secret: End-user CoinSpot API secret.
        order_id: Buy order id to cancel.
        confirm_token: Required confirm token (must match COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN).
    """
    params = {
        "coinspot_api_key": coinspot_api_key,
        "coinspot_api_secret": coinspot_api_secret,
        "order_id": order_id,
        "confirm_token": confirm_token,
    }

    def _pre() -> None:
        _require_trading()
        require_destructive_confirmation(confirm_token)

    return await _with_user_client(
        "cancel_buy_order",
        coinspot_api_key,
        coinspot_api_secret,
        params,
        lambda c: c.cancel_buy_order(order_id),
        prechecks=_pre,
    )


async def cancel_all_buy_orders(
    coinspot_api_key: str,
    coinspot_api_secret: str,
    coin: str | None = None,
    confirm_token: str | None = None,
) -> str:
    """Cancel all open buy orders, optionally filtered by coin.

    Args:
        coinspot_api_key: End-user CoinSpot API key.
        coinspot_api_secret: End-user CoinSpot API secret.
        coin: Optional coin ticker filter.
        confirm_token: Required confirm token (must match COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN).
    """
    params = {
        "coinspot_api_key": coinspot_api_key,
        "coinspot_api_secret": coinspot_api_secret,
        "coin": coin,
        "confirm_token": confirm_token,
    }

    def _pre() -> None:
        _require_trading()
        require_destructive_confirmation(confirm_token)

    return await _with_user_client(
        "cancel_all_buy_orders",
        coinspot_api_key,
        coinspot_api_secret,
        params,
        lambda c: c.cancel_all_buy_orders(coin),
        prechecks=_pre,
    )


async def cancel_sell_order(
    coinspot_api_key: str,
    coinspot_api_secret: str,
    order_id: str,
    confirm_token: str | None = None,
) -> str:
    """Cancel an open sell order.

    Args:
        coinspot_api_key: End-user CoinSpot API key.
        coinspot_api_secret: End-user CoinSpot API secret.
        order_id: Sell order id to cancel.
        confirm_token: Required confirm token (must match COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN).
    """
    params = {
        "coinspot_api_key": coinspot_api_key,
        "coinspot_api_secret": coinspot_api_secret,
        "order_id": order_id,
        "confirm_token": confirm_token,
    }

    def _pre() -> None:
        _require_trading()
        require_destructive_confirmation(confirm_token)

    return await _with_user_client(
        "cancel_sell_order",
        coinspot_api_key,
        coinspot_api_secret,
        params,
        lambda c: c.cancel_sell_order(order_id),
        prechecks=_pre,
    )


async def cancel_all_sell_orders(
    coinspot_api_key: str,
    coinspot_api_secret: str,
    coin: str | None = None,
    confirm_token: str | None = None,
) -> str:
    """Cancel all open sell orders, optionally filtered by coin.

    Args:
        coinspot_api_key: End-user CoinSpot API key.
        coinspot_api_secret: End-user CoinSpot API secret.
        coin: Optional coin ticker filter.
        confirm_token: Required confirm token (must match COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN).
    """
    params = {
        "coinspot_api_key": coinspot_api_key,
        "coinspot_api_secret": coinspot_api_secret,
        "coin": coin,
        "confirm_token": confirm_token,
    }

    def _pre() -> None:
        _require_trading()
        require_destructive_confirmation(confirm_token)

    return await _with_user_client(
        "cancel_all_sell_orders",
        coinspot_api_key,
        coinspot_api_secret,
        params,
        lambda c: c.cancel_all_sell_orders(coin),
        prechecks=_pre,
    )


async def get_coin_withdraw_details(
    coinspot_api_key: str, coinspot_api_secret: str, cointype: str
) -> str:
    """Get withdrawal networks, fees, and minimums for a coin.

    Args:
        coinspot_api_key: End-user CoinSpot API key.
        coinspot_api_secret: End-user CoinSpot API secret.
        cointype: Coin ticker such as BTC.
    """
    params = {
        "coinspot_api_key": coinspot_api_key,
        "coinspot_api_secret": coinspot_api_secret,
        "cointype": cointype,
    }
    return await _with_user_client(
        "get_coin_withdraw_details",
        coinspot_api_key,
        coinspot_api_secret,
        params,
        lambda c: c.coin_withdraw_details(cointype),
        prechecks=_require_withdrawals,
    )


async def withdraw_coin(
    coinspot_api_key: str,
    coinspot_api_secret: str,
    cointype: str,
    amount: float,
    address: str,
    network: str | None = None,
    paymentid: str | None = None,
    confirm_token: str | None = None,
) -> str:
    """Withdraw coins to an external address.

    Always requests CoinSpot email confirmation (emailconfirm=YES).

    Args:
        coinspot_api_key: End-user CoinSpot API key.
        coinspot_api_secret: End-user CoinSpot API secret.
        cointype: Coin ticker.
        amount: Amount to withdraw.
        address: Destination address.
        network: Optional network such as ETH or BSC.
        paymentid: Optional memo/payment id where required.
        confirm_token: Required confirm token (must match COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN).
    """
    params = {
        "coinspot_api_key": coinspot_api_key,
        "coinspot_api_secret": coinspot_api_secret,
        "cointype": cointype,
        "amount": amount,
        "address": address,
        "network": network,
        "paymentid": paymentid,
        "confirm_token": confirm_token,
    }

    def _pre() -> None:
        _require_withdrawals()
        require_destructive_confirmation(confirm_token)
        enforce_withdraw_amount(amount)
        enforce_withdraw_address(address)

    return await _with_user_client(
        "withdraw_coin",
        coinspot_api_key,
        coinspot_api_secret,
        params,
        lambda c: c.coin_withdraw(
            cointype,
            amount,
            address,
            network=network,
            paymentid=paymentid,
        ),
        prechecks=_pre,
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
        pass


def apply_tool_exposure_policy() -> None:
    """Register destructive tools only when env flags AND confirm token are set."""
    configure_audit_logging()
    for name in TRADING_TOOL_NAMES + WITHDRAWAL_TOOL_NAMES:
        _safe_remove_tool(name)

    want_trading = trading_enabled()
    want_withdrawals = withdrawals_enabled()
    if (want_trading or want_withdrawals) and not destructive_confirm_configured():
        AUDIT_LOGGER.warning(
            "Trading/withdrawal flags are enabled but "
            "COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN is unset; "
            "refusing to register privileged tools."
        )
        return

    if want_trading:
        for name in TRADING_TOOL_NAMES:
            mcp.add_tool(_PRIVILEGED_TOOLS[name], name=name, annotations=_DESTRUCTIVE)

    if want_withdrawals:
        mcp.add_tool(
            get_coin_withdraw_details,
            name="get_coin_withdraw_details",
            annotations=_READ_ONLY,
        )
        mcp.add_tool(withdraw_coin, name="withdraw_coin", annotations=_DESTRUCTIVE)


apply_tool_exposure_policy()


def run() -> None:
    """Run the MCP server over stdio."""
    apply_tool_exposure_policy()
    mcp.run(transport="stdio")
