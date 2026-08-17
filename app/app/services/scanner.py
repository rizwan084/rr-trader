from __future__ import annotations

from typing import Any, Dict, List, Optional
import asyncio
import statistics

import httpx

from app.config import Settings


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
    - Liquidity
    - LONG / SHORT scoring
    - Single-symbol analysis
    """

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings()

        self.futures_url = self.settings.binance_futures_url.rstrip("/")
        self.spot_url = self.settings.binance_spot_url.rstrip("/")

        self.timeout = float(self.settings.request_timeout)
        self.min_confidence = int(self.settings.min_confidence)

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
                "User-Agent": "RR-Trader/1.0"
            },
        ) as client:

            response = await client.get(
                url,
                params=params,
            )

            response.raise_for_status()

            return response.json()

    # =========================================================
    # URL
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
            params={"symbol": symbol},
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
        limit: int = 100,
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

        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }

        data = await self._get(
            url,
            params=params,
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

        blocked_exact = {
            "UPUSDT",
            "DOWNUSDT",
            "BULLUSDT",
            "BEARUSDT",
        }

        if symbol in blocked_exact:
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
    # CANDLE ANALYSIS
    # =========================================================

    @staticmethod
    def analyze_candles(
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

        ema20 = MarketScanner.ema(
            closes,
            20,
        )

        ema50 = MarketScanner.ema(
            closes,
            50,
        )

        previous_price = closes[-6]

        if previous_price == 0:

            momentum = 0.0

        else:

            momentum = (
                (
                    price - previous_price
                )
                / previous_price
            ) * 100

        recent_volumes = volumes[-20:]

        avg_volume = (
            statistics.mean(
                recent_volumes
            )
            if recent_volumes
            else 0.0
        )

        current_volume = volumes[-1]

        if avg_volume > 0:

            volume_ratio = (
                current_volume
                / avg_volume
            )

        else:

            volume_ratio = 1.0

        recent_high = max(
            highs[-20:]
        )

        recent_low = min(
            lows[-20:]
        )

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

    # =========================================================
    # SCORE
    # =========================================================

    @staticmethod
    def calculate_score(
        ticker: Dict[str, Any],
        analysis: Dict[str, Any],
    ) -> Dict[str, Any]:

        if not analysis.get("valid"):

            return {
                "direction": "NEUTRAL",
                "confidence": 0,
                "reasons": [],
            }

        try:

            price_change = float(
                ticker.get(
                    "priceChangePercent",
                    0,
                )
            )

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

            price_change = 0.0
            quote_volume = 0.0

        momentum = float(
            analysis.get(
                "momentum",
                0,
            )
        )

        volume_ratio = float(
            analysis.get(
                "volume_ratio",
                1,
            )
        )

        bullish = bool(
            analysis.get("bullish")
        )

        bearish = bool(
            analysis.get("bearish")
        )

        long_score = 0
        short_score = 0

        long_reasons: List[str] = []
        short_reasons: List[str] = []

        # -----------------------------------------------------
        # EMA TREND
        # -----------------------------------------------------

        if bullish:

            long_score += 30

            long_reasons.append(
                "EMA bullish trend"
            )

        if bearish:

            short_score += 30

            short_reasons.append(
                "EMA bearish trend"
            )

        # -----------------------------------------------------
        # MOMENTUM
        # -----------------------------------------------------

        if momentum > 0:

            long_score += 20

            long_reasons.append(
                "positive momentum"
            )

        elif momentum < 0:

            short_score += 20

            short_reasons.append(
                "negative momentum"
            )

        # -----------------------------------------------------
        # 24H MOVE
        # -----------------------------------------------------

        if price_change > 0:

            long_score += 15

            long_reasons.append(
                "positive 24h move"
            )

        elif price_change < 0:

            short_score += 15

            short_reasons.append(
                "negative 24h move"
            )

        # -----------------------------------------------------
        # VOLUME
        # -----------------------------------------------------

        if volume_ratio >= 1.20:

            if momentum > 0:

                long_score += 20

                long_reasons.append(
                    "volume confirmation"
                )

            elif momentum < 0:

                short_score += 20

                short_reasons.append(
                    "volume confirmation"
                )

        # -----------------------------------------------------
        # LIQUIDITY
        # -----------------------------------------------------

        if quote_volume >= 10_000_000:

            if momentum > 0:

                long_score += 15

                long_reasons.append(
                    "high liquidity"
                )

            elif momentum < 0:

                short_score += 15

                short_reasons.append(
                    "high liquidity"
                )

        # -----------------------------------------------------
        # FINAL DIRECTION
        # -----------------------------------------------------

        if long_score > short_score:

            direction = "LONG"

            confidence = min(
                long_score,
                100,
            )

            reasons = long_reasons

        elif short_score > long_score:

            direction = "SHORT"

            confidence = min(
                short_score,
                100,
            )

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

    # =========================================================
    # SINGLE SYMBOL ANALYSIS
    # =========================================================

    async def scan_symbol(
        self,
        symbol: str,
        market: str = "futures",
        interval: str = "15m",
        limit: int = 100,
    ) -> Dict[str, Any]:

        market = market.lower().strip()

        symbol = (
            symbol.upper()
            .replace("/", "")
            .strip()
        )

        if market not in {
            "futures",
            "spot",
        }:

            raise ValueError(
                "market must be 'futures' or 'spot'"
            )

        if not symbol.endswith("USDT"):

            raise ValueError(
                "Only USDT pairs are supported."
            )

        # Get ticker + candles
        ticker, klines = await asyncio.gather(
            self.get_ticker(
                symbol,
                market,
            ),
            self.get_klines(
                symbol,
                market,
                interval,
                limit,
            ),
        )

        analysis = self.analyze_candles(
            klines
        )

        score = self.calculate_score(
            ticker,
            analysis,
        )

        return {
            "success": True,
            "symbol": symbol,
            "market": market,
            "interval": interval,
            "price": float(
                ticker.get(
                    "lastPrice",
                    0,
                )
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
            "direction": score[
                "direction"
            ],
            "confidence": score[
                "confidence"
            ],
            "publishable": (
                score["confidence"]
                >= self.min_confidence
                and score["direction"]
                in ("LONG", "SHORT")
            ),
            "reasons": score[
                "reasons"
            ],
            "analysis": analysis,
        }

    # =========================================================
    # GENERAL MARKET SCAN
    # =========================================================

    async def scan(
        self,
        market: str = "futures",
        interval: str = "15m",
        limit: int = 100,
        max_candidates: Optional[int] = None,
    ) -> Dict[str, Any]:

        market = market.lower().strip()

        if market not in {
            "futures",
            "spot",
        }:

            raise ValueError(
                "market must be 'futures' or 'spot'"
            )

        tickers = await self.get_24h_tickers(
            market
        )

        valid = [
            ticker
            for ticker in tickers
            if self.is_valid_usdt_pair(
                ticker
            )
        ]

        # Highest liquidity first
        valid.sort(
            key=lambda x: float(
                x.get(
                    "quoteVolume",
                    0,
                )
            ),
            reverse=True,
        )

        scan_limit = (
            max_candidates
            if max_candidates is not None
            else int(
                self.settings.auto_scan_coins
            )
        )

        candidates = valid[
            :scan_limit
        ]

        # -----------------------------------------------------
        # Analyze candidates concurrently
        # -----------------------------------------------------

        async def analyze_ticker(
            ticker: Dict[str, Any],
        ) -> Dict[str, Any]:

            symbol = str(
                ticker.get(
                    "symbol",
                    "",
                )
            )

            try:

                return await self.scan_symbol(
                    symbol=symbol,
                    market=market,
                    interval=interval,
                    limit=limit,
                )

            except Exception as exc:

                return {
                    "success": False,
                    "symbol": symbol,
                    "market": market,
                    "direction": "ERROR",
                    "confidence": 0,
                    "error": str(exc),
                }

        results = await asyncio.gather(
            *[
                analyze_ticker(ticker)
                for ticker in candidates
            ]
        )

        results = list(results)

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
            if item.get(
                "confidence",
                0,
            ) >= self.min_confidence
            and item.get(
                "direction"
            ) in (
                "LONG",
                "SHORT",
            )
        ]

        return {
            "success": True,
            "market": market,
            "interval": interval,
            "scanned": len(results),
            "publishable": len(
                publishable
            ),
            "min_confidence": (
                self.min_confidence
            ),
            "candidates": results,
            "top_signals": publishable,
        }


# =============================================================
# HELPER
# =============================================================

async def scan_market(
    market: str = "futures",
    interval: str = "15m",
) -> Dict[str, Any]:

    scanner = MarketScanner()

    return await scanner.scan(
        market=market,
        interval=interval,
    )
