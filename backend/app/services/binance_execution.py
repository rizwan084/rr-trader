from __future__ import annotations

import hashlib
import hmac
import math
import time
from decimal import Decimal, ROUND_DOWN
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import settings


class BinanceExecutionError(RuntimeError):
    pass


class BinanceExecutionClient:
    """Small, isolated Binance USD-M Futures execution client.

    It is deliberately separate from the existing market-data client. No live
    order can be sent unless LIVE_TRADING_ENABLED=true and TRADING_MODE=live.
    """

    def __init__(self) -> None:
        self.base_url = settings.binance_futures_url.rstrip("/")
        self.api_key = settings.binance_api_key.strip()
        self.api_secret = settings.binance_api_secret.strip()
        self.timeout = settings.request_timeout

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.api_secret)

    @property
    def live_enabled(self) -> bool:
        return bool(settings.live_trading_enabled and settings.trading_mode == "live")

    def _assert_live(self) -> None:
        if not self.live_enabled:
            raise BinanceExecutionError("Live execution is disabled. Set TRADING_MODE=live and LIVE_TRADING_ENABLED=true.")
        if not self.configured:
            raise BinanceExecutionError("BINANCE_API_KEY/BINANCE_API_SECRET are not configured.")

    @staticmethod
    def _clean_params(params: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in params.items() if v is not None}

    def _signed_params(self, params: dict[str, Any]) -> dict[str, Any]:
        payload = self._clean_params(dict(params))
        payload.setdefault("recvWindow", settings.binance_recv_window)
        payload["timestamp"] = int(time.time() * 1000)
        query = urlencode(payload, doseq=True)
        signature = hmac.new(self.api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        payload["signature"] = signature
        return payload

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        signed: bool = False,
    ) -> Any:
        headers = {"Accept": "application/json"}
        if signed:
            self._assert_live()
            headers["X-MBX-APIKEY"] = self.api_key
            payload = self._signed_params(params or {})
        else:
            payload = self._clean_params(params or {})

        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=self.timeout, headers=headers) as client:
            response = await client.request(method, url, params=payload)

        try:
            data = response.json()
        except Exception:
            data = {"status_code": response.status_code, "text": response.text[:500]}

        if response.status_code >= 400:
            raise BinanceExecutionError(f"Binance API {response.status_code}: {data}")
        return data

    async def account(self) -> dict[str, Any]:
        return await self._request("GET", "/fapi/v2/account", signed=True)

    async def position_risk(self, symbol: str | None = None) -> Any:
        return await self._request("GET", "/fapi/v2/positionRisk", params={"symbol": symbol}, signed=True)

    async def open_orders(self, symbol: str | None = None) -> Any:
        return await self._request("GET", "/fapi/v1/openOrders", params={"symbol": symbol}, signed=True)

    async def order_status(self, symbol: str, order_id: int | str) -> dict[str, Any]:
        return await self._request("GET", "/fapi/v1/order", params={"symbol": symbol, "orderId": order_id}, signed=True)

    async def set_leverage(self, symbol: str, leverage: int) -> dict[str, Any]:
        leverage = max(1, min(int(leverage), settings.max_leverage))
        return await self._request("POST", "/fapi/v1/leverage", params={"symbol": symbol.upper(), "leverage": leverage}, signed=True)

    async def exchange_info(self) -> dict[str, Any]:
        # Public endpoint; useful for quantity/price filters before a live order.
        return await self._request("GET", "/fapi/v1/exchangeInfo")

    async def new_order(self, **params: Any) -> dict[str, Any]:
        params.setdefault("newOrderRespType", "RESULT")
        return await self._request("POST", "/fapi/v1/order", params=params, signed=True)

    async def cancel_order(self, symbol: str, order_id: int | str) -> dict[str, Any]:
        return await self._request("DELETE", "/fapi/v1/order", params={"symbol": symbol.upper(), "orderId": order_id}, signed=True)

    async def cancel_all_orders(self, symbol: str) -> dict[str, Any]:
        return await self._request("DELETE", "/fapi/v1/allOpenOrders", params={"symbol": symbol.upper()}, signed=True)

    async def normalize_order_quantity(self, symbol: str, quantity: float) -> float:
        info = await self.exchange_info()
        row = next((x for x in info.get("symbols", []) if x.get("symbol") == symbol.upper()), None)
        if not row:
            raise BinanceExecutionError(f"Binance symbol not found: {symbol}")

        filters = {f.get("filterType"): f for f in row.get("filters", [])}
        lot = filters.get("MARKET_LOT_SIZE") or filters.get("LOT_SIZE") or {}
        step = Decimal(str(lot.get("stepSize", "0")))
        minimum = Decimal(str(lot.get("minQty", "0")))
        maximum = Decimal(str(lot.get("maxQty", "0")))
        value = Decimal(str(max(quantity, 0)))
        if step > 0:
            value = (value / step).to_integral_value(rounding=ROUND_DOWN) * step
        if minimum > 0 and value < minimum:
            raise BinanceExecutionError(f"Calculated quantity {value} is below Binance minimum {minimum} for {symbol}.")
        if maximum > 0 and value > maximum:
            value = maximum
        return float(value)

    async def normalize_price(self, symbol: str, price: float) -> float:
        info = await self.exchange_info()
        row = next((x for x in info.get("symbols", []) if x.get("symbol") == symbol.upper()), None)
        if not row:
            raise BinanceExecutionError(f"Binance symbol not found: {symbol}")
        filters = {f.get("filterType"): f for f in row.get("filters", [])}
        price_filter = filters.get("PRICE_FILTER", {})
        tick = Decimal(str(price_filter.get("tickSize", "0")))
        value = Decimal(str(price))
        if tick > 0:
            value = (value / tick).to_integral_value(rounding=ROUND_DOWN) * tick
        return float(value)


binance_execution_client = BinanceExecutionClient()
