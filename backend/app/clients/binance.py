from __future__ import annotations

import asyncio
from typing import Any, Optional

import httpx

from app.core.config import settings


# =========================================================
# RR TRADER MULTI-EXCHANGE MARKET CLIENT
#
# Supported exchanges:
#   - Binance Futures
#   - Binance Spot
#   - Bitget USDT Futures
#   - MEXC Futures
#   - OKX SWAP / Perpetual
#
# Supported timeframes:
#   - 5m
#   - 15m
#   - 30m
#   - 45m  -> built from 15m candles
#   - 1h
#   - 4h
#   - 1D
#
# This file is intentionally kept compatible with the old
# BinanceClient interface so existing RR Trader code can
# continue using:
#
#   binance_client.klines(...)
#   binance_client.ticker_24h(...)
#   binance_client.order_book(...)
#   binance_client.price(...)
#   binance_client.exchange_info(...)
# =========================================================


# =========================================================
# DEFAULT ENDPOINTS
# =========================================================

BINANCE_FUTURES_URL = (
    "https://fapi.binance.com"
)

BINANCE_SPOT_URL = (
    "https://api.binance.com"
)

BITGET_URL = (
    "https://api.bitget.com"
)

MEXC_URL = (
    "https://api.mexc.com"
)

OKX_URL = (
    "https://www.okx.com"
)


# =========================================================
# TIMEFRAME MAP
# =========================================================

SUPPORTED_TIMEFRAMES = (
    "5m",
    "15m",
    "30m",
    "45m",
    "1h",
    "4h",
    "1d",
)


# Native timeframes available on exchanges.
#
# 45m is NOT requested directly.
# It is generated from 3 x 15m candles.
NATIVE_TIMEFRAMES = {
    "5m",
    "15m",
    "30m",
    "1h",
    "4h",
    "1d",
}


# =========================================================
# HELPERS
# =========================================================


def normalize_market(
    market: str,
) -> str:

    value = (
        str(market)
        .lower()
        .strip()
    )

    aliases = {
        "future": "futures",
        "futures": "futures",
        "future_usdt": "futures",
        "spot": "spot",
    }

    return aliases.get(
        value,
        value,
    )


def normalize_timeframe(
    interval: str,
) -> str:

    value = (
        str(interval)
        .strip()
        .lower()
    )

    aliases = {
        "5": "5m",
        "5min": "5m",
        "5minute": "5m",
        "15": "15m",
        "15min": "15m",
        "30": "30m",
        "30min": "30m",
        "45": "45m",
        "45min": "45m",
        "60m": "1h",
        "60min": "1h",
        "1hour": "1h",
        "1hr": "1h",
        "1h": "1h",
        "240m": "4h",
        "240min": "4h",
        "4hour": "4h",
        "4hr": "4h",
        "4h": "4h",
        "1day": "1d",
        "1d": "1d",
        "1D": "1d",
    }

    result = aliases.get(
        value,
        value,
    )

    if result not in SUPPORTED_TIMEFRAMES:
        raise ValueError(
            "Unsupported timeframe. "
            "Use: 5m, 15m, 30m, 45m, 1h, 4h, 1d"
        )

    return result


def normalize_symbol(
    symbol: str,
) -> str:

    return (
        str(symbol)
        .upper()
        .replace(
            "/",
            "",
        )
        .replace(
            "-PERP",
            "",
        )
        .replace(
            "_PERP",
            "",
        )
        .strip()
    )


# =========================================================
# UNIFIED HTTP CLIENT
# =========================================================


