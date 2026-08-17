from __future__ import annotations

from typing import Any, Optional

import httpx

from app.config import Settings


class BinanceClient:
    """
    RR Trader Binance market-data client.

    Supports:
    - Binance Futures
    - Binance Spot
    - Exchange information
    - 24h ticker
    - Klines/candles
    - Order book
    - Funding rate
    - Open interest
    - Recent liquidation orders
    """

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings()

        self.futures_url = self.settings.binance_futures_url.rstrip("/")
        self.spot_url = self.settings.binance_spot_url.rstrip("/")
        self.timeout = self.settings.request_timeout

        self.headers = {
            "User-Agent": "RR-Trader/1.0",
            "Accept": "application/json",
        }

    def _base_url(self, market: str) -> str:
        market = market.lower().strip()

        if market == "futures":
            return self.futures_url

        if market == "spot":
            return self.spot_url

        raise ValueError("market must be 'spot' or 'futures'")

    async def _request(
        self,
        method: str,
        url: str,
        params: Optional[dict[str, Any]] = None,
    ) -> Any:
        async with httpx.AsyncClient(
            timeout=self.timeout,
            headers=self.headers,
        ) as client:
            response = await client.request(
                method=method,
                url=url,
                params=params,
            )

            response.raise_for_status()
            return response.json()

    # ---------------------------------------------------------
    # EXCHANGE INFORMATION
    # ---------------------------------------------------------

    async def exchange_info(self, market: str = "futures") -> dict[str, Any]:
        base = self._base_url(market)

        endpoint = (
            "/fapi/v1/exchangeInfo"
            if market.lower() == "futures"
            else "/api/v3/exchangeInfo"
        )

        return await self._request(
            "GET",
            f"{base}{endpoint}",
        )

    # ---------------------------------------------------------
    # 24H TICKER
    # ---------------------------------------------------------

    async def ticker_24h(
        self,
        market: str = "futures",
        symbol: Optional[str] = None,
    ) -> Any:
        base = self._base_url(market)

        endpoint = (
            "/fapi/v1/ticker/24hr"
            if market.lower() == "futures"
            else "/api/v3/ticker/24hr"
        )

        params = {}

        if symbol:
            params["symbol"] = symbol.upper()

        return await self._request(
            "GET",
            f"{base}{endpoint}",
            params=params,
        )

    # ---------------------------------------------------------
    # KLINES / CANDLES
    # ---------------------------------------------------------

    async def klines(
        self,
        symbol: str,
        interval: str = "15m",
        limit: int = 200,
        market: str = "futures",
    ) -> list[list[Any]]:
        base = self._base_url(market)

        endpoint = (
            "/fapi/v1/klines"
            if market.lower() == "futures"
            else "/api/v3/klines"
        )

        params = {
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": limit,
        }

        return await self._request(
            "GET",
            f"{base}{endpoint}",
            params=params,
        )

    # ---------------------------------------------------------
    # ORDER BOOK / DEPTH
    # ---------------------------------------------------------

    async def depth(
        self,
        symbol: str,
        limit: int = 100,
        market: str = "futures",
    ) -> dict[str, Any]:
        base = self._base_url(market)

        endpoint = (
            "/fapi/v1/depth"
            if market.lower() == "futures"
            else "/api/v3/depth"
        )

        params = {
            "symbol": symbol.upper(),
            "limit": limit,
        }

        return await self._request(
            "GET",
            f"{base}{endpoint}",
            params=params,
        )

    # ---------------------------------------------------------
    # FUTURES FUNDING RATE
    # ---------------------------------------------------------

    async def funding_rate(
        self,
        symbol: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        base = self.futures_url

        return await self._request(
            "GET",
            f"{base}/fapi/v1/fundingRate",
            params={
                "symbol": symbol.upper(),
                "limit": limit,
            },
        )

    # ---------------------------------------------------------
    # FUTURES OPEN INTEREST
    # ---------------------------------------------------------

    async def open_interest(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"{self.futures_url}/fapi/v1/openInterest",
            params={
                "symbol": symbol.upper(),
            },
        )

    # ---------------------------------------------------------
    # FUTURES OPEN INTEREST HISTORY
    # ---------------------------------------------------------

    async def open_interest_history(
        self,
        symbol: str,
        period: str = "5m",
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        return await self._request(
            "GET",
            f"{self.futures_url}/futures/data/openInterestHist",
            params={
                "symbol": symbol.upper(),
                "period": period,
                "limit": limit,
            },
        )

    # ---------------------------------------------------------
    # FUTURES LONG / SHORT RATIO
    # ---------------------------------------------------------

    async def global_long_short_ratio(
        self,
        symbol: str,
        period: str = "5m",
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        return await self._request(
            "GET",
            f"{self.futures_url}/futures/data/globalLongShortAccountRatio",
            params={
                "symbol": symbol.upper(),
                "period": period,
                "limit": limit,
            },
        )

    # ---------------------------------------------------------
    # TOP TRADER LONG / SHORT RATIO
    # ---------------------------------------------------------

    async def top_trader_long_short_ratio(
        self,
        symbol: str,
        period: str = "5m",
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        return await self._request(
            "GET",
            f"{self.futures_url}/futures/data/topLongShortAccountRatio",
            params={
                "symbol": symbol.upper(),
                "period": period,
                "limit": limit,
            },
        )

    # ---------------------------------------------------------
    # RECENT LIQUIDATION ORDERS
    # ---------------------------------------------------------

    async def liquidation_orders(
        self,
        symbol: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        params = {
            "limit": limit,
        }

        if symbol:
            params["symbol"] = symbol.upper()

        return await self._request(
            "GET",
            f"{self.futures_url}/fapi/v1/allForceOrders",
            params=params,
        )

    # ---------------------------------------------------------
    # PRICE
    # ---------------------------------------------------------

    async def price(
        self,
        symbol: str,
        market: str = "futures",
    ) -> dict[str, Any]:
        base = self._base_url(market)

        endpoint = (
            "/fapi/v1/ticker/price"
            if market.lower() == "futures"
            else "/api/v3/ticker/price"
        )

        return await self._request(
            "GET",
            f"{base}{endpoint}",
            params={
                "symbol": symbol.upper(),
            },
        )

    # ---------------------------------------------------------
    # SERVER TIME
    # ---------------------------------------------------------

    async def server_time(
        self,
        market: str = "futures",
    ) -> dict[str, Any]:
        base = self._base_url(market)

        endpoint = (
            "/fapi/v1/time"
            if market.lower() == "futures"
            else "/api/v3/time"
        )

        return await self._request(
            "GET",
            f"{base}{endpoint}",
        )

    # ---------------------------------------------------------
    # CLOSE CLIENT
    # ---------------------------------------------------------

    async def close(self) -> None:
        """
        Reserved for future persistent HTTP client support.
        """
        return None


__all__ = ["BinanceClient"]
