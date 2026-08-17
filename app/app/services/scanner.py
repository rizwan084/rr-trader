from __future__ import annotations

from typing import Any, Dict, List, Optional
import asyncio
import math
import statistics

import httpx

from app.config import Settings


class MarketScanner:
    """
    RR Trader market scanner.

    Supports:
    - Binance Futures
    - Binance Spot
    - 24h ticker data
    - OHLCV candles
    - EMA trend
    - Momentum
    - Volume
    - Basic LONG / SHORT scoring
    """

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings()

        self.futures_url = self.settings.binance_futures_url.rstrip("/")
        self.spot_url = self.settings.binance_spot_url.rstrip("/")

        self.timeout = float(self.settings.request_timeout)
        self.min_confidence = int(self.settings.min_confidence)

    # ---------------------------------------------------------
    # HTTP
    # ---------------------------------------------------------

    async def _get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:

        async with httpx.AsyncClient(
            timeout=self.timeout,
            headers={"User-Agent": "RR-Trader/1.0"},
        ) as client:

            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()

    # ---------------------------------------------------------
    # MARKET DATA
    # ---------------------------------------------------------

    async def get_24h_tickers(self, market: str = "futures") -> List[Dict]:
        """
        Get Binance 24h ticker data.
        """

        market = market.lower()

        if market == "spot":
            url = f"{self.spot_url}/api/v3/ticker/24hr"
        else:
            url = f"{self.futures_url}/fapi/v1/ticker/24hr"

        data = await self._get(url)

        if not isinstance(data, list):
            return []

        return data

    async def get_klines(
        self,
        symbol: str,
        market: str = "futures",
        interval: str = "15m",
        limit: int = 100,
    ) -> List[List]:

        market = market.lower()

        if market == "spot":
            url = f"{self.spot_url}/api/v3/klines"
        else:
            url = f"{self.futures_url}/fapi/v1/klines"

        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }

        data = await self._get(url, params)

        return data if isinstance(data, list) else []

    # ---------------------------------------------------------
    # SYMBOL FILTER
    # ---------------------------------------------------------

    @staticmethod
    def is_valid_usdt_pair(ticker: Dict) -> bool:

        symbol = str(ticker.get("symbol", ""))

        if not symbol.endswith("USDT"):
            return False

        blocked = (
            "UPUSDT",
            "DOWNUSDT",
            "BULLUSDT",
            "BEARUSDT",
        )

        if symbol in blocked:
            return False

        return True

    # ---------------------------------------------------------
    # EMA
    # ---------------------------------------------------------

    @staticmethod
    def ema(values: List[float], period: int) -> float:

        if not values:
            return 0.0

        if len(values) < period:
            return statistics.mean(values)

        multiplier = 2 / (period + 1)

        ema_value = statistics.mean(values[:period])

        for price in values[period:]:
            ema_value = (
                price - ema_value
            ) * multiplier + ema_value

        return ema_value

    # ---------------------------------------------------------
    # MARKET ANALYSIS
    # ---------------------------------------------------------

    @staticmethod
    def analyze_candles(klines: List[List]) -> Dict[str, Any]:

        if len(klines) < 30:
            return {
                "valid": False,
                "reason": "not_enough_candles",
            }

        closes = [float(k[4]) for k in klines]
        highs = [float(k[2]) for k in klines]
        lows = [float(k[3]) for k in klines]
        volumes = [float(k[5]) for k in klines]

        price = closes[-1]

        ema20 = MarketScanner.ema(closes, 20)
        ema50 = MarketScanner.ema(closes, 50)

        previous_price = closes[-6]

        if previous_price == 0:
            momentum = 0.0
        else:
            momentum = (
                (price - previous_price)
                / previous_price
            ) * 100

        avg_volume = (
            statistics.mean(volumes[-20:])
            if len(volumes) >= 20
            else statistics.mean(volumes)
        )

        current_volume = volumes[-1]

        volume_ratio = (
            current_volume / avg_volume
            if avg_volume > 0
            else 1.0
        )

        recent_high = max(highs[-20:])
        recent_low = min(lows[-20:])

        bullish = (
            price > ema20
            and ema20 > ema50
            and momentum > 0
        )

        bearish = (
            price < ema20
            and ema20 < ema50
            and momentum < 0
        )

        return {
            "valid": True,
            "price": price,
            "ema20": ema20,
            "ema50": ema50,
            "momentum": momentum,
            "volume_ratio": volume_ratio,
            "recent_high": recent_high,
            "recent_low": recent_low,
            "bullish": bullish,
            "bearish": bearish,
        }

    # ---------------------------------------------------------
    # SCORE
    # ---------------------------------------------------------

    @staticmethod
    def calculate_score(
        ticker: Dict,
        analysis: Dict[str, Any],
    ) -> Dict[str, Any]:

        if not analysis.get("valid"):
            return {
                "direction": "NEUTRAL",
                "confidence": 0,
                "reasons": [],
            }

        price_change = float(
            ticker.get("priceChangePercent", 0)
        )

        quote_volume = float(
            ticker.get("quoteVolume", 0)
        )

        momentum = float(
            analysis.get("momentum", 0)
        )

        volume_ratio = float(
            analysis.get("volume_ratio", 1)
        )

        bullish = bool(analysis.get("bullish"))
        bearish = bool(analysis.get("bearish"))

        long_score = 0
        short_score = 0

        long_reasons: List[str] = []
        short_reasons: List[str] = []

        # EMA trend
        if bullish:
            long_score += 30
            long_reasons.append("EMA bullish trend")

        if bearish:
            short_score += 30
            short_reasons.append("EMA bearish trend")

        # Momentum
        if momentum > 0:
            long_score += 20
            long_reasons.append("positive momentum")

        elif momentum < 0:
            short_score += 20
            short_reasons.append("negative momentum")

        # 24h price change
        if price_change > 0:
            long_score += 15
            long_reasons.append("positive 24h move")

        elif price_change < 0:
            short_score += 15
            short_reasons.append("negative 24h move")

        # Volume
        if volume_ratio >= 1.2:

            if momentum > 0:
                long_score += 20
                long_reasons.append("volume confirmation")

            elif momentum < 0:
                short_score += 20
                short_reasons.append("volume confirmation")

        # Liquidity
        if quote_volume >= 10_000_000:

            if momentum > 0:
                long_score += 15
                long_reasons.append("high liquidity")

            elif momentum < 0:
                short_score += 15
                short_reasons.append("high liquidity")

        if long_score > short_score:
            direction = "LONG"
            confidence = min(long_score, 100)
            reasons = long_reasons

        elif short_score > long_score:
            direction = "SHORT"
            confidence = min(short_score, 100)
            reasons = short_reasons

        else:
            direction = "NEUTRAL"
            confidence = 0
            reasons = []

        return {
            "direction": direction,
            "confidence": confidence,
            "reasons": reasons,
        }

    # ---------------------------------------------------------
    # SCAN
    # ---------------------------------------------------------

    async def scan(
        self,
        market: str = "futures",
        interval: str = "15m",
        limit: int = 100,
        max_candidates: Optional[int] = None,
    ) -> Dict[str, Any]:

        market = market.lower()

        if market not in ("futures", "spot"):
            raise ValueError(
                "market must be 'futures' or 'spot'"
            )

        tickers = await self.get_24h_tickers(market)

        valid = [
            ticker
            for ticker in tickers
            if self.is_valid_usdt_pair(ticker)
        ]

        # Highest quote volume first
        valid.sort(
            key=lambda x: float(
                x.get("quoteVolume", 0)
            ),
            reverse=True,
        )

        scan_limit = (
            max_candidates
            if max_candidates is not None
            else int(self.settings.auto_scan_coins)
        )

        candidates = valid[:scan_limit]

        results: List[Dict[str, Any]] = []

        for ticker in candidates:

            symbol = ticker.get("symbol")

            try:

                klines = await self.get_klines(
                    symbol=symbol,
                    market=market,
                    interval=interval,
                    limit=limit,
                )

                analysis = self.analyze_candles(
                    klines
                )

                score = self.calculate_score(
                    ticker,
                    analysis,
                )

                result = {
                    "symbol": symbol,
                    "market": market,
                    "price": float(
                        ticker.get("lastPrice", 0)
                    ),
                    "price_change_24h": float(
                        ticker.get(
                            "priceChangePercent",
                            0,
                        )
                    ),
                    "quote_volume_24h": float(
                        ticker.get(
                            "quoteVolume",
                            0,
                        )
                    ),
                    "direction": score["direction"],
                    "confidence": score["confidence"],
                    "reasons": score["reasons"],
                    "analysis": analysis,
                }

                results.append(result)

            except Exception as exc:

                results.append(
                    {
                        "symbol": symbol,
                        "market": market,
                        "direction": "ERROR",
                        "confidence": 0,
                        "error": str(exc),
                    }
                )

        # Highest confidence first
        results.sort(
            key=lambda x: x.get(
                "confidence",
                0,
            ),
            reverse=True,
        )

        publishable = [
            item
            for item in results
            if item.get("confidence", 0)
            >= self.min_confidence
            and item.get("direction")
            in ("LONG", "SHORT")
        ]

        return {
            "success": True,
            "market": market,
            "interval": interval,
            "scanned": len(results),
            "publishable": len(publishable),
            "min_confidence": self.min_confidence,
            "candidates": results,
            "top_signals": publishable,
        }


# ---------------------------------------------------------
# SIMPLE HELPER
# ---------------------------------------------------------

async def scan_market(
    market: str = "futures",
    interval: str = "15m",
) -> Dict[str, Any]:

    scanner = MarketScanner()

    return await scanner.scan(
        market=market,
        interval=interval,
    )