class MultiExchangeClient:

    def __init__(self) -> None:

        self._client: Optional[
            httpx.AsyncClient
        ] = None

        self._request_semaphore = (
            asyncio.Semaphore(8)
        )

    # =====================================================
    # HTTP CLIENT
    # =====================================================

    async def _get_client(
        self,
    ) -> httpx.AsyncClient:

        if self._client is None:

            max_connections = getattr(
                settings,
                "http_max_connections",
                50,
            )

            max_keepalive = getattr(
                settings,
                "http_max_keepalive",
                20,
            )

            timeout = getattr(
                settings,
                "request_timeout",
                20.0,
            )

            limits = httpx.Limits(
                max_connections=(
                    max_connections
                ),
                max_keepalive_connections=(
                    max_keepalive
                ),
            )

            self._client = (
                httpx.AsyncClient(
                    timeout=timeout,
                    limits=limits,
                    headers={
                        "User-Agent": (
                            "RR-Trader/2.0"
                        ),
                        "Accept": (
                            "application/json"
                        ),
                    },
                )
            )

        return self._client

    # =====================================================
    # GENERIC GET
    # =====================================================

    async def _request(
        self,
        url: str,
        *,
        params: Optional[
            dict[str, Any]
        ] = None,
    ) -> Any:

        client = await self._get_client()

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
    # CLOSE
    # =====================================================

    async def close(
        self,
    ) -> None:

        if self._client is not None:

            await self._client.aclose()

            self._client = None

    # =====================================================
    # BINANCE BASE URL
    # =====================================================

    def _binance_base_url(
        self,
        market: str,
    ) -> str:

        market = normalize_market(
            market
        )

        if market == "futures":

            return (
                getattr(
                    settings,
                    "binance_futures_url",
                    BINANCE_FUTURES_URL,
                )
                .rstrip("/")
            )

        if market == "spot":

            return (
                getattr(
                    settings,
                    "binance_spot_url",
                    BINANCE_SPOT_URL,
                )
                .rstrip("/")
            )

        raise ValueError(
            "Binance market must be "
            "'spot' or 'futures'"
        )

    # =====================================================
    # BINANCE GENERIC GET
    # =====================================================

    async def _binance_get(
        self,
        path: str,
        *,
        market: str = "futures",
        params: Optional[
            dict[str, Any]
        ] = None,
    ) -> Any:

        url = (
            f"{self._binance_base_url(market)}"
            f"{path}"
        )

        return await self._request(
            url,
            params=params,
        )

    # =====================================================
    # BINANCE EXCHANGE INFO
    # =====================================================

    async def exchange_info(
        self,
        market: str = "futures",
    ) -> dict[str, Any]:

        market = normalize_market(
            market
        )

        path = (
            "/fapi/v1/exchangeInfo"
            if market == "futures"
            else "/api/v3/exchangeInfo"
        )

        return await self._binance_get(
            path,
            market=market,
        )

    # =====================================================
    # BINANCE 24H TICKER
    # =====================================================

    async def ticker_24h(
        self,
        market: str = "futures",
        symbol: Optional[str] = None,
    ) -> Any:

        market = normalize_market(
            market
        )

        path = (
            "/fapi/v1/ticker/24hr"
            if market == "futures"
            else "/api/v3/ticker/24hr"
        )

        params: dict[str, Any] = {}

        if symbol:

            params["symbol"] = (
                normalize_symbol(symbol)
            )

        return await self._binance_get(
            path,
            market=market,
            params=params,
        )

    # =====================================================
    # BINANCE KLINES
    # =====================================================

    async def klines(
        self,
        symbol: str,
        interval: str,
        *,
        market: str = "futures",
        limit: int = 200,
    ) -> Any:

        market = normalize_market(
            market
        )

        timeframe = normalize_timeframe(
            interval
        )

        if timeframe == "45m":

            raw = await self.klines(
                symbol,
                "15m",
                market=market,
                limit=max(
                    limit * 3 + 3,
                    30,
                ),
            )

            return build_45m_candles(
                raw,
                limit=limit,
            )

        path = (
            "/fapi/v1/klines"
            if market == "futures"
            else "/api/v3/klines"
        )

        params = {
            "symbol": normalize_symbol(
                symbol
            ),
            "interval": timeframe,
            "limit": min(
                int(limit),
                1000,
            ),
        }

        return await self._binance_get(
            path,
            market=market,
            params=params,
        )

    # =====================================================
    # BINANCE ORDER BOOK
    # =====================================================

    async def order_book(
        self,
        symbol: str,
        *,
        market: str = "futures",
        limit: int = 100,
    ) -> Any:

        market = normalize_market(
            market
        )

        path = (
            "/fapi/v1/depth"
            if market == "futures"
            else "/api/v3/depth"
        )

        params = {
            "symbol": normalize_symbol(
                symbol
            ),
            "limit": min(
                int(limit),
                1000,
            ),
        }

        return await self._binance_get(
            path,
            market=market,
            params=params,
        )

    # =====================================================
    # BINANCE PRICE
    # =====================================================

    async def price(
        self,
        symbol: str,
        *,
        market: str = "futures",
    ) -> Any:

        market = normalize_market(
            market
        )

        path = (
            "/fapi/v1/ticker/price"
            if market == "futures"
            else "/api/v3/ticker/price"
        )

        return await self._binance_get(
            path,
            market=market,
            params={
                "symbol": normalize_symbol(
                    symbol
                )
            },
        )

    # =====================================================
    # BITGET FUTURES
    # =====================================================

    async def bitget_tickers(
        self,
    ) -> list[dict[str, Any]]:

        data = await self._request(
            f"{BITGET_URL}/api/v2/mix/market/tickers",
            params={
                "productType":
                    "USDT-FUTURES",
            },
        )

        if not isinstance(data, dict):
            return []

        rows = data.get(
            "data",
            [],
        )

        return (
            rows
            if isinstance(rows, list)
            else []
        )

    async def bitget_contracts(
        self,
    ) -> list[dict[str, Any]]:

        data = await self._request(
            f"{BITGET_URL}/api/v2/mix/market/contracts",
            params={
                "productType":
                    "USDT-FUTURES",
            },
        )

        if not isinstance(data, dict):
            return []

        rows = data.get(
            "data",
            [],
        )

        return (
            rows
            if isinstance(rows, list)
            else []
        )

    async def bitget_klines(
        self,
        symbol: str,
        interval: str,
        *,
        limit: int = 200,
    ) -> Any:

        timeframe = normalize_timeframe(
            interval
        )

        if timeframe == "45m":

            raw = await self.bitget_klines(
                symbol,
                "15m",
                limit=max(
                    limit * 3 + 3,
                    30,
                ),
            )

            return build_45m_candles(
                raw,
                limit=limit,
            )

        granularity = {
            "5m": "5m",
            "15m": "15m",
            "30m": "30m",
            "1h": "1H",
            "4h": "4H",
            "1d": "1D",
        }[timeframe]

        data = await self._request(
            f"{BITGET_URL}/api/v2/mix/market/candles",
            params={
                "symbol": normalize_symbol(
                    symbol
                ),
                "granularity": granularity,
                "productType":
                    "USDT-FUTURES",
                "limit": min(
                    int(limit),
                    1000,
                ),
            },
        )

        if not isinstance(data, dict):
            return []

        rows = data.get(
            "data",
            [],
        )

        return (
            rows
            if isinstance(rows, list)
            else []
        )

    async def bitget_order_book(
        self,
        symbol: str,
        *,
        limit: int = 100,
    ) -> Any:

        data = await self._request(
            f"{BITGET_URL}/api/v2/mix/market/merge-depth",
            params={
                "symbol": normalize_symbol(
                    symbol
                ),
                "productType":
                    "USDT-FUTURES",
                "limit": min(
                    int(limit),
                    100,
                ),
            },
        )

        return data

    async def bitget_price(
        self,
        symbol: str,
    ) -> Any:

        data = await self._request(
            f"{BITGET_URL}/api/v2/mix/market/symbol-price",
            params={
                "symbol": normalize_symbol(
                    symbol
                ),
                "productType":
                    "USDT-FUTURES",
            },
        )

        return data

    # =====================================================
    # MEXC FUTURES
    # =====================================================

    async def mexc_contracts(
        self,
    ) -> list[dict[str, Any]]:

        data = await self._request(
            f"{MEXC_URL}/api/v1/contract/detail"
        )

        if not isinstance(data, dict):
            return []

        rows = data.get(
            "data",
            [],
        )

        return (
            rows
            if isinstance(rows, list)
            else []
        )

    async def mexc_tickers(
        self,
    ) -> list[dict[str, Any]]:

        data = await self._request(
            f"{MEXC_URL}/api/v1/contract/ticker"
        )

        if isinstance(data, dict):

            rows = data.get(
                "data",
                [],
            )

            if isinstance(rows, list):
                return rows

            if isinstance(rows, dict):
                return [rows]

        return []

    async def mexc_klines(
        self,
        symbol: str,
        interval: str,
        *,
        limit: int = 200,
    ) -> Any:

        timeframe = normalize_timeframe(
            interval
        )

        if timeframe == "45m":

            raw = await self.mexc_klines(
                symbol,
                "15m",
                limit=max(
                    limit * 3 + 3,
                    30,
                ),
            )

            return build_45m_candles(
                raw,
                limit=limit,
            )

        # MEXC contract API interval names.
        interval_map = {
            "5m": "Min5",
            "15m": "Min15",
            "30m": "Min30",
            "1h": "Min60",
            "4h": "Hour4",
            "1d": "Day1",
        }

        mexc_interval = interval_map[
            timeframe
        ]

        data = await self._request(
            f"{MEXC_URL}/api/v1/contract/kline/"
            f"{normalize_symbol(symbol)}",
            params={
                "interval": mexc_interval,
                "limit": min(
                    int(limit),
                    2000,
                ),
            },
        )

        return data

    async def mexc_order_book(
        self,
        symbol: str,
        *,
        limit: int = 100,
    ) -> Any:

        return await self._request(
            f"{MEXC_URL}/api/v1/contract/depth/"
            f"{normalize_symbol(symbol)}",
            params={
                "limit": min(
                    int(limit),
                    50,
                ),
            },
        )

    async def mexc_price(
        self,
        symbol: str,
    ) -> Any:

        return await self._request(
            f"{MEXC_URL}/api/v1/contract/ticker",
            params={
                "symbol": normalize_symbol(
                    symbol
                ),
            },
        )

    # =====================================================
    # OKX SWAP
    # =====================================================

    async def okx_instruments(
        self,
    ) -> list[dict[str, Any]]:

        data = await self._request(
            f"{OKX_URL}/api/v5/public/instruments",
            params={
                "instType": "SWAP",
            },
        )

        if not isinstance(data, dict):
            return []

        rows = data.get(
            "data",
            [],
        )

        return (
            rows
            if isinstance(rows, list)
            else []
        )

    async def okx_tickers(
        self,
    ) -> list[dict[str, Any]]:

        data = await self._request(
            f"{OKX_URL}/api/v5/market/tickers",
            params={
                "instType": "SWAP",
            },
        )

        if not isinstance(data, dict):
            return []

        rows = data.get(
            "data",
            [],
        )

        return (
            rows
            if isinstance(rows, list)
            else []
        )

    async def okx_klines(
        self,
        symbol: str,
        interval: str,
        *,
        limit: int = 200,
    ) -> Any:

        timeframe = normalize_timeframe(
            interval
        )

        if timeframe == "45m":

            raw = await self.okx_klines(
                symbol,
                "15m",
                limit=max(
                    limit * 3 + 3,
                    30,
                ),
            )

            return build_45m_candles(
                raw,
                limit=limit,
            )

        bar_map = {
            "5m": "5m",
            "15m": "15m",
            "30m": "30m",
            "1h": "1H",
            "4h": "4H",
            "1d": "1Dutc",
        }

        bar = bar_map[
            timeframe
        ]

        inst_id = (
            normalize_okx_symbol(
                symbol
            )
        )

        data = await self._request(
            f"{OKX_URL}/api/v5/market/candles",
            params={
                "instId": inst_id,
                "bar": bar,
                "limit": min(
                    int(limit),
                    300,
                ),
            },
        )

        if not isinstance(data, dict):
            return []

        rows = data.get(
            "data",
            [],
        )

        return (
            rows
            if isinstance(rows, list)
            else []
        )

    async def okx_order_book(
        self,
        symbol: str,
        *,
        limit: int = 100,
    ) -> Any:

        return await self._request(
            f"{OKX_URL}/api/v5/market/books",
            params={
                "instId":
                    normalize_okx_symbol(
                        symbol
                    ),
                "sz": min(
                    int(limit),
                    400,
                ),
            },
        )

    async def okx_price(
        self,
        symbol: str,
    ) -> Any:

        return await self._request(
            f"{OKX_URL}/api/v5/market/ticker",
            params={
                "instId":
                    normalize_okx_symbol(
                        symbol
                    ),
            },
        )

    # =====================================================
    # UNIFIED EXCHANGE KLINES
    # =====================================================

    async def exchange_klines(
        self,
        exchange: str,
        symbol: str,
        interval: str,
        *,
        market: str = "futures",
        limit: int = 200,
    ) -> Any:

        exchange_name = (
            exchange
            .lower()
            .strip()
        )

        if exchange_name == "binance":

            return await self.klines(
                symbol,
                interval,
                market=market,
                limit=limit,
            )

        if exchange_name == "bitget":

            if normalize_market(
                market
            ) != "futures":

                raise ValueError(
                    "Bitget adapter currently "
                    "supports USDT Futures."
                )

            return await self.bitget_klines(
                symbol,
                interval,
                limit=limit,
            )

        if exchange_name == "mexc":

            if normalize_market(
                market
            ) != "futures":

                raise ValueError(
                    "MEXC adapter currently "
                    "supports Futures."
                )

            return await self.mexc_klines(
                symbol,
                interval,
                limit=limit,
            )

        if exchange_name == "okx":

            if normalize_market(
                market
            ) != "futures":

                raise ValueError(
                    "OKX adapter currently "
                    "supports SWAP/Perpetual Futures."
                )

            return await self.okx_klines(
                symbol,
                interval,
                limit=limit,
            )

        raise ValueError(
            "Unsupported exchange. "
            "Use Binance, Bitget, MEXC or OKX."
        )

    # =====================================================
    # UNIFIED PRICE
    # =====================================================

    async def exchange_price(
        self,
        exchange: str,
        symbol: str,
        *,
        market: str = "futures",
    ) -> Any:

        exchange_name = (
            exchange
            .lower()
            .strip()
        )

        if exchange_name == "binance":

            return await self.price(
                symbol,
                market=market,
            )

        if exchange_name == "bitget":

            return await self.bitget_price(
                symbol
            )

        if exchange_name == "mexc":

            return await self.mexc_price(
                symbol
            )

        if exchange_name == "okx":

            return await self.okx_price(
                symbol
            )

        raise ValueError(
            "Unsupported exchange."
        )

    # =====================================================
    # COMMON FUTURES UNIVERSE
    # =====================================================

    async def futures_universe(
        self,
    ) -> dict[str, list[str]]:

        results = await asyncio.gather(
            self._safe_binance_symbols(),
            self._safe_bitget_symbols(),
            self._safe_mexc_symbols(),
            self._safe_okx_symbols(),
        )

        return {
            "binance": results[0],
            "bitget": results[1],
            "mexc": results[2],
            "okx": results[3],
        }

    async def common_futures_symbols(
        self,
    ) -> list[str]:

        universe = (
            await self.futures_universe()
        )

        sets = [
            set(
                symbols
            )
            for symbols in universe.values()
            if symbols
        ]

        if not sets:
            return []

        common = sets[0]

        for symbol_set in sets[1:]:

            common &= symbol_set

        return sorted(
            common
        )

    # =====================================================
    # SAFE SYMBOL FETCHERS
    # =====================================================

    async def _safe_binance_symbols(
        self,
    ) -> list[str]:

        try:

            data = await self.exchange_info(
                market="futures"
            )

            return sorted(
                {
                    normalize_symbol(
                        item.get(
                            "symbol",
                            "",
                        )
                    )
                    for item in data.get(
                        "symbols",
                        [],
                    )
                    if item.get(
                        "quoteAsset"
                    )
                    == "USDT"
                    and item.get(
                        "status"
                    )
                    == "TRADING"
                }
            )

        except Exception:

            return []

    async def _safe_bitget_symbols(
        self,
    ) -> list[str]:

        try:

            rows = (
                await self.bitget_contracts()
            )

            return sorted(
                {
                    normalize_symbol(
                        item.get(
                            "symbol",
                            "",
                        )
                    )
                    for item in rows
                    if str(
                        item.get(
                            "quoteCoin",
                            ""
                        )
                    ).upper()
                    == "USDT"
                    and str(
                        item.get(
                            "symbolStatus",
                            "normal",
                        )
                    ).lower()
                    in {
                        "normal",
                        "trading",
                    }
                }
            )

        except Exception:

            return []

    async def _safe_mexc_symbols(
        self,
    ) -> list[str]:

        try:

            rows = (
                await self.mexc_contracts()
            )

            symbols = []

            for item in rows:

                symbol = normalize_symbol(
                    item.get(
                        "symbol",
                        ""
                    )
                )

                if symbol:

                    # MEXC USDT perpetual
                    # symbols generally end
                    # with _USDT / USDT.
                    if (
                        "USDT"
                        in symbol
                    ):
                        symbols.append(
                            symbol
                        )

            return sorted(
                set(symbols)
            )

        except Exception:

            return []

    async def _safe_okx_symbols(
        self,
    ) -> list[str]:

        try:

            rows = (
                await self.okx_instruments()
            )

            symbols = []

            for item in rows:

                inst_id = str(
                    item.get(
                        "instId",
                        ""
                    )
                )

                settle_ccy = str(
                    item.get(
                        "settleCcy",
                        ""
                    )
                ).upper()

                state = str(
                    item.get(
                        "state",
                        ""
                    )
                ).lower()

                if (
                    settle_ccy == "USDT"
                    and state == "live"
                ):

                    symbols.append(
                        normalize_symbol(
                            inst_id
                        )
                    )

            return sorted(
                set(symbols)
            )

        except Exception:

            return []


