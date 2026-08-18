from __future__ import annotations

import asyncio
from typing import Any

from app.clients.binance import binance_client
from app.core.config import settings


class MarketScanner:
    """
    RR Trader market scanner foundation.

    Core decision timeframes:
    - 15m
    - 1h
    - 4h

    Supports:
    - Binance Futures
    - Binance Spot

    Deep 24-point intelligence will be added
    in the analysis-engine phase.
    """

    CORE_TIMEFRAMES = (
        "15m",
        "1h",
        "4h",
    )

    TIMEFRAME_WEIGHTS = {
        "15m": 0.30,
        "1h": 0.35,
        "4h": 0.35,
    }

    def __init__(self) -> None:
        self.deep_analysis_limit = (
            settings.deep_analysis_limit
        )

    # =====================================================
    # SYMBOL NORMALIZATION
    # =====================================================

    @staticmethod
    def normalize_symbol(
        symbol: str,
    ) -> str:

        clean = (
            str(symbol or "")
            .upper()
            .replace("/", "")
            .replace("-", "")
            .strip()
        )

        if not clean:
            raise ValueError(
                "Symbol is required."
            )

        if not clean.endswith("USDT"):
            clean = f"{clean}USDT"

        return clean

    # =====================================================
    # MARKET VALIDATION
    # =====================================================

    @staticmethod
    def normalize_market(
        market: str,
    ) -> str:

        clean = (
            str(market or "")
            .lower()
            .strip()
        )

        if clean not in {
            "spot",
            "futures",
        }:
            raise ValueError(
                "market must be 'spot' or 'futures'"
            )

        return clean

    # =====================================================
    # CANDLE FETCH
    # =====================================================

    async def _fetch_timeframe(
        self,
        symbol: str,
        timeframe: str,
        market: str,
        limit: int,
    ) -> dict[str, Any]:

        candles = await binance_client.klines(
            symbol=symbol,
            interval=timeframe,
            market=market,
            limit=limit,
        )

        return {
            "timeframe": timeframe,
            "market": market,
            "symbol": symbol,
            "candle_count": (
                len(candles)
                if isinstance(
                    candles,
                    list,
                )
                else 0
            ),
            "candles": candles,
        }

    # =====================================================
    # SINGLE SYMBOL
    # =====================================================

    async def scan_symbol(
        self,
        symbol: str,
        market: str = "futures",
        limit: int = 200,
    ) -> dict[str, Any]:

        symbol = self.normalize_symbol(
            symbol
        )

        market = self.normalize_market(
            market
        )

        timeframe_tasks = [
            self._fetch_timeframe(
                symbol=symbol,
                timeframe=timeframe,
                market=market,
                limit=limit,
            )
            for timeframe in self.CORE_TIMEFRAMES
        ]

        timeframe_results = await asyncio.gather(
            *timeframe_tasks,
            return_exceptions=True,
        )

        timeframes: dict[str, Any] = {}
        errors: dict[str, str] = {}

        for timeframe, result in zip(
            self.CORE_TIMEFRAMES,
            timeframe_results,
        ):

            if isinstance(
                result,
                Exception,
            ):
                errors[timeframe] = str(
                    result
                )

                timeframes[timeframe] = {
                    "success": False,
                    "error": str(result),
                }

                continue

            timeframes[timeframe] = {
                "success": True,
                "timeframe": timeframe,
                "candle_count": result[
                    "candle_count"
                ],
                "status": (
                    "data_ready_for_analysis"
                ),
            }

        return {
            "success": len(errors) == 0,
            "symbol": symbol,
            "market": market,
            "core_timeframes": list(
                self.CORE_TIMEFRAMES
            ),
            "timeframe_weights": dict(
                self.TIMEFRAME_WEIGHTS
            ),
            "timeframes": timeframes,
            "errors": errors,
            "status": (
                "scanner_data_ready"
                if not errors
                else "scanner_partial"
            ),
        }

    # =====================================================
    # MARKET UNIVERSE
    # =====================================================

    @staticmethod
    def _valid_usdt_symbol(
        ticker: Any,
    ) -> bool:

        if not isinstance(
            ticker,
            dict,
        ):
            return False

        symbol = str(
            ticker.get(
                "symbol",
                "",
            )
        ).upper()

        if not symbol.endswith(
            "USDT"
        ):
            return False

        if any(
            blocked in symbol
            for blocked in (
                "UPUSDT",
                "DOWNUSDT",
                "BULLUSDT",
                "BEARUSDT",
            )
        ):
            return False

        try:
            price = float(
                ticker.get(
                    "lastPrice",
                    0,
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            price = 0.0

        return price > 0

    @staticmethod
    def _candidate_score(
        ticker: dict[str, Any],
    ) -> float:

        try:
            volume = float(
                ticker.get(
                    "quoteVolume",
                    0,
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            volume = 0.0

        try:
            change = abs(
                float(
                    ticker.get(
                        "priceChangePercent",
                        0,
                    )
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            change = 0.0

        volume_component = min(
            60.0,
            (
                max(
                    volume,
                    0.0,
                )
                / 10_000_000.0
            )
            ** 0.5
            * 10.0,
        )

        momentum_component = min(
            30.0,
            change * 5.0,
        )

        liquidity_bonus = (
            10.0
            if volume >= 100_000_000
            else 5.0
            if volume >= 25_000_000
            else 0.0
        )

        return round(
            min(
                100.0,
                volume_component
                + momentum_component
                + liquidity_bonus,
            ),
            2,
        )

    # =====================================================
    # FULL MARKET UNIVERSE
    # =====================================================

    async def build_universe(
        self,
        market: str = "futures",
    ) -> list[dict[str, Any]]:

        market = self.normalize_market(
            market
        )

        tickers = await (
            binance_client.ticker_24h(
                market=market
            )
        )

        if not isinstance(
            tickers,
            list,
        ):
            return []

        universe: list[
            dict[str, Any]
        ] = []

        for ticker in tickers:

            if not self._valid_usdt_symbol(
                ticker
            ):
                continue

            symbol = self.normalize_symbol(
                ticker["symbol"]
            )

            universe.append(
                {
                    "symbol": symbol,
                    "market": market,
                    "price": ticker.get(
                        "lastPrice"
                    ),
                    "price_change_24h": ticker.get(
                        "priceChangePercent",
                        0,
                    ),
                    "quote_volume_24h": ticker.get(
                        "quoteVolume",
                        0,
                    ),
                    "candidate_score": (
                        self._candidate_score(
                            ticker
                        )
                    ),
                }
            )

        universe.sort(
            key=lambda item: float(
                item.get(
                    "candidate_score",
                    0,
                )
            ),
            reverse=True,
        )

        return universe

    # =====================================================
    # SCAN MARKET
    # =====================================================

    async def scan(
        self,
        market: str = "futures",
    ) -> dict[str, Any]:

        market = self.normalize_market(
            market
        )

        universe = await self.build_universe(
            market=market
        )

        candidates = universe[
            : self.deep_analysis_limit
        ]

        return {
            "success": True,
            "market": market,
            "universe_mode": (
                "FULL_MARKET"
            ),
            "scanned_universe": len(
                universe
            ),
            "deep_analysis_limit": (
                self.deep_analysis_limit
            ),
            "selected_candidates": (
                candidates
            ),
            "core_timeframes": list(
                self.CORE_TIMEFRAMES
            ),
            "status": (
                "candidate_universe_ready"
            ),
        }

    # =====================================================
    # COMPATIBILITY HELPERS
    # =====================================================

    async def scan_market(
        self,
        market: str = "futures",
    ) -> dict[str, Any]:

        return await self.scan(
            market=market
        )

    async def scan_markets(
        self,
        market: str = "futures",
    ) -> dict[str, Any]:

        return await self.scan(
            market=market
        )

    async def analyze(
        self,
        symbol: str,
        market: str = "futures",
    ) -> dict[str, Any]:

        return await self.scan_symbol(
            symbol=symbol,
            market=market,
        )

    async def analyze_symbol(
        self,
        symbol: str,
        market: str = "futures",
    ) -> dict[str, Any]:

        return await self.scan_symbol(
            symbol=symbol,
            market=market,
        )


__all__ = [
    "MarketScanner",
]
