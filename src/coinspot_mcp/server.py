"""CoinSpot MCP server exposing public, read-only, and trading tools."""

from __future__ import annotations

import json
from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from coinspot_mcp.client import CoinspotClient, CoinspotError, env_flag

mcp = MCPServer(
    name="coinspot",
    title="CoinSpot Australia",
    description="Access the CoinSpot Australia cryptocurrency exchange API (v2).",
    instructions=(
        "Use public tools for market prices and order books without credentials. "
        "Use read-only tools for balances and account history when COINSPOT_API_KEY "
        "and COINSPOT_API_SECRET are configured. Trading and withdrawal tools require "
        "extra environment flags and a full-access API key."
    ),
    website_url="https://www.coinspot.com.au/v2/api",
    version="0.1.0",
)


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)


async def _call(coro) -> str:
    try:
        result = await coro
        return _json(result)
    except CoinspotError as exc:
        payload = {"status": "error", "message": str(exc)}
        if exc.payload is not None:
            payload["details"] = exc.payload
        return _json(payload)


def _require_trading() -> None:
    if not env_flag("COINSPOT_ALLOW_TRADING"):
        raise CoinspotError(
            "Trading tools are disabled. Set COINSPOT_ALLOW_TRADING=true to enable "
            "place/edit/cancel order tools."
        )


def _require_withdrawals() -> None:
    if not env_flag("COINSPOT_ALLOW_WITHDRAWALS"):
        raise CoinspotError(
            "Withdrawal tools are disabled. Set COINSPOT_ALLOW_WITHDRAWALS=true to enable "
            "them, and enable withdrawals on the CoinSpot API key."
        )


def get_client() -> CoinspotClient:
    return CoinspotClient()


# ---- Public tools -------------------------------------------------------


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def get_latest_prices() -> str:
    """Get latest buy/ask/last prices for all CoinSpot markets."""
    async with get_client() as client:
        return await _call(client.latest_prices())


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def get_latest_coin_price(cointype: str, markettype: str | None = None) -> str:
    """Get latest prices for a coin, optionally against a market (e.g. USDT).

    Args:
        cointype: Coin ticker such as BTC, ETH, or DOGE.
        markettype: Optional market ticker such as USDT. Defaults to AUD.
    """
    async with get_client() as client:
        return await _call(client.latest_coin_price(cointype, markettype))


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def get_buy_price(cointype: str, markettype: str | None = None) -> str:
    """Get the latest buy price for a coin.

    Args:
        cointype: Coin ticker such as BTC.
        markettype: Optional market ticker such as USDT.
    """
    async with get_client() as client:
        return await _call(client.buy_price(cointype, markettype))


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def get_sell_price(cointype: str, markettype: str | None = None) -> str:
    """Get the latest sell price for a coin.

    Args:
        cointype: Coin ticker such as BTC.
        markettype: Optional market ticker such as USDT.
    """
    async with get_client() as client:
        return await _call(client.sell_price(cointype, markettype))


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def get_open_orders(cointype: str, markettype: str | None = None) -> str:
    """List public open buy/sell orders for a coin market.

    Args:
        cointype: Coin ticker such as BTC.
        markettype: Optional market ticker such as USDT.
    """
    async with get_client() as client:
        return await _call(client.open_orders(cointype, markettype))


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def get_completed_orders(cointype: str, markettype: str | None = None) -> str:
    """List recent completed public buy/sell orders for a coin market.

    Args:
        cointype: Coin ticker such as BTC.
        markettype: Optional market ticker such as USDT.
    """
    async with get_client() as client:
        return await _call(client.completed_orders(cointype, markettype))


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def get_completed_orders_summary(cointype: str, markettype: str | None = None) -> str:
    """List recent completed public orders as a combined summary.

    Args:
        cointype: Coin ticker such as BTC.
        markettype: Optional market ticker such as USDT.
    """
    async with get_client() as client:
        return await _call(client.completed_orders_summary(cointype, markettype))


