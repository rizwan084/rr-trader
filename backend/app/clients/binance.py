from __future__ import annotations

import asyncio
import random
import time
from typing import Any, Optional

import httpx

from app.core.config import settings


class BinanceClient:
    """
    RR Trader shared async Binance market-data client.

    Supports:
    - Binance Spot
    - Binance Futures

    Core market data:
    - Exchange information
    - 24h ticker
    - Klines
    - Order book
    - Price

    Futures intelligence:
    - Open Interest
    - Funding Rate
    - Global Long/Short Ratio
    - Top Trader Long/Short Ratio
    - Recent liquidation / force-order data

    Performance / reliability:
    - Persistent AsyncClient
    - HTTP connection pooling
    - Concurrency semaphore
    - Short-lived cache
    - Retry with exponential backoff
    - 418 / 429 protection
    - Retry-After support
    """

    def __init__(self) -> None:

        self._client: Optional[
            httpx.AsyncClient
        ] = None

        self._client_lock = asyncio.Lock()

        self._request_semaphore = (
            asyncio.Semaphore(8)
        )

        self._cache: dict[
            str,
            tuple[float, Any],
        ] = {}

        self._cache_lock = asyncio.Lock()

        self.max_retries = 4

        self.base_backoff_seconds = 0.5

        self.max_backoff_seconds = 8.0

        self.ticker_cache_seconds = 15.0

        self.exchange_info_cache_seconds = (
            300.0
        )

    # =====================================================
    # HTTP CLIENT
    # =====================================================

    async def _get_client(
        self,
    ) -> httpx.AsyncClient:

        if self._client is not None:
            return self._client

        async with self._client_lock:

            if self._client is not None:
                return self._client

            limits = httpx.Limits(
                max_connections=(
                    settings.http_max_connections
                ),
                max_keepalive_connections=(
                    settings.http_max_keepalive
                ),
            )

            timeout = httpx.Timeout(
                timeout=settings.request_timeout,
                connect=min(
                    settings.request_timeout,
                    10.0,
                ),
            )

            self._client = (
                httpx.AsyncClient(
                    timeout=timeout,
                    limits=limits,
                    headers={
                        "User-Agent":
                            "RR-Trader/1.0",
                        "Accept":
                            "application/json",
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
            str(market)
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
    # CACHE HELPERS
    # =====================================================

    @staticmethod
    def _cache_key(
        path: str,
        market: str,
        params: Optional[
            dict[str, Any]
        ],
    ) -> str:

        normalized_params = tuple(
            sorted(
                (
                    str(key),
                    str(value),
                )
                for key, value
                in (
                    params or {}
                ).items()
            )
        )

        return (
            f"{market.lower()}"
            f"|{path}"
            f"|{normalized_params}"
        )

    async def _cache_get(
        self,
        key: str,
    ) -> Any | None:

        async with self._cache_lock:

            item = self._cache.get(
                key
            )

            if item is None:
                return None

            expires_at, value = item

            if time.monotonic() >= (
                expires_at
            ):

                self._cache.pop(
                    key,
                    None,
                )

                return None

            return value

    async def _cache_set(
        self,
        key: str,
        value: Any,
        ttl: float,
    ) -> None:

        async with self._cache_lock:

            self._cache[key] = (
                time.monotonic()
                + max(
                    0.0,
                    ttl,
                ),
                value,
            )

    async def clear_cache(self) -> None:

        async with self._cache_lock:

            self._cache.clear()

    # =====================================================
    # RETRY DELAY
    # =====================================================

    def _retry_delay(
        self,
        attempt: int,
        retry_after: str | None = None,
    ) -> float:

        if retry_after:

            try:

                retry_seconds = float(
                    retry_after
                )

                return max(
                    0.1,
                    min(
                        retry_seconds,
                        self.max_backoff_seconds,
                    ),
                )

            except (
                TypeError,
                ValueError,
            ):
                pass

        exponential = (
            self.base_backoff_seconds
            * (
                2 ** attempt
            )
        )

        jitter = random.uniform(
            0.0,
            0.25,
        )

        return min(
            self.max_backoff_seconds,
            exponential + jitter,
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
        cache_ttl: float = 0.0,
        use_cache: bool = False,
    ) -> Any:

        normalized_market = (
            str(market)
            .lower()
            .strip()
        )

        url = (
            f"{self._base_url(normalized_market)}"
            f"{path}"
        )

        key = self._cache_key(
            path,
            normalized_market,
            params,
        )

        if use_cache and cache_ttl > 0:

            cached = await self._cache_get(
                key
            )

            if cached is not None:
                return cached

        client = await self._get_client()

        last_error: Exception | None = None

        for attempt in range(
            self.max_retries + 1
        ):

            try:

                async with (
                    self._request_semaphore
                ):

                    response = (
                        await client.get(
                            url,
                            params=params,
                        )
                    )

                # -----------------------------------------
                # Rate limit handling
                # -----------------------------------------

                if response.status_code in {
                    418,
                    429,
                }:

                    retry_after = (
                        response.headers.get(
                            "Retry-After"
                        )
                    )

                    if attempt >= (
                        self.max_retries
                    ):

                        response.raise_for_status()

                    await asyncio.sleep(
                        self._retry_delay(
                            attempt,
                            retry_after,
                        )
                    )

                    continue

                # -----------------------------------------
                # Temporary server errors
                # -----------------------------------------

                if response.status_code in {
                    500,
                    502,
                    503,
                    504,
                }:

                    if attempt >= (
                        self.max_retries
                    ):

                        response.raise_for_status()

                    await asyncio.sleep(
                        self._retry_delay(
                            attempt
                        )
                    )

                    continue

                response.raise_for_status()

                data = response.json()

                if (
                    use_cache
                    and cache_ttl > 0
                ):

                    await self._cache_set(
                        key,
                        data,
                        cache_ttl,
                    )

                return data

            except (
                httpx.TimeoutException,
                httpx.NetworkError,
                httpx.RemoteProtocolError,
            ) as exc:

                last_error = exc

                if attempt >= (
                    self.max_retries
                ):
                    raise

                await asyncio.sleep(
                    self._retry_delay(
                        attempt
                    )
                )

            except httpx.HTTPStatusError as exc:

                last_error = exc

                if attempt >= (
                    self.max_retries
                ):
                    raise

                if exc.response.status_code not in {
                    418,
                    429,
                    500,
                    502,
                    503,
                    504,
                }:

                    raise

                await asyncio.sleep(
                    self._retry_delay(
                        attempt,
                        exc.response.headers.get(
                            "Retry-After"
                        ),
                    )
                )

        if last_error is not None:
            raise last_error

        raise RuntimeError(
            "Binance request failed without a response."
        )

    # =====================================================
    # EXCHANGE INFORMATION
    # =====================================================

    async def exchange_info(
        self,
        market: str = "futures",
    ) -> dict[str, Any]:

        normalized_market = (
            market.lower()
        )

        path = (
            "/fapi/v1/exchangeInfo"
            if normalized_market
            == "futures"
            else "/api/v3/exchangeInfo"
        )

        return await self.get(
            path,
            market=normalized_market,
            cache_ttl=(
                self.exchange_info_cache_seconds
            ),
            use_cache=True,
        )

    # =====================================================
    # 24H TICKER
    # =====================================================

    async def ticker_24h(
        self,
        market: str = "futures",
        symbol: Optional[str] = None,
    ) -> Any:

        normalized_market = (
            market.lower()
        )

        path = (
            "/fapi/v1/ticker/24hr"
            if normalized_market
            == "futures"
            else "/api/v3/ticker/24hr"
        )

        params: dict[str, Any] = {}

        if symbol:

            params["symbol"] = (
                symbol.upper()
            )

        # All-symbol ticker is expensive enough to
        # benefit strongly from a short cache.
        ttl = (
            self.ticker_cache_seconds
            if symbol is None
            else 3.0
        )

        return await self.get(
            path,
            market=normalized_market,
            params=params,
            cache_ttl=ttl,
            use_cache=True,
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

        normalized_market = (
            market.lower()
        )

        path = (
            "/fapi/v1/klines"
            if normalized_market
            == "futures"
            else "/api/v3/klines"
        )

        safe_limit = max(
            1,
            min(
                int(limit),
                1500,
            ),
        )

        params = {
            "symbol":
                symbol.upper(),
            "interval":
                interval,
            "limit":
                safe_limit,
        }

        return await self.get(
            path,
            market=normalized_market,
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

        normalized_market = (
            market.lower()
        )

        path = (
            "/fapi/v1/depth"
            if normalized_market
            == "futures"
            else "/api/v3/depth"
        )

        safe_limit = max(
            5,
            min(
                int(limit),
                5000,
            ),
        )

        params = {
            "symbol":
                symbol.upper(),
            "limit":
                safe_limit,
        }

        return await self.get(
            path,
            market=normalized_market,
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

        normalized_market = (
            market.lower()
        )

        path = (
            "/fapi/v1/ticker/price"
            if normalized_market
            == "futures"
            else "/api/v3/ticker/price"
        )

        return await self.get(
            path,
            market=normalized_market,
            params={
                "symbol":
                    symbol.upper(),
            },
            cache_ttl=1.0,
            use_cache=True,
        )

    # =====================================================
    # MARK PRICE
    # =====================================================

    async def mark_price(
        self,
        symbol: str,
    ) -> Any:

        return await self.get(
            "/fapi/v1/premiumIndex",
            market="futures",
            params={
                "symbol":
                    symbol.upper(),
            },
            cache_ttl=2.0,
            use_cache=True,
        )

    # =====================================================
    # OPEN INTEREST
    # =====================================================

    async def open_interest(
        self,
        symbol: str,
    ) -> Any:

        return await self.get(
            "/fapi/v1/openInterest",
            market="futures",
            params={
                "symbol":
                    symbol.upper(),
            },
            cache_ttl=3.0,
            use_cache=True,
        )

    # =====================================================
    # OPEN INTEREST HISTORY
    # =====================================================

    async def open_interest_history(
        self,
        symbol: str,
        period: str = "5m",
        limit: int = 30,
    ) -> list[dict[str, Any]]:

        safe_limit = max(
            1,
            min(
                int(limit),
                500,
            ),
        )

        data = await self.get(
            "/futures/data/openInterestHist",
            market="futures",
            params={
                "symbol":
                    symbol.upper(),
                "period":
                    period,
                "limit":
                    safe_limit,
            },
            cache_ttl=5.0,
            use_cache=True,
        )

        return (
            data
            if isinstance(
                data,
                list,
            )
            else []
        )

    # =====================================================
    # FUNDING RATE
    # =====================================================

    async def funding_rate(
        self,
        symbol: str,
        limit: int = 30,
    ) -> list[dict[str, Any]]:

        safe_limit = max(
            1,
            min(
                int(limit),
                1000,
            ),
        )

        data = await self.get(
            "/fapi/v1/fundingRate",
            market="futures",
            params={
                "symbol":
                    symbol.upper(),
                "limit":
                    safe_limit,
            },
            cache_ttl=10.0,
            use_cache=True,
        )

        return (
            data
            if isinstance(
                data,
                list,
            )
            else []
        )

    # =====================================================
    # GLOBAL LONG / SHORT RATIO
    # =====================================================

    async def global_long_short_ratio(
        self,
        symbol: str,
        period: str = "5m",
        limit: int = 30,
    ) -> list[dict[str, Any]]:

        safe_limit = max(
            1,
            min(
                int(limit),
                500,
            ),
        )

        data = await self.get(
            "/futures/data/globalLongShortAccountRatio",
            market="futures",
            params={
                "symbol":
                    symbol.upper(),
                "period":
                    period,
                "limit":
                    safe_limit,
            },
            cache_ttl=5.0,
            use_cache=True,
        )

        return (
            data
            if isinstance(
                data,
                list,
            )
            else []
        )

    # =====================================================
    # TOP TRADER ACCOUNT LONG / SHORT RATIO
    # =====================================================

    async def top_trader_long_short_ratio(
        self,
        symbol: str,
        period: str = "5m",
        limit: int = 30,
    ) -> list[dict[str, Any]]:

        safe_limit = max(
            1,
            min(
                int(limit),
                500,
            ),
        )

        data = await self.get(
            "/futures/data/topLongShortAccountRatio",
            market="futures",
            params={
                "symbol":
                    symbol.upper(),
                "period":
                    period,
                "limit":
                    safe_limit,
            },
            cache_ttl=5.0,
            use_cache=True,
        )

        return (
            data
            if isinstance(
                data,
                list,
            )
            else []
        )

    # =====================================================
    # TOP TRADER POSITION RATIO
    # =====================================================

    async def top_trader_position_ratio(
        self,
        symbol: str,
        period: str = "5m",
        limit: int = 30,
    ) -> list[dict[str, Any]]:

        safe_limit = max(
            1,
            min(
                int(limit),
                500,
            ),
        )

        data = await self.get(
            "/futures/data/topLongShortPositionRatio",
            market="futures",
            params={
                "symbol":
                    symbol.upper(),
                "period":
                    period,
                "limit":
                    safe_limit,
            },
            cache_ttl=5.0,
            use_cache=True,
        )

        return (
            data
            if isinstance(
                data,
                list,
            )
            else []
        )

    # =====================================================
    # RECENT LIQUIDATION / FORCE ORDERS
    # =====================================================

    async def liquidation_orders(
        self,
        symbol: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:

        safe_limit = max(
            1,
            min(
                int(limit),
                1000,
            ),
        )

        params: dict[str, Any] = {
            "limit":
                safe_limit,
        }

        if symbol:

            params["symbol"] = (
                symbol.upper()
            )

        data = await self.get(
            "/fapi/v1/allForceOrders",
            market="futures",
            params=params,
            cache_ttl=5.0,
            use_cache=True,
        )

        return (
            data
            if isinstance(
                data,
                list,
            )
            else []
        )

    # =====================================================
    # SERVER TIME
    # =====================================================

    async def server_time(
        self,
        market: str = "futures",
    ) -> dict[str, Any]:

        normalized_market = (
            market.lower()
        )

        path = (
            "/fapi/v1/time"
            if normalized_market
            == "futures"
            else "/api/v3/time"
        )

        return await self.get(
            path,
            market=normalized_market,
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

        await self.clear_cache()


# =========================================================
# SHARED INSTANCE
# =========================================================

binance_client = BinanceClient()


__all__ = [
    "BinanceClient",
    "binance_client",
]
