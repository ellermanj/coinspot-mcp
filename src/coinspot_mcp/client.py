"""Async CoinSpot API v2 client with HMAC-SHA512 authentication."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import time
from typing import Any

import httpx

PUBLIC_BASE = "https://www.coinspot.com.au/pubapi/v2"
FULL_BASE = "https://www.coinspot.com.au/api/v2"
READONLY_BASE = "https://www.coinspot.com.au/api/v2/ro"


class CoinspotError(Exception):
    """Raised when the CoinSpot API returns an error or credentials are missing."""

    def __init__(self, message: str, *, status_code: int | None = None, payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class CoinspotClient:
    """Thin async wrapper around CoinSpot public, read-only, and full-access APIs."""

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        *,
        timeout: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("COINSPOT_API_KEY", "")
        self.api_secret = (
            api_secret if api_secret is not None else os.getenv("COINSPOT_API_SECRET", "")
        )
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._nonce_lock = threading.Lock()
        self._last_nonce = 0

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> CoinspotClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    def _next_nonce(self) -> int:
        # Microsecond timestamps keep nonces monotonic across rapid successive calls.
        candidate = int(time.time() * 1_000_000)
        with self._nonce_lock:
            if candidate <= self._last_nonce:
                candidate = self._last_nonce + 1
            self._last_nonce = candidate
            return candidate

    def _require_credentials(self) -> None:
        if not self.api_key or not self.api_secret:
            raise CoinspotError(
                "Missing CoinSpot credentials. Set COINSPOT_API_KEY and COINSPOT_API_SECRET."
            )

    def _sign(self, body: str) -> str:
        return hmac.new(
            self.api_secret.encode("utf-8"),
            body.encode("utf-8"),
            hashlib.sha512,
        ).hexdigest()

    async def _public_get(self, path: str) -> dict[str, Any]:
        url = f"{PUBLIC_BASE}{path}"
        response = await self._client.get(url)
        return self._parse_response(response)

    async def _authenticated_post(
        self,
        base: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._require_credentials()
        body: dict[str, Any] = dict(payload or {})
        body["nonce"] = self._next_nonce()
        # Compact JSON must match the signed payload byte-for-byte.
        encoded = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
        headers = {
            "Content-Type": "application/json",
            "key": self.api_key,
            "sign": self._sign(encoded),
        }
        response = await self._client.post(f"{base}{path}", content=encoded, headers=headers)
        return self._parse_response(response)

    def _parse_response(self, response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError as exc:
            raise CoinspotError(
                f"Invalid JSON response (HTTP {response.status_code})",
                status_code=response.status_code,
                payload=response.text,
            ) from exc

        if response.status_code != 200:
            message = (
                data.get("message")
                if isinstance(data, dict)
                else None
            ) or f"HTTP {response.status_code}"
            raise CoinspotError(str(message), status_code=response.status_code, payload=data)

        if isinstance(data, dict) and data.get("status") not in (None, "ok"):
            raise CoinspotError(
                str(data.get("message") or data.get("status") or "CoinSpot API error"),
                status_code=response.status_code,
                payload=data,
            )
        if not isinstance(data, dict):
            raise CoinspotError(
                "Unexpected response shape",
                status_code=response.status_code,
                payload=data,
            )
        return data

    @staticmethod
    def _drop_none(payload: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in payload.items() if value is not None}

    # ---- Public API -----------------------------------------------------

    async def latest_prices(self) -> dict[str, Any]:
        return await self._public_get("/latest")

    async def latest_coin_price(self, cointype: str, markettype: str | None = None) -> dict[str, Any]:
        path = f"/latest/{cointype.upper()}"
        if markettype:
            path = f"{path}/{markettype.upper()}"
        return await self._public_get(path)

    async def buy_price(self, cointype: str, markettype: str | None = None) -> dict[str, Any]:
        path = f"/buyprice/{cointype.upper()}"
        if markettype:
            path = f"{path}/{markettype.upper()}"
        return await self._public_get(path)

    async def sell_price(self, cointype: str, markettype: str | None = None) -> dict[str, Any]:
        path = f"/sellprice/{cointype.upper()}"
        if markettype:
            path = f"{path}/{markettype.upper()}"
        return await self._public_get(path)

    async def open_orders(
        self, cointype: str, markettype: str | None = None
    ) -> dict[str, Any]:
        path = f"/orders/open/{cointype.upper()}"
        if markettype:
            path = f"{path}/{markettype.upper()}"
        return await self._public_get(path)

    async def completed_orders(
        self, cointype: str, markettype: str | None = None
    ) -> dict[str, Any]:
        path = f"/orders/completed/{cointype.upper()}"
        if markettype:
            path = f"{path}/{markettype.upper()}"
        return await self._public_get(path)

    async def completed_orders_summary(
        self, cointype: str, markettype: str | None = None
    ) -> dict[str, Any]:
        path = f"/orders/summary/completed/{cointype.upper()}"
        if markettype:
            path = f"{path}/{markettype.upper()}"
        return await self._public_get(path)

    # ---- Read-only API --------------------------------------------------

    async def ro_status(self) -> dict[str, Any]:
        return await self._authenticated_post(READONLY_BASE, "/status")

    async def ro_market_open_orders(
        self, cointype: str, markettype: str | None = None
    ) -> dict[str, Any]:
        return await self._authenticated_post(
            READONLY_BASE,
            "/orders/market/open",
            self._drop_none({"cointype": cointype.upper(), "markettype": _upper_or_none(markettype)}),
        )

    async def ro_market_completed_orders(
        self,
        cointype: str,
        markettype: str | None = None,
        startdate: str | None = None,
        enddate: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        return await self._authenticated_post(
            READONLY_BASE,
            "/orders/market/completed",
            self._drop_none(
                {
                    "cointype": cointype.upper(),
                    "markettype": _upper_or_none(markettype),
                    "startdate": startdate,
                    "enddate": enddate,
                    "limit": limit,
                }
            ),
        )

    async def my_balances(self) -> dict[str, Any]:
        return await self._authenticated_post(READONLY_BASE, "/my/balances")

    async def my_balance(self, cointype: str, available: bool = False) -> dict[str, Any]:
        flag = "yes" if available else "no"
        return await self._authenticated_post(
            READONLY_BASE,
            f"/my/balance/{cointype.upper()}?available={flag}",
        )

    async def my_open_market_orders(
        self, cointype: str | None = None, markettype: str | None = None
    ) -> dict[str, Any]:
        return await self._authenticated_post(
            READONLY_BASE,
            "/my/orders/market/open",
            self._drop_none(
                {
                    "cointype": _upper_or_none(cointype),
                    "markettype": _upper_or_none(markettype),
                }
            ),
        )

    async def my_open_limit_orders(self, cointype: str | None = None) -> dict[str, Any]:
        return await self._authenticated_post(
            READONLY_BASE,
            "/my/orders/limit/open",
            self._drop_none({"cointype": _upper_or_none(cointype)}),
        )

    async def my_order_history(
        self,
        cointype: str | None = None,
        markettype: str | None = None,
        startdate: str | None = None,
        enddate: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        return await self._authenticated_post(
            READONLY_BASE,
            "/my/orders/completed",
            self._drop_none(
                {
                    "cointype": _upper_or_none(cointype),
                    "markettype": _upper_or_none(markettype),
                    "startdate": startdate,
                    "enddate": enddate,
                    "limit": limit,
                }
            ),
        )

    async def my_market_order_history(
        self,
        cointype: str | None = None,
        markettype: str | None = None,
        startdate: str | None = None,
        enddate: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        return await self._authenticated_post(
            READONLY_BASE,
            "/my/orders/market/completed",
            self._drop_none(
                {
                    "cointype": _upper_or_none(cointype),
                    "markettype": _upper_or_none(markettype),
                    "startdate": startdate,
                    "enddate": enddate,
                    "limit": limit,
                }
            ),
        )

    async def my_send_receive(self) -> dict[str, Any]:
        return await self._authenticated_post(READONLY_BASE, "/my/sendreceive")

    async def my_deposits(
        self, startdate: str | None = None, enddate: str | None = None
    ) -> dict[str, Any]:
        return await self._authenticated_post(
            READONLY_BASE,
            "/my/deposits",
            self._drop_none({"startdate": startdate, "enddate": enddate}),
        )

    async def my_withdrawals(
        self, startdate: str | None = None, enddate: str | None = None
    ) -> dict[str, Any]:
        return await self._authenticated_post(
            READONLY_BASE,
            "/my/withdrawals",
            self._drop_none({"startdate": startdate, "enddate": enddate}),
        )

    async def my_affiliate_payments(self) -> dict[str, Any]:
        return await self._authenticated_post(READONLY_BASE, "/my/affiliatepayments")

    async def my_referral_payments(self) -> dict[str, Any]:
        return await self._authenticated_post(READONLY_BASE, "/my/referralpayments")

    # ---- Full-access API ------------------------------------------------

    async def full_status(self) -> dict[str, Any]:
        return await self._authenticated_post(FULL_BASE, "/status")

    async def coin_deposit_address(self, cointype: str) -> dict[str, Any]:
        return await self._authenticated_post(
            FULL_BASE,
            "/my/coin/deposit",
            {"cointype": cointype.upper()},
        )

    async def buy_now_coin_list(self) -> dict[str, Any]:
        return await self._authenticated_post(FULL_BASE, "/my/buy/now/coinlist")

    async def sell_now_coin_list(self) -> dict[str, Any]:
        return await self._authenticated_post(FULL_BASE, "/my/sell/now/coinlist")

    async def quote_buy_now(
        self, cointype: str, amount: float | str, amounttype: str = "coin"
    ) -> dict[str, Any]:
        return await self._authenticated_post(
            FULL_BASE,
            "/quote/buy/now",
            {
                "cointype": cointype.upper(),
                "amount": amount,
                "amounttype": amounttype.lower(),
            },
        )

    async def quote_sell_now(
        self, cointype: str, amount: float | str, amounttype: str = "coin"
    ) -> dict[str, Any]:
        return await self._authenticated_post(
            FULL_BASE,
            "/quote/sell/now",
            {
                "cointype": cointype.upper(),
                "amount": amount,
                "amounttype": amounttype.lower(),
            },
        )

    async def quote_swap_now(
        self, cointypesell: str, cointypebuy: str, amount: float | str
    ) -> dict[str, Any]:
        return await self._authenticated_post(
            FULL_BASE,
            "/quote/swap/now",
            {
                "cointypesell": cointypesell.upper(),
                "cointypebuy": cointypebuy.upper(),
                "amount": amount,
            },
        )

    async def place_buy_order(
        self,
        cointype: str,
        amount: float | str,
        rate: float | str,
        markettype: str | None = None,
    ) -> dict[str, Any]:
        return await self._authenticated_post(
            FULL_BASE,
            "/my/buy",
            self._drop_none(
                {
                    "cointype": cointype.upper(),
                    "amount": amount,
                    "rate": rate,
                    "markettype": _upper_or_none(markettype),
                }
            ),
        )

    async def edit_buy_order(
        self,
        cointype: str,
        order_id: str,
        rate: float | str,
        newrate: float | str,
    ) -> dict[str, Any]:
        return await self._authenticated_post(
            FULL_BASE,
            "/my/buy/edit",
            {
                "cointype": cointype.upper(),
                "id": order_id,
                "rate": rate,
                "newrate": newrate,
            },
        )

    async def place_buy_now(
        self,
        cointype: str,
        amount: float | str,
        amounttype: str = "coin",
        rate: float | str | None = None,
        threshold: float | str | None = None,
        direction: str | None = None,
    ) -> dict[str, Any]:
        return await self._authenticated_post(
            FULL_BASE,
            "/my/buy/now",
            self._drop_none(
                {
                    "cointype": cointype.upper(),
                    "amount": amount,
                    "amounttype": amounttype.lower(),
                    "rate": rate,
                    "threshold": threshold,
                    "direction": _upper_or_none(direction),
                }
            ),
        )

    async def place_sell_order(
        self,
        cointype: str,
        amount: float | str,
        rate: float | str,
        markettype: str | None = None,
    ) -> dict[str, Any]:
        return await self._authenticated_post(
            FULL_BASE,
            "/my/sell",
            self._drop_none(
                {
                    "cointype": cointype.upper(),
                    "amount": amount,
                    "rate": rate,
                    "markettype": _upper_or_none(markettype),
                }
            ),
        )

    async def edit_sell_order(
        self,
        cointype: str,
        order_id: str,
        rate: float | str,
        newrate: float | str,
    ) -> dict[str, Any]:
        return await self._authenticated_post(
            FULL_BASE,
            "/my/sell/edit",
            {
                "cointype": cointype.upper(),
                "id": order_id,
                "rate": rate,
                "newrate": newrate,
            },
        )

    async def place_sell_now(
        self,
        cointype: str,
        amount: float | str,
        amounttype: str = "coin",
        rate: float | str | None = None,
        threshold: float | str | None = None,
        direction: str | None = None,
    ) -> dict[str, Any]:
        return await self._authenticated_post(
            FULL_BASE,
            "/my/sell/now",
            self._drop_none(
                {
                    "cointype": cointype.upper(),
                    "amount": amount,
                    "amounttype": amounttype.lower(),
                    "rate": rate,
                    "threshold": threshold,
                    "direction": _upper_or_none(direction),
                }
            ),
        )

    async def place_swap_now(
        self,
        cointypesell: str,
        cointypebuy: str,
        amount: float | str,
        rate: float | str | None = None,
        threshold: float | str | None = None,
        direction: str | None = None,
    ) -> dict[str, Any]:
        return await self._authenticated_post(
            FULL_BASE,
            "/my/swap/now",
            self._drop_none(
                {
                    "cointypesell": cointypesell.upper(),
                    "cointypebuy": cointypebuy.upper(),
                    "amount": amount,
                    "rate": rate,
                    "threshold": threshold,
                    "direction": _upper_or_none(direction),
                }
            ),
        )

    async def cancel_buy_order(self, order_id: str) -> dict[str, Any]:
        return await self._authenticated_post(FULL_BASE, "/my/buy/cancel", {"id": order_id})

    async def cancel_all_buy_orders(self, coin: str | None = None) -> dict[str, Any]:
        return await self._authenticated_post(
            FULL_BASE,
            "/my/buy/cancel/all",
            self._drop_none({"coin": _upper_or_none(coin)}),
        )

    async def cancel_sell_order(self, order_id: str) -> dict[str, Any]:
        return await self._authenticated_post(FULL_BASE, "/my/sell/cancel", {"id": order_id})

    async def cancel_all_sell_orders(self, coin: str | None = None) -> dict[str, Any]:
        return await self._authenticated_post(
            FULL_BASE,
            "/my/sell/cancel/all",
            self._drop_none({"coin": _upper_or_none(coin)}),
        )

    async def coin_withdraw_details(self, cointype: str) -> dict[str, Any]:
        return await self._authenticated_post(
            FULL_BASE,
            "/my/coin/withdraw/senddetails",
            {"cointype": cointype.upper()},
        )

    async def coin_withdraw(
        self,
        cointype: str,
        amount: float | str,
        address: str,
        *,
        emailconfirm: str = "YES",
        network: str | None = None,
        paymentid: str | None = None,
    ) -> dict[str, Any]:
        return await self._authenticated_post(
            FULL_BASE,
            "/my/coin/withdraw/send",
            self._drop_none(
                {
                    "cointype": cointype.upper(),
                    "amount": amount,
                    "address": address,
                    "emailconfirm": emailconfirm.upper(),
                    "network": network,
                    "paymentid": paymentid,
                }
            ),
        )


def _upper_or_none(value: str | None) -> str | None:
    return value.upper() if value else None


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}
