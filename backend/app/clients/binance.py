from __future__ import annotations

import asyncio
from typing import Any, Optional

import httpx

from app.core.config import settings


class BinanceClient:
    """
    Shared async Binance market-data client.

    Supports:
    - Binance Futures
    - Binance Spot

    Phase 1 foundation:
    - Persistent HTTP client
    - Connection pooling
    - Concurrency control
    - Separate Spot/Futures base URLs
    - Clean request layer
    """

    def __init__(self) -> None:
        self._client: Optional[
            httpx.AsyncClient
        ] = None

        self._request_semaphore = asyncio.Semaphore(
            8
        )

    # =====================================================
    # HTTP CLIENT
    # =====================================================

    async def _get_client(
        self,
    ) -> httpx.AsyncClient:

        if self._client is None:

            limits = httpx.Limits(
                max_connections=(
                    settings.http_max_connections
                ),
                max_keepalive_connections=(
                    settings.http_max_keepalive
                ),
            )

            self._client = (
                httpx.AsyncClient(
                    timeout=settings.request_timeout,
                    limits=limits,
                    headers={
                        "User-Agent": (
                            "RR-Trader/1.0"
                        ),
                        "Accept": (
                            "application/json"
                        ),
                    },
                )
            )

        return self._client

    # =====================================================
    # BASE URL
    # =====================================================

    def _base_url(
        self,
        market: str,
    ) -> str:

        normalized = (
            market
            .lower()
            .strip()
        )

        if normalized == "futures":
            return (
                settings
                .binance_futures_url
                .rstrip("/")
            )

        if normalized == "spot":
            return (
                settings
                .binance_spot_url
                .rstrip("/")
            )

        raise ValueError(
            "market must be 'spot' or 'futures'"
        )

    # =====================================================
    # REQUEST
    # =====================================================

    async def get(
        self,
        path: str,
        *,
        market: str = "futures",
        params: Optional[
            dict[str, Any]
        ] = None,
    ) -> Any:

        client = await self._get_client()

        url = (
            f"{self._base_url(market)}"
            f"{path}"
        )

        async with (
            self._request_semaphore
        ):

            response = await client.get(
                url,
                params=params,
            )

            response.raise_for_status()

            return response.json()

    # =====================================================
    # EXCHANGE INFO
    # =====================================================

    async def exchange_info(
        self,
        market: str = "futures",
    ) -> dict[str, Any]:

        path = (
            "/fapi/v1/exchangeInfo"
            if market.lower() == "futures"
            else "/api/v3/exchangeInfo"
        )

        return await self.get(
            path,
            market=market,
        )

    # =====================================================
    # 24H TICKER
    # =====================================================

    async def ticker_24h(
        self,
        market: str = "futures",
        symbol: Optional[str] = None,
    ) -> Any:

        path = (
            "/fapi/v1/ticker/24hr"
            if market.lower() == "futures"
            else "/api/v3/ticker/24hr"
        )

        params: dict[str, Any] = {}

        if symbol:
            params["symbol"] = (
                symbol.upper()
            )

        return await self.get(
            path,
            market=market,
            params=params,
        )

    # =====================================================
    # KLINES
    # =====================================================

    async def klines(
        self,
        symbol: str,
        interval: str,
        *,
        market: str = "futures",
        limit: int = 200,
    ) -> Any:

        path = (
            "/fapi/v1/klines"
            if market.lower() == "futures"
            else "/api/v3/klines"
        )

        params = {
            "symbol": (
                symbol.upper()
            ),
            "interval": interval,
            "limit": limit,
        }

        return await self.get(
            path,
            market=market,
            params=params,
        )

    # =====================================================
    # ORDER BOOK
    # =====================================================

    async def order_book(
        self,
        symbol: str,
        *,
        market: str = "futures",
        limit: int = 100,
    ) -> Any:

        path = (
            "/fapi/v1/depth"
            if market.lower() == "futures"
            else "/api/v3/depth"
        )

        params = {
            "symbol": (
                symbol.upper()
            ),
            "limit": limit,
        }

        return await self.get(
            path,
            market=market,
            params=params,
        )

    # =====================================================
    # PRICE
    # =====================================================

    async def price(
        self,
        symbol: str,
        *,
        market: str = "futures",
    ) -> Any:

        path = (
            "/fapi/v1/ticker/price"
            if market.lower() == "futures"
            else "/api/v3/ticker/price"
        )

        return await self.get(
            path,
            market=market,
            params={
                "symbol": (
                    symbol.upper()
                ),
            },
        )

    # =====================================================
    # CLOSE
    # =====================================================

    async def close(
        self,
    ) -> None:

        if self._client is not None:

            await self._client.aclose()

            self._client = None


# =========================================================
# SHARED INSTANCE
# =========================================================

binance_client = BinanceClient()


__all__ = [
    "BinanceClient",
    "binance_client",
]
