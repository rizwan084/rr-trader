from __future__ import annotations

from typing import Any, Dict, List, Optional
import statistics

import httpx

# IMPORTANT:
# Project structure:
# app/
#   app/
#     config.py
#     services/
#       scanner.py
#
# Isliye scanner.py se config ko parent package se import karna hai.
from ..config import Settings


class MarketScanner:
    """
    RR Trader Live Market Scanner.

    Supports:
    - Binance Futures
    - Binance Spot
    - 24h ticker
    - OHLCV candles
    - EMA20 / EMA50
    - Momentum
    - Volume confirmation
    - LONG / SHORT scoring
    - Single-symbol analysis
    """

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings()

        self.futures_url = (
            self.settings.binance_futures_url.rstrip("/")
        )

        self.spot_url = (
            self.settings.binance_spot_url.rstrip("/")
        )

        self.timeout = float(
            self.settings.request_timeout
        )

        self.min_confidence = int(
            self.settings.min_confidence
        )

    # =========================================================
    # HTTP
    # =========================================================

    async def _get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        async with httpx.AsyncClient(
            timeout=self.timeout,
            headers={
                "User-Agent": "RR-Trader/2.0",
            },
        ) as client:

            response = await client.get(
                url,
                params=params,
            )

            response.raise_for_status()

            return response.json()

    # =========================================================
    # BASE URL
    # =========================================================

    def _base_url(self, market: str) -> str:
        market = market.lower().strip()

        if market == "spot":
            return self.spot_url

        if market == "futures":
            return self.futures_url

        raise ValueError(
            "market must be 'futures' or 'spot'"
        )

    # =========================================================
    # 24H TICKERS
    # =========================================================

    async def get_24h_tickers(
        self,
        market: str = "futures",
    ) -> List[Dict[str, Any]]:

        market = market.lower().strip()

        if market == "spot":
            url = f"{self.spot_url}/api/v3/ticker/24hr"

        elif market == "futures":
            url = f"{self.futures_url}/fapi/v1/ticker/24hr"

        else:
            raise ValueError(
                "market must be 'futures' or 'spot'"
            )

        data = await self._get(url)

        if not isinstance(data, list):
            return []

        return data

    # =========================================================
    # SINGLE TICKER
    # =========================================================

    async def get_ticker(
        self,
        symbol: str,
        market: str = "futures",
    ) -> Dict[str, Any]:

        market = market.lower().strip()
        symbol = symbol.upper().replace("/", "").strip()

        if market == "spot":
            url = f"{self.spot_url}/api/v3/ticker/24hr"

        elif market == "futures":
            url = f"{self.futures_url}/fapi/v1/ticker/24hr"

        else:
            raise ValueError(
                "market must be 'futures' or 'spot'"
            )

        data = await self._get(
            url,
            params={
                "symbol": symbol,
            },
        )

        if not isinstance(data, dict):
            raise ValueError(
                "Invalid Binance ticker response"
            )

        return data

    # =========================================================
    # KLINES
    # =========================================================

    async def get_klines(
        self,
        symbol: str,
        market: str = "futures",
        interval: str = "15m",
        limit: int = 200,
    ) -> List[List[Any]]:

        market = market.lower().strip()
        symbol = symbol.upper().replace("/", "").strip()

        if market == "spot":
            url = f"{self.spot_url}/api/v3/klines"

        elif market == "futures":
            url = f"{self.futures_url}/fapi/v1/klines"

        else:
            raise ValueError(
                "market must be 'futures' or 'spot'"
            )

        data = await self._get(
            url,
            params={
                "symbol": symbol,
                "interval": interval,
                "limit": limit,
            },
        )

        if not isinstance(data, list):
            return []

        return data

    # =========================================================
    # SYMBOL VALIDATION
    # =========================================================

    @staticmethod
    def is_valid_usdt_pair(
        ticker: Dict[str, Any],
    ) -> bool:

        symbol = str(
            ticker.get("symbol", "")
        ).upper()

        if not symbol.endswith("USDT"):
            return False

        blocked_words = (
            "UPUSDT",
            "DOWNUSDT",
            "BULLUSDT",
            "BEARUSDT",
        )

        if any(
            word in symbol
            for word in blocked_words
        ):
            return False

        return True

    # =========================================================
    # EMA
    # =========================================================

    @staticmethod
    def ema(
        values: List[float],
        period: int,
    ) -> float:

        if not values:
            return 0.0

        if len(values) < period:
            return float(
                statistics.mean(values)
            )

        multiplier = 2 / (period + 1)

        ema_value = statistics.mean(
            values[:period]
        )

        for price in values[period:]:
            ema_value = (
                (price - ema_value)
                * multiplier
            ) + ema_value

        return float(ema_value)

    # =========================================================
    # ATR
    # =========================================================

    @staticmethod
    def atr(
        klines: List[List[Any]],
        period: int = 14,
    ) -> float:

        if len(klines) < period + 1:
            return 0.0

        try:
            highs = [
                float(k[2])
                for k in klines
            ]

            lows = [
                float(k[3])
                for k in klines
            ]

            closes = [
                float(k[4])
                for k in klines
            ]

        except (
            ValueError,
            TypeError,
            IndexError,
        ):
            return 0.0

        true_ranges: List[float] = []

        for i in range(1, len(klines)):
            high = highs[i]
            low = lows[i]
            previous_close = closes[i - 1]

            true_range = max(
                high - low,
                abs(high - previous_close),
                abs(low - previous_close),
            )

            true_ranges.append(
                true_range
            )

        if len(true_ranges) < period:
            return 0.0

        return float(
            statistics.mean(
                true_ranges[-period:]
            )
        )

    # =========================================================
    # CANDLE ANALYSIS
    # =========================================================

    @classmethod
    def analyze_candles(
        cls,
        klines: List[List[Any]],
    ) -> Dict[str, Any]:

        if len(klines) < 50:
            return {
                "valid": False,
                "reason": "not_enough_candles",
            }

        try:
            closes = [
                float(k[4])
                for k in klines
            ]

            highs = [
                float(k[2])
                for k in klines
            ]

            lows = [
                float(k[3])
                for k in klines
            ]

            volumes = [
                float(k[5])
                for k in klines
            ]

        except (
            ValueError,
            TypeError,
            IndexError,
        ):
            return {
                "valid": False,
                "reason": "invalid_candle_data",
            }

        price = closes[-1]

        ema20 = cls.ema(
            closes,
            20,
        )

        ema50 = cls.ema(
            closes,
            50,
        )

        previous_price = closes[-6]

        if previous_price == 0:
            momentum_pct = 0.0
        else:
            momentum_pct = (
                (price - previous_price)
                / previous_price
            ) * 100

        recent_volume = statistics.mean(
            volumes[-10:]
        )

        previous_volume = statistics.mean(
            volumes[-30:-10]
        )

        volume_ratio = (
            recent_volume / previous_volume
            if previous_volume > 0
            else 1.0
        )

        if (
            price > ema20
            and ema20 > ema50
        ):
            direction = "LONG"

        elif (
            price < ema20
            and ema20 < ema50
        ):
            direction = "SHORT"

        else:
            direction = "WAIT"

        confidence = 50.0
        reasons: List[str] = []

        if direction == "LONG":

            confidence += 15

            reasons.append(
                "Price is above EMA20 and EMA50"
            )

            if momentum_pct > 0:
                confidence += 10
                reasons.append(
                    "Positive momentum"
                )

            if volume_ratio > 1.2:
                confidence += 8
                reasons.append(
                    "Volume confirmation"
                )

        elif direction == "SHORT":

            confidence += 15

            reasons.append(
                "Price is below EMA20 and EMA50"
            )

            if momentum_pct < 0:
                confidence += 10
                reasons.append(
                    "Negative momentum"
                )

            if volume_ratio > 1.2:
                confidence += 8
                reasons.append(
                    "Volume confirmation"
                )

        else:

            reasons.append(
                "EMA structure is mixed"
            )

        confidence = round(
            max(
                0,
                min(
                    confidence,
                    100,
                ),
            ),
            2,
        )

        return {
            "valid": True,
            "price": price,
            "ema20": round(ema20, 8),
            "ema50": round(ema50, 8),
            "momentum_pct": round(
                momentum_pct,
                4,
            ),
            "volume_ratio": round(
                volume_ratio,
                4,
            ),
            "direction": direction,
            "confidence": confidence,
            "reasons": reasons,
            "atr": round(
                cls.atr(klines),
                8,
            ),
        }

    # =========================================================
    # SYMBOL ANALYSIS
    # =========================================================

    async def analyze_symbol(
        self,
        symbol: str,
        market: str = "futures",
    ) -> Dict[str, Any]:

        symbol = (
            symbol.upper()
            .replace("/", "")
            .strip()
        )

        market = market.lower().strip()

        if not symbol.endswith("USDT"):
            raise ValueError(
                "Only USDT trading pairs are supported."
            )

        ticker = await self.get_ticker(
            symbol=symbol,
            market=market,
        )

        klines = await self.get_klines(
            symbol=symbol,
            market=market,
            interval=self.settings.default_interval,
            limit=self.settings.default_candle_limit,
        )

        candle_analysis = self.analyze_candles(
            klines
        )

        if not candle_analysis.get("valid"):
            return {
                "success": False,
                "symbol": symbol,
                "market": market,
                "reason": candle_analysis.get(
                    "reason",
                    "analysis_failed",
                ),
            }

        price = float(
            ticker.get(
                "lastPrice",
                candle_analysis["price"],
            )
        )

        direction = candle_analysis[
            "direction"
        ]

        confidence = float(
            candle_analysis["confidence"]
        )

        atr_value = float(
            candle_analysis.get(
                "atr",
                0,
            )
        )

        if atr_value <= 0:
            atr_value = price * 0.01

        entry = price

        if direction == "LONG":

            stop_loss = entry - (
                atr_value * 1.2
            )

            risk = entry - stop_loss

            tp1 = entry + (
                risk * 1.5
            )

            tp2 = entry + (
                risk * 2.5
            )

            tp3 = entry + (
                risk * 3.5
            )

        elif direction == "SHORT":

            stop_loss = entry + (
                atr_value * 1.2
            )

            risk = stop_loss - entry

            tp1 = entry - (
                risk * 1.5
            )

            tp2 = entry - (
                risk * 2.5
            )

            tp3 = entry - (
                risk * 3.5
            )

        else:

            entry = None
            stop_loss = None
            tp1 = None
            tp2 = None
            tp3 = None
            risk = 0.0

        if risk > 0:
            risk_reward = abs(
                tp2 - entry
            ) / risk
        else:
            risk_reward = 0.0

        if risk_reward >= 3:
            confidence += 4

        elif risk_reward >= 2:
            confidence += 2

        confidence = round(
            max(
                0,
                min(
                    confidence,
                    100,
                ),
            ),
            2,
        )

        if (
            direction in {
                "LONG",
                "SHORT",
            }
            and confidence
            >= self.min_confidence
        ):
            signal = direction

        elif direction in {
            "LONG",
            "SHORT",
        }:
            signal = "WATCH"

        else:
            signal = "WAIT"

        if direction == "LONG":

            thesis = (
                "Bullish EMA structure with "
                "supportive momentum and "
                "volume conditions."
            )

        elif direction == "SHORT":

            thesis = (
                "Bearish EMA structure with "
                "negative momentum and "
                "volume conditions."
            )

        else:

            thesis = (
                "Market structure is mixed; "
                "wait for stronger confirmation."
            )

        return {
            "success": True,
            "symbol": symbol,
            "market": market,
            "direction": direction,
            "signal": signal,
            "confidence": confidence,
            "price": price,
            "entry": entry,
            "stop_loss": stop_loss,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "risk_reward": round(
                risk_reward,
                2,
            ),
            "thesis": thesis,
            "technical": candle_analysis,
            "ticker": {
                "last_price": ticker.get(
                    "lastPrice"
                ),
                "price_change_percent": ticker.get(
                    "priceChangePercent"
                ),
                "volume": ticker.get(
                    "volume"
                ),
                "quote_volume": ticker.get(
                    "quoteVolume"
                ),
            },
        }

    # =========================================================
    # CANDIDATES
    # =========================================================

    async def get_candidates(
        self,
        market: str = "futures",
        limit: Optional[int] = None,
    ) -> List[str]:

        if limit is None:
            limit = self.settings.auto_scan_coins

        tickers = await self.get_24h_tickers(
            market
        )

        candidates = []

        for ticker in tickers:

            if not self.is_valid_usdt_pair(
                ticker
            ):
                continue

            symbol = str(
                ticker.get(
                    "symbol",
                    "",
                )
            ).upper()

            if not symbol:
                continue

            try:
                quote_volume = float(
                    ticker.get(
                        "quoteVolume",
                        0,
                    )
                )
            except (
                ValueError,
                TypeError,
            ):
                quote_volume = 0.0

            candidates.append(
                (
                    symbol,
                    quote_volume,
                )
            )

        candidates.sort(
            key=lambda item: item[1],
            reverse=True,
        )

        return [
            symbol
            for symbol, _ in candidates[:limit]
        ]

    # =========================================================
    # SCAN SYMBOL
    # =========================================================

    async def scan_symbol(
        self,
        symbol: str,
        market: str = "futures",
    ) -> Dict[str, Any]:

        return await self.analyze_symbol(
            symbol=symbol,
            market=market,
        )

    # =========================================================
    # SCAN MARKET
    # =========================================================

    async def scan(
        self,
        market: str = "futures",
    ) -> List[Dict[str, Any]]:

        market = market.lower().strip()

        if market not in {
            "spot",
            "futures",
        }:
            raise ValueError(
                "market must be 'spot' or 'futures'"
            )

        candidates = await self.get_candidates(
            market=market,
        )

        results: List[Dict[str, Any]] = []

        for symbol in candidates:

            try:

                analysis = await self.analyze_symbol(
                    symbol=symbol,
                    market=market,
                )

                if (
                    analysis.get("success")
                    and analysis.get("signal")
                    in {
                        "LONG",
                        "SHORT",
                    }
                    and float(
                        analysis.get(
                            "confidence",
                            0,
                        )
                    ) >= self.min_confidence
                ):
                    results.append(
                        analysis
                    )

            except Exception as exc:

                print(
                    f"RR Trader scanner error "
                    f"for {symbol}: {exc}"
                )

        results.sort(
            key=lambda item: float(
                item.get(
                    "confidence",
                    0,
                )
            ),
            reverse=True,
        )

        return results[:10]

    # =========================================================
    # COMPATIBILITY METHODS
    # =========================================================

    async def scan_market(
        self,
        market: str = "futures",
    ) -> List[Dict[str, Any]]:

        return await self.scan(
            market=market
        )

    async def scan_markets(
        self,
        market: str = "futures",
    ) -> List[Dict[str, Any]]:

        return await self.scan(
            market=market
        )

    async def run(
        self,
        market: str = "futures",
    ) -> List[Dict[str, Any]]:

        return await self.scan(
            market=market
        )

    async def execute(
        self,
        market: str = "futures",
    ) -> List[Dict[str, Any]]:

        return await self.scan(
            market=market
        )


__all__ = [
    "MarketScanner",
]