# ---- Read-only account tools --------------------------------------------


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def check_readonly_status() -> str:
    """Check that the configured read-only/full API credentials are working."""
    async with get_client() as client:
        return await _call(client.ro_status())


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def get_my_balances() -> str:
    """List all coin balances with AUD value and rate."""
    async with get_client() as client:
        return await _call(client.my_balances())


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def get_my_balance(cointype: str, available: bool = False) -> str:
    """Get balance details for a single coin.

    Args:
        cointype: Coin ticker such as BTC or AUD.
        available: If true, also return the available (unlocked) balance.
    """
    async with get_client() as client:
        return await _call(client.my_balance(cointype, available=available))


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def get_my_open_market_orders(
    cointype: str | None = None, markettype: str | None = None
) -> str:
    """List your open market orders.

    Args:
        cointype: Optional coin ticker filter.
        markettype: Optional market ticker filter such as AUD or USDT.
    """
    async with get_client() as client:
        return await _call(client.my_open_market_orders(cointype, markettype))


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def get_my_open_limit_orders(cointype: str | None = None) -> str:
    """List your open limit/stop orders.

    Args:
        cointype: Optional coin ticker filter.
    """
    async with get_client() as client:
        return await _call(client.my_open_limit_orders(cointype))


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
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
    async with get_client() as client:
        return await _call(
            client.my_order_history(cointype, markettype, startdate, enddate, limit)
        )


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
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
    async with get_client() as client:
        return await _call(
            client.my_market_order_history(cointype, markettype, startdate, enddate, limit)
        )


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def get_my_send_receive_history() -> str:
    """List your coin send and receive transaction history."""
    async with get_client() as client:
        return await _call(client.my_send_receive())


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def get_my_deposits(startdate: str | None = None, enddate: str | None = None) -> str:
    """List your AUD deposit history.

    Args:
        startdate: Optional UTC start date YYYY-MM-DD or UNIX epoch.
        enddate: Optional UTC end date YYYY-MM-DD or UNIX epoch.
    """
    async with get_client() as client:
        return await _call(client.my_deposits(startdate, enddate))


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def get_my_withdrawals(startdate: str | None = None, enddate: str | None = None) -> str:
    """List your AUD withdrawal history.

    Args:
        startdate: Optional UTC start date YYYY-MM-DD or UNIX epoch.
        enddate: Optional UTC end date YYYY-MM-DD or UNIX epoch.
    """
    async with get_client() as client:
        return await _call(client.my_withdrawals(startdate, enddate))


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def get_my_affiliate_payments() -> str:
    """List completed affiliate payments."""
    async with get_client() as client:
        return await _call(client.my_affiliate_payments())


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def get_my_referral_payments() -> str:
    """List completed referral payments."""
    async with get_client() as client:
        return await _call(client.my_referral_payments())


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def get_readonly_market_open_orders(cointype: str, markettype: str | None = None) -> str:
    """List open market orders via the authenticated read-only API.

    Args:
        cointype: Coin ticker such as BTC.
        markettype: Optional market ticker such as AUD or USDT.
    """
    async with get_client() as client:
        return await _call(client.ro_market_open_orders(cointype, markettype))


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
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
    async with get_client() as client:
        return await _call(
            client.ro_market_completed_orders(
                cointype, markettype, startdate, enddate, limit
            )
        )