# =========================================================
# OKX SYMBOL CONVERSION
# =========================================================


def normalize_okx_symbol(
    symbol: str,
) -> str:

    clean = normalize_symbol(
        symbol
    )

    # BTCUSDT -> BTC-USDT-SWAP
    if clean.endswith("USDT"):

        base = clean[
            :-4
        ]

        return (
            f"{base}-USDT-SWAP"
        )

    return clean


# =========================================================
# 45 MINUTE SYNTHETIC CANDLES
# =========================================================


def build_45m_candles(
    candles: Any,
    *,
    limit: int = 200,
) -> list[list[Any]]:

    if not isinstance(
        candles,
        list,
    ):

        return []

    normalized = []

    for candle in candles:

        try:

            # Binance format:
            # [
            # open_time,
            # open,
            # high,
            # low,
            # close,
            # volume,
            # ...
            # ]

            if len(candle) >= 6:

                normalized.append(
                    {
                        "ts": int(
                            candle[0]
                        ),
                        "open": float(
                            candle[1]
                        ),
                        "high": float(
                            candle[2]
                        ),
                        "low": float(
                            candle[3]
                        ),
                        "close": float(
                            candle[4]
                        ),
                        "volume": float(
                            candle[5]
                        ),
                    }
                )

        except (
            TypeError,
            ValueError,
            IndexError,
        ):

            continue

    if not normalized:

        return []

    normalized.sort(
        key=lambda item:
            item["ts"]
    )

    groups = []

    current = None
    current_bucket = None

    bucket_ms = (
        45 * 60 * 1000
    )

    for candle in normalized:

        bucket = (
            candle["ts"]
            // bucket_ms
        )

        if (
            current is None
            or bucket != current_bucket
        ):

            if current is not None:

                groups.append(
                    current
                )

            current_bucket = bucket

            current = {
                "ts": (
                    bucket
                    * bucket_ms
                ),
                "open":
                    candle["open"],
                "high":
                    candle["high"],
                "low":
                    candle["low"],
                "close":
                    candle["close"],
                "volume":
                    candle["volume"],
            }

        else:

            current["high"] = max(
                current["high"],
                candle["high"],
            )

            current["low"] = min(
                current["low"],
                candle["low"],
            )

            current["close"] = (
                candle["close"]
            )

            current["volume"] += (
                candle["volume"]
            )

    if current is not None:

        groups.append(
            current
        )

    # Return Binance-compatible
    # kline-style arrays.
    output = []

    for item in groups:

        output.append(
            [
                item["ts"],
                str(
                    item["open"]
                ),
                str(
                    item["high"]
                ),
                str(
                    item["low"]
                ),
                str(
                    item["close"]
                ),
                str(
                    item["volume"]
                ),
                item["ts"]
                + bucket_ms
                - 1,
                "0",
                0,
                "0",
                "0",
                "0",
            ]
        )

    return output[
        -limit:
    ]


