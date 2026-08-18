from __future__ import annotations

import asyncio
import random
from typing import Any, Optional

import httpx

from ..config import Settings


class BinanceClient:
    """
    RR Trader Binance market-data client.

    Supports:
    - Binance Futures
    - Binance Spot
    - Exchange information
    - 24h ticker
    - Klines / candles
    - Order book
    - Funding rate
    - Open interest
    - Open interest history
    - Global long / short ratio
    - Top trader long / short ratio
    - Recent liquidation orders
    - Price
    - Server time
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
    ) -> None:

        self.settings = (
            settings or Settings()
        )

        self.futures_url = (
            self.settings.binance_futures_url
            .rstrip("/")
        )

        self.spot_url = (
            self.settings.binance_spot_url
            .rstrip("/")
        )

        self.timeout = (
            self.settings.request_timeout
        )

        self.headers = {
            "User-Agent": "RR-Trader/1.0",
            "Accept": "application/json",
        }

        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            headers=self.headers,
            limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10,
            ),
        )

        self._request_semaphore = asyncio.Semaphore(8)
        self._ticker_cache: dict[str, tuple[float, Any]] = {}
        self._ticker_cache_ttl = 15.0

    # =========================================================
    # BASE URL
    # =========================================================

    def _base_url(
        self,
        market: str,
    ) -> str:

        market = (
            market
            .lower()
            .strip()
        )

        if market == "futures":
            return self.futures_url

        if market == "spot":
            return self.spot_url

        raise ValueError(
            "market must be 'spot' or 'futures'"
        )

    # =========================================================
    # HTTP REQUEST
    # =========================================================

    async def _request(
        self,
        method: str,
        url: str,
        params: Optional[
            dict[str, Any]
        ] = None,
    ) -> Any:
        """Rate-limited Binance request with retry/backoff for 429/418."""

        last_error: Optional[Exception] = None

        for attempt in range(5):
            try:
                async with self._request_semaphore:
                    response = await self._client.request(
                        method=method,
                        url=url,
                        params=params,
                    )

                if response.status_code in {429, 418}:
                    retry_after = response.headers.get("Retry-After")
                    try:
                        delay = float(retry_after) if retry_after else 0.0
                    except ValueError:
                        delay = 0.0

                    if delay <= 0:
                        delay = min(12.0, 1.5 * (2 ** attempt))

                    delay += random.uniform(0.05, 0.35)
                    if attempt == 4:
                        response.raise_for_status()

                    await asyncio.sleep(delay)
                    continue

                response.raise_for_status()
                return response.json()

            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
                if attempt == 4:
                    raise
                await asyncio.sleep(min(4.0, 0.5 * (2 ** attempt)))

            except httpx.HTTPStatusError as exc:
                last_error = exc
                if attempt == 4:
                    raise
                await asyncio.sleep(min(4.0, 0.5 * (2 ** attempt)))

        if last_error:
            raise last_error

        raise RuntimeError("Binance request failed unexpectedly")

    # =========================================================
    # EXCHANGE INFORMATION
    # =========================================================

    async def exchange_info(
        self,
        market: str = "futures",
    ) -> dict[str, Any]:

        market = market.lower()

        base = self._base_url(
            market
        )

        endpoint = (
            "/fapi/v1/exchangeInfo"
            if market == "futures"
            else "/api/v3/exchangeInfo"
        )

        return await self._request(
            "GET",
            f"{base}{endpoint}",
        )

    # =========================================================
    # 24H TICKER
    # =========================================================

    async def ticker_24h(
        self,
        market: str = "futures",
        symbol: Optional[str] = None,
    ) -> Any:

        market = market.lower()

        base = self._base_url(
            market
        )

        endpoint = (
            "/fapi/v1/ticker/24hr"
            if market == "futures"
            else "/api/v3/ticker/24hr"
        )

        params: dict[str, Any] = {}

        if symbol:
            params["symbol"] = (
                symbol.upper()
            )

        cache_key = f"{market}:{symbol.upper() if symbol else '*'}"
        now = asyncio.get_running_loop().time()
        cached = self._ticker_cache.get(cache_key)
        if cached and (now - cached[0]) < self._ticker_cache_ttl:
            return cached[1]

        data = await self._request(
            "GET",
            f"{base}{endpoint}",
            params=params,
        )

        self._ticker_cache[cache_key] = (now, data)
        return data

    # =========================================================
    # KLINES / CANDLES
    # =========================================================

    async def klines(
        self,
        symbol: str,
        interval: str = "15m",
        limit: int = 200,
        market: str = "futures",
    ) -> list[list[Any]]:

        market = market.lower()

        base = self._base_url(
            market
        )

        endpoint = (
            "/fapi/v1/klines"
            if market == "futures"
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

    # =========================================================
    # ORDER BOOK / DEPTH
    # =========================================================

    async def depth(
        self,
        symbol: str,
        limit: int = 100,
        market: str = "futures",
    ) -> dict[str, Any]:

        market = market.lower()

        base = self._base_url(
            market
        )

        endpoint = (
            "/fapi/v1/depth"
            if market == "futures"
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

    # =========================================================
    # FUTURES FUNDING RATE
    # =========================================================

    async def funding_rate(
        self,
        symbol: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:

        return await self._request(
            "GET",
            f"{self.futures_url}/fapi/v1/fundingRate",
            params={
                "symbol": symbol.upper(),
                "limit": limit,
            },
        )

    # =========================================================
    # FUTURES OPEN INTEREST
    # =========================================================

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

    # =========================================================
    # FUTURES OPEN INTEREST HISTORY
    # =========================================================

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

    # =========================================================
    # GLOBAL LONG / SHORT RATIO
    # =========================================================

    async def global_long_short_ratio(
        self,
        symbol: str,
        period: str = "5m",
        limit: int = 30,
    ) -> list[dict[str, Any]]:

        return await self._request(
            "GET",
            (
                f"{self.futures_url}"
                "/futures/data/"
                "globalLongShortAccountRatio"
            ),
            params={
                "symbol": symbol.upper(),
                "period": period,
                "limit": limit,
            },
        )

    # =========================================================
    # TOP TRADER LONG / SHORT RATIO
    # =========================================================

    async def top_trader_long_short_ratio(
        self,
        symbol: str,
        period: str = "5m",
        limit: int = 30,
    ) -> list[dict[str, Any]]:

        return await self._request(
            "GET",
            (
                f"{self.futures_url}"
                "/futures/data/"
                "topLongShortAccountRatio"
            ),
            params={
                "symbol": symbol.upper(),
                "period": period,
                "limit": limit,
            },
        )

    # =========================================================
    # RECENT LIQUIDATION ORDERS
    # =========================================================

    async def liquidation_orders(
        self,
        symbol: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:

        params: dict[str, Any] = {
            "limit": limit,
        }

        if symbol:
            params["symbol"] = (
                symbol.upper()
            )

        return await self._request(
            "GET",
            f"{self.futures_url}/fapi/v1/allForceOrders",
            params=params,
        )

    # =========================================================
    # PRICE
    # =========================================================

    async def price(
        self,
        symbol: str,
        market: str = "futures",
    ) -> dict[str, Any]:

        market = market.lower()

        base = self._base_url(
            market
        )

        endpoint = (
            "/fapi/v1/ticker/price"
            if market == "futures"
            else "/api/v3/ticker/price"
        )

        return await self._request(
            "GET",
            f"{base}{endpoint}",
            params={
                "symbol": symbol.upper(),
            },
        )

    # =========================================================
    # SERVER TIME
    # =========================================================

    async def server_time(
        self,
        market: str = "futures",
    ) -> dict[str, Any]:

        market = market.lower()

        base = self._base_url(
            market
        )

        endpoint = (
            "/fapi/v1/time"
            if market == "futures"
            else "/api/v3/time"
        )

        return await self._request(
            "GET",
            f"{base}{endpoint}",
        )

    # =========================================================
    # CLOSE CLIENT
    # =========================================================

    async def close(self) -> None:
        await self._client.aclose()


__all__ = [
    "BinanceClient",
]