# ---- Full-access / quote tools ------------------------------------------


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def check_full_access_status() -> str:
    """Check that the configured full-access API credentials are working."""
    async with get_client() as client:
        return await _call(client.full_status())


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def get_coin_deposit_address(cointype: str) -> str:
    """Get deposit networks and addresses for a coin.

    Args:
        cointype: Coin ticker such as BTC.
    """
    async with get_client() as client:
        return await _call(client.coin_deposit_address(cointype))


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def get_buy_now_coin_list() -> str:
    """List coins available for Buy Now."""
    async with get_client() as client:
        return await _call(client.buy_now_coin_list())


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def get_sell_now_coin_list() -> str:
    """List coins available for Sell/Swap Now."""
    async with get_client() as client:
        return await _call(client.sell_now_coin_list())


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def quote_buy_now(cointype: str, amount: float, amounttype: str = "coin") -> str:
    """Get a Buy Now quote.

    Args:
        cointype: Coin ticker such as BTC.
        amount: Amount to buy.
        amounttype: Whether amount is 'coin' or 'aud'.
    """
    async with get_client() as client:
        return await _call(client.quote_buy_now(cointype, amount, amounttype))


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def quote_sell_now(cointype: str, amount: float, amounttype: str = "coin") -> str:
    """Get a Sell Now quote.

    Args:
        cointype: Coin ticker such as BTC.
        amount: Amount to sell.
        amounttype: Whether amount is 'coin' or 'aud'.
    """
    async with get_client() as client:
        return await _call(client.quote_sell_now(cointype, amount, amounttype))


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def quote_swap_now(cointypesell: str, cointypebuy: str, amount: float) -> str:
    """Get a Swap Now quote.

    Args:
        cointypesell: Coin ticker to sell/swap from.
        cointypebuy: Coin ticker to receive.
        amount: Amount of the sell coin to swap.
    """
    async with get_client() as client:
        return await _call(client.quote_swap_now(cointypesell, cointypebuy, amount))


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        open_world_hint=True,
    ),
)
async def place_buy_order(
    cointype: str,
    amount: float,
    rate: float,
    markettype: str | None = None,
) -> str:
    """Place a limit/market buy order. Requires COINSPOT_ALLOW_TRADING=true.

    Args:
        cointype: Coin ticker such as BTC.
        amount: Coin amount to buy.
        rate: Limit rate in market currency.
        markettype: Optional market ticker (default AUD).
    """
    try:
        _require_trading()
    except CoinspotError as exc:
        return _json({"status": "error", "message": str(exc)})
    async with get_client() as client:
        return await _call(client.place_buy_order(cointype, amount, rate, markettype))


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        open_world_hint=True,
    ),
)
async def edit_buy_order(cointype: str, order_id: str, rate: float, newrate: float) -> str:
    """Edit an open buy order rate. Requires COINSPOT_ALLOW_TRADING=true.

    Args:
        cointype: Coin ticker.
        order_id: Existing buy order id.
        rate: Current order rate.
        newrate: Proposed new rate.
    """
    try:
        _require_trading()
    except CoinspotError as exc:
        return _json({"status": "error", "message": str(exc)})
    async with get_client() as client:
        return await _call(client.edit_buy_order(cointype, order_id, rate, newrate))


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        open_world_hint=True,
    ),
)
async def place_buy_now(
    cointype: str,
    amount: float,
    amounttype: str = "coin",
    rate: float | None = None,
    threshold: float | None = None,
    direction: str | None = None,
) -> str:
    """Place a Buy Now (instant) order. Requires COINSPOT_ALLOW_TRADING=true.

    Args:
        cointype: Coin ticker.
        amount: Amount to buy.
        amounttype: 'coin' or 'aud'.
        rate: Optional quote rate used with threshold.
        threshold: Optional max percent deviation from rate.
        direction: Optional UP, DOWN, or BOTH.
    """
    try:
        _require_trading()
    except CoinspotError as exc:
        return _json({"status": "error", "message": str(exc)})
    async with get_client() as client:
        return await _call(
            client.place_buy_now(cointype, amount, amounttype, rate, threshold, direction)
        )


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        open_world_hint=True,
    ),
)
async def place_sell_order(
    cointype: str,
    amount: float,
    rate: float,
    markettype: str | None = None,
) -> str:
    """Place a limit/market sell order. Requires COINSPOT_ALLOW_TRADING=true.

    Args:
        cointype: Coin ticker.
        amount: Coin amount to sell.
        rate: Limit rate in market currency.
        markettype: Optional market ticker (default AUD).
    """
    try:
        _require_trading()
    except CoinspotError as exc:
        return _json({"status": "error", "message": str(exc)})
    async with get_client() as client:
        return await _call(client.place_sell_order(cointype, amount, rate, markettype))


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        open_world_hint=True,
    ),
)
async def edit_sell_order(cointype: str, order_id: str, rate: float, newrate: float) -> str:
    """Edit an open sell order rate. Requires COINSPOT_ALLOW_TRADING=true.

    Args:
        cointype: Coin ticker.
        order_id: Existing sell order id.
        rate: Current order rate.
        newrate: Proposed new rate.
    """
    try:
        _require_trading()
    except CoinspotError as exc:
        return _json({"status": "error", "message": str(exc)})
    async with get_client() as client:
        return await _call(client.edit_sell_order(cointype, order_id, rate, newrate))


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        open_world_hint=True,
    ),
)
async def place_sell_now(
    cointype: str,
    amount: float,
    amounttype: str = "coin",
    rate: float | None = None,
    threshold: float | None = None,
    direction: str | None = None,
) -> str:
    """Place a Sell Now (instant) order. Requires COINSPOT_ALLOW_TRADING=true.

    Args:
        cointype: Coin ticker.
        amount: Amount to sell.
        amounttype: 'coin' or 'aud'.
        rate: Optional quote rate used with threshold.
        threshold: Optional max percent deviation from rate.
        direction: Optional UP, DOWN, or BOTH.
    """
    try:
        _require_trading()
    except CoinspotError as exc:
        return _json({"status": "error", "message": str(exc)})
    async with get_client() as client:
        return await _call(
            client.place_sell_now(cointype, amount, amounttype, rate, threshold, direction)
        )


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        open_world_hint=True,
    ),
)
async def place_swap_now(
    cointypesell: str,
    cointypebuy: str,
    amount: float,
    rate: float | None = None,
    threshold: float | None = None,
    direction: str | None = None,
) -> str:
    """Place a Swap Now order. Requires COINSPOT_ALLOW_TRADING=true.

    Args:
        cointypesell: Coin ticker to sell/swap from.
        cointypebuy: Coin ticker to receive.
        amount: Amount of sell coin.
        rate: Optional quote rate used with threshold.
        threshold: Optional max percent deviation from rate.
        direction: Optional UP, DOWN, or BOTH.
    """
    try:
        _require_trading()
    except CoinspotError as exc:
        return _json({"status": "error", "message": str(exc)})
    async with get_client() as client:
        return await _call(
            client.place_swap_now(
                cointypesell, cointypebuy, amount, rate, threshold, direction
            )
        )


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        open_world_hint=True,
    ),
)
async def cancel_buy_order(order_id: str) -> str:
    """Cancel an open buy order. Requires COINSPOT_ALLOW_TRADING=true.

    Args:
        order_id: Buy order id to cancel.
    """
    try:
        _require_trading()
    except CoinspotError as exc:
        return _json({"status": "error", "message": str(exc)})
    async with get_client() as client:
        return await _call(client.cancel_buy_order(order_id))


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        open_world_hint=True,
    ),
)
async def cancel_all_buy_orders(coin: str | None = None) -> str:
    """Cancel all open buy orders, optionally filtered by coin.

    Requires COINSPOT_ALLOW_TRADING=true.

    Args:
        coin: Optional coin ticker filter.
    """
    try:
        _require_trading()
    except CoinspotError as exc:
        return _json({"status": "error", "message": str(exc)})
    async with get_client() as client:
        return await _call(client.cancel_all_buy_orders(coin))


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        open_world_hint=True,
    ),
)
async def cancel_sell_order(order_id: str) -> str:
    """Cancel an open sell order. Requires COINSPOT_ALLOW_TRADING=true.

    Args:
        order_id: Sell order id to cancel.
    """
    try:
        _require_trading()
    except CoinspotError as exc:
        return _json({"status": "error", "message": str(exc)})
    async with get_client() as client:
        return await _call(client.cancel_sell_order(order_id))


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        open_world_hint=True,
    ),
)
async def cancel_all_sell_orders(coin: str | None = None) -> str:
    """Cancel all open sell orders, optionally filtered by coin.

    Requires COINSPOT_ALLOW_TRADING=true.

    Args:
        coin: Optional coin ticker filter.
    """
    try:
        _require_trading()
    except CoinspotError as exc:
        return _json({"status": "error", "message": str(exc)})
    async with get_client() as client:
        return await _call(client.cancel_all_sell_orders(coin))