# =========================================================
# BACKWARD-COMPATIBLE BINANCE CLIENT
# =========================================================


class BinanceClient:

    """
    Backward-compatible wrapper.

    Existing RR Trader code can continue using:

        binance_client.exchange_info()
        binance_client.ticker_24h()
        binance_client.klines()
        binance_client.order_book()
        binance_client.price()
        binance_client.close()

    while the same client now exposes:

        bitget_klines()
        mexc_klines()
        okx_klines()
        futures_universe()
        common_futures_symbols()
        exchange_klines()
        exchange_price()
    """

    def __init__(self) -> None:

        self._client = (
            MultiExchangeClient()
        )

    async def exchange_info(
        self,
        market: str = "futures",
    ) -> dict[str, Any]:

        return await (
            self._client.exchange_info(
                market
            )
        )

    async def ticker_24h(
        self,
        market: str = "futures",
        symbol: Optional[str] = None,
    ) -> Any:

        return await (
            self._client.ticker_24h(
                market,
                symbol,
            )
        )

    async def klines(
        self,
        symbol: str,
        interval: str,
        *,
        market: str = "futures",
        limit: int = 200,
    ) -> Any:

        return await (
            self._client.klines(
                symbol,
                interval,
                market=market,
                limit=limit,
            )
        )

    async def order_book(
        self,
        symbol: str,
        *,
        market: str = "futures",
        limit: int = 100,
    ) -> Any:

        return await (
            self._client.order_book(
                symbol,
                market=market,
                limit=limit,
            )
        )

    async def price(
        self,
        symbol: str,
        *,
        market: str = "futures",
    ) -> Any:

        return await (
            self._client.price(
                symbol,
                market=market,
            )
        )

    async def close(
        self,
    ) -> None:

        await self._client.close()

    # =====================================================
    # NEW EXCHANGE METHODS
    # =====================================================

    async def bitget_tickers(
        self,
    ) -> list[dict[str, Any]]:

        return await (
            self._client.bitget_tickers()
        )

    async def bitget_contracts(
        self,
    ) -> list[dict[str, Any]]:

        return await (
            self._client.bitget_contracts()
        )

    async def bitget_klines(
        self,
        symbol: str,
        interval: str,
        *,
        limit: int = 200,
    ) -> Any:

        return await (
            self._client.bitget_klines(
                symbol,
                interval,
                limit=limit,
            )
        )

    async def bitget_order_book(
        self,
        symbol: str,
        *,
        limit: int = 100,
    ) -> Any:

        return await (
            self._client.bitget_order_book(
                symbol,
                limit=limit,
            )
        )

    async def bitget_price(
        self,
        symbol: str,
    ) -> Any:

        return await (
            self._client.bitget_price(
                symbol
            )
        )

    async def mexc_contracts(
        self,
    ) -> list[dict[str, Any]]:

        return await (
            self._client.mexc_contracts()
        )

    async def mexc_tickers(
        self,
    ) -> list[dict[str, Any]]:

        return await (
            self._client.mexc_tickers()
        )

    async def mexc_klines(
        self,
        symbol: str,
        interval: str,
        *,
        limit: int = 200,
    ) -> Any:

        return await (
            self._client.mexc_klines(
                symbol,
                interval,
                limit=limit,
            )
        )

    async def mexc_order_book(
        self,
        symbol: str,
        *,
        limit: int = 100,
    ) -> Any:

        return await (
            self._client.mexc_order_book(
                symbol,
                limit=limit,
            )
        )

    async def mexc_price(
        self,
        symbol: str,
    ) -> Any:

        return await (
            self._client.mexc_price(
                symbol
            )
        )

    async def okx_instruments(
        self,
    ) -> list[dict[str, Any]]:

        return await (
            self._client.okx_instruments()
        )

    async def okx_tickers(
        self,
    ) -> list[dict[str, Any]]:

        return await (
            self._client.okx_tickers()
        )

    async def okx_klines(
        self,
        symbol: str,
        interval: str,
        *,
        limit: int = 200,
    ) -> Any:

        return await (
            self._client.okx_klines(
                symbol,
                interval,
                limit=limit,
            )
        )

    async def okx_order_book(
        self,
        symbol: str,
        *,
        limit: int = 100,
    ) -> Any:

        return await (
            self._client.okx_order_book(
                symbol,
                limit=limit,
            )
        )

    async def okx_price(
        self,
        symbol: str,
    ) -> Any:

        return await (
            self._client.okx_price(
                symbol
            )
        )

    async def futures_universe(
        self,
    ) -> dict[str, list[str]]:

        return await (
            self._client.futures_universe()
        )

    async def common_futures_symbols(
        self,
    ) -> list[str]:

        return await (
            self._client.common_futures_symbols()
        )

    async def exchange_klines(
        self,
        exchange: str,
        symbol: str,
        interval: str,
        *,
        market: str = "futures",
        limit: int = 200,
    ) -> Any:

        return await (
            self._client.exchange_klines(
                exchange,
                symbol,
                interval,
                market=market,
                limit=limit,
            )
        )

    async def exchange_price(
        self,
        exchange: str,
        symbol: str,
        *,
        market: str = "futures",
    ) -> Any:

        return await (
            self._client.exchange_price(
                exchange,
                symbol,
                market=market,
            )
        )


# =========================================================
# SHARED INSTANCE
# =========================================================

binance_client = BinanceClient()


# =========================================================
# EXPORTS
# =========================================================

__all__ = [
    "BinanceClient",
    "MultiExchangeClient",
    "binance_client",
    "SUPPORTED_TIMEFRAMES",
    "NATIVE_TIMEFRAMES",
    "build_45m_candles",
    "normalize_symbol",
    "normalize_timeframe",
]