@mcp.tool(
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def get_coin_withdraw_details(cointype: str) -> str:
    """Get withdrawal networks, fees, and minimums for a coin.

    Requires the CoinSpot API key withdrawal permission.

    Args:
        cointype: Coin ticker such as BTC.
    """
    async with get_client() as client:
        return await _call(client.coin_withdraw_details(cointype))


@mcp.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        open_world_hint=True,
    ),
)
async def withdraw_coin(
    cointype: str,
    amount: float,
    address: str,
    emailconfirm: str = "YES",
    network: str | None = None,
    paymentid: str | None = None,
) -> str:
    """Withdraw coins to an external address.

    Requires COINSPOT_ALLOW_WITHDRAWALS=true and withdrawal permission on the API key.
    Defaults emailconfirm to YES so CoinSpot emails a confirmation link.

    Args:
        cointype: Coin ticker.
        amount: Amount to withdraw.
        address: Destination address.
        emailconfirm: YES (default) or NO.
        network: Optional network such as ETH or BSC.
        paymentid: Optional memo/payment id where required.
    """
    try:
        _require_withdrawals()
    except CoinspotError as exc:
        return _json({"status": "error", "message": str(exc)})
    async with get_client() as client:
        return await _call(
            client.coin_withdraw(
                cointype,
                amount,
                address,
                emailconfirm=emailconfirm,
                network=network,
                paymentid=paymentid,
            )
        )


def run() -> None:
    """Run the MCP server over stdio."""
    mcp.run(transport="stdio")
