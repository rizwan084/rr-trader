from __future__ import annotations

import asyncio
import statistics
from typing import Any, Dict, List, Optional, Tuple

import httpx

from ..config import Settings


class MarketScanner:
    """
    RR Trader Multi-Timeframe Market Scanner.

    Markets:
        - Binance Futures
        - Binance Spot

    Timeframes:
        - 1m
        - 2m  (aggregated from 1m)
        - 3m
        - 5m
        - 15m
        - 30m
        - 45m (aggregated from 15m)
        - 1h
        - 4h

    Analysis:
        - 24H price change
        - 24H quote volume
        - liquidity
        - EMA20
        - EMA50
        - momentum
        - candle volume
        - volume ratio
        - trend
        - multi-timeframe confirmation
        - confidence
        - entry / SL / TP
        - risk/reward
    """

    # =========================================================
    # TIMEFRAME CONFIGURATION
    # =========================================================

    TIMEFRAMES = (
        "1m",
        "2m",
        "3m",
        "5m",
        "15m",
        "30m",
        "45m",
        "1h",
        "4h",
    )

    # Native Binance intervals.
    # 2m is created from 1m.
    # 45m is created from 15m.
    NATIVE_TIMEFRAMES = (
        "1m",
        "3m",
        "5m",
        "15m",
        "30m",
        "1h",
        "4h",
    )

    # How strongly each timeframe affects final confidence.
    TIMEFRAME_WEIGHTS: Dict[str, float] = {
        "1m": 0.05,
        "2m": 0.05,
        "3m": 0.06,
        "5m": 0.08,
        "15m": 0.15,
        "30m": 0.16,
        "45m": 0.14,
        "1h": 0.15,
        "4h": 0.16,
    }

    # =========================================================
    # INITIALIZATION
    # =========================================================

    def __init__(
        self,
        settings: Optional[Settings] = None,
    ) -> None:

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

        self.base_candle_limit = max(
            100,
            int(
                self.settings.default_candle_limit
            ),
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
                "User-Agent": "RR-Trader/3.0",
                "Accept": "application/json",
            },
        ) as client:

            response = await client.get(
                url,
                params=params,
            )

            response.raise_for_status()

            return response.json()

    # =========================================================
    # MARKET URL
    # =========================================================

    def _base_url(
        self,
        market: str,
    ) -> str:

        market = market.lower().strip()

        if market == "spot":
            return self.spot_url

        if market == "futures":
            return self.futures_url

        raise ValueError(
            "market must be 'futures' or 'spot'"
        )

    # =========================================================
    # VALIDATION
    # =========================================================

    @staticmethod
    def normalize_symbol(
        symbol: str,
    ) -> str:

        return (
            symbol
            .upper()
            .replace("/", "")
            .replace("-", "")
            .strip()
        )

    @staticmethod
    def validate_market(
        market: str,
    ) -> str:

        market = market.lower().strip()

        if market not in {
            "spot",
            "futures",
        }:
            raise ValueError(
                "market must be 'spot' or 'futures'"
            )

        return market

    # =========================================================
    # 24H TICKERS
    # =========================================================

    async def get_24h_tickers(
        self,
        market: str = "futures",
    ) -> List[Dict[str, Any]]:

        market = self.validate_market(
            market
        )

        if market == "spot":

            url = (
                f"{self.spot_url}"
                "/api/v3/ticker/24hr"
            )

        else:

            url = (
                f"{self.futures_url}"
                "/fapi/v1/ticker/24hr"
            )

        data = await self._get(
            url
        )

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

        market = self.validate_market(
            market
        )

        symbol = self.normalize_symbol(
            symbol
        )

        if market == "spot":

            url = (
                f"{self.spot_url}"
                "/api/v3/ticker/24hr"
            )

        else:

            url = (
                f"{self.futures_url}"
                "/fapi/v1/ticker/24hr"
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

        market = self.validate_market(
            market
        )

        symbol = self.normalize_symbol(
            symbol
        )

        if market == "spot":

            url = (
                f"{self.spot_url}"
                "/api/v3/klines"
            )

        else:

            url = (
                f"{self.futures_url}"
                "/fapi/v1/klines"
            )

        limit = max(
            50,
            min(
                int(limit),
                1000,
            ),
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
    # SYMBOL FILTER
    # =========================================================

    @staticmethod
    def is_valid_usdt_pair(
        ticker: Dict[str, Any],
    ) -> bool:

        symbol = str(
            ticker.get(
                "symbol",
                "",
            )
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
    # SAFE FLOAT
    # =========================================================

    @staticmethod
    def _float(
        value: Any,
        default: float = 0.0,
    ) -> float:

        try:
            return float(value)
        except (
            TypeError,
            ValueError,
        ):
            return default

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

        if period <= 0:
            return 0.0

        if len(values) < period:

            return float(
                statistics.mean(values)
            )

        multiplier = 2.0 / (
            period + 1
        )

        ema_value = statistics.mean(
            values[:period]
        )

        for price in values[period:]:

            ema_value = (
                (
                    price
                    - ema_value
                )
                * multiplier
            ) + ema_value

        return float(
            ema_value
        )

    # =========================================================
    # ATR
    # =========================================================

    @staticmethod
    def atr(
        klines: List[List[Any]],
        period: int = 14,
    ) -> float:

        if len(klines) < (
            period + 1
        ):
            return 0.0

        highs: List[float] = []
        lows: List[float] = []
        closes: List[float] = []

        try:

            for candle in klines:

                highs.append(
                    float(candle[2])
                )

                lows.append(
                    float(candle[3])
                )

                closes.append(
                    float(candle[4])
                )

        except (
            ValueError,
            TypeError,
            IndexError,
        ):

            return 0.0

        true_ranges: List[float] = []

        for index in range(
            1,
            len(klines),
        ):

            high = highs[index]
            low = lows[index]
            previous_close = closes[
                index - 1
            ]

            tr = max(
                high - low,
                abs(
                    high
                    - previous_close
                ),
                abs(
                    low
                    - previous_close
                ),
            )

            true_ranges.append(
                tr
            )

        if len(true_ranges) < period:
            return 0.0

        return float(
            statistics.mean(
                true_ranges[
                    -period:
                ]
            )
        )

    # =========================================================
    # AGGREGATE KLINES
    # =========================================================

    @staticmethod
    def aggregate_klines(
        klines: List[List[Any]],
        group_size: int,
    ) -> List[List[Any]]:

        if group_size <= 1:
            return klines

        if not klines:
            return []

        aggregated: List[
            List[Any]
        ] = []

        total = len(klines)

        usable = (
            total
            // group_size
        ) * group_size

        # Work from the oldest complete groups.
        source = klines[
            total - usable:
        ]

        for start in range(
            0,
            usable,
            group_size,
        ):

            group = source[
                start:
                start + group_size
            ]

            if len(group) != group_size:
                continue

            try:

                open_time = int(
                    group[0][0]
                )

                open_price = float(
                    group[0][1]
                )

                high_price = max(
                    float(
                        candle[2]
                    )
                    for candle in group
                )

                low_price = min(
                    float(
                        candle[3]
                    )
                    for candle in group
                )

                close_price = float(
                    group[-1][4]
                )

                volume = sum(
                    float(
                        candle[5]
                    )
                    for candle in group
                )

                close_time = int(
                    group[-1][6]
                )

                quote_volume = sum(
                    float(
                        candle[7]
                    )
                    for candle in group
                )

                trades = sum(
                    int(
                        candle[8]
                    )
                    for candle in group
                )

                taker_buy_base = sum(
                    float(
                        candle[9]
                    )
                    for candle in group
                )

                taker_buy_quote = sum(
                    float(
                        candle[10]
                    )
                    for candle in group
                )

                aggregated.append(
                    [
                        open_time,
                        str(
                            open_price
                        ),
                        str(
                            high_price
                        ),
                        str(
                            low_price
                        ),
                        str(
                            close_price
                        ),
                        str(
                            volume
                        ),
                        close_time,
                        str(
                            quote_volume
                        ),
                        trades,
                        str(
                            taker_buy_base
                        ),
                        str(
                            taker_buy_quote
                        ),
                        "0",
                    ]
                )

            except (
                ValueError,
                TypeError,
                IndexError,
            ):

                continue

        return aggregated

    # =========================================================
    # GET TIMEFRAME CANDLES
    # =========================================================

    async def get_timeframe_klines(
        self,
        symbol: str,
        market: str,
        timeframe: str,
        limit: Optional[int] = None,
    ) -> List[List[Any]]:

        symbol = self.normalize_symbol(
            symbol
        )

        market = self.validate_market(
            market
        )

        requested_limit = (
            int(limit)
            if limit is not None
            else self.base_candle_limit
        )

        requested_limit = max(
            80,
            min(
                requested_limit,
                300,
            ),
        )

        # -----------------------------------------------------
        # 2m
        # -----------------------------------------------------

        if timeframe == "2m":

            source_limit = min(
                1000,
                (
                    requested_limit
                    * 2
                    + 10
                ),
            )

            one_minute = (
                await self.get_klines(
                    symbol=symbol,
                    market=market,
                    interval="1m",
                    limit=source_limit,
                )
            )

            return self.aggregate_klines(
                one_minute,
                2,
            )[-requested_limit:]

        # -----------------------------------------------------
        # 45m
        # -----------------------------------------------------

        if timeframe == "45m":

            source_limit = min(
                1000,
                (
                    requested_limit
                    * 3
                    + 10
                ),
            )

            fifteen_minute = (
                await self.get_klines(
                    symbol=symbol,
                    market=market,
                    interval="15m",
                    limit=source_limit,
                )
            )

            return self.aggregate_klines(
                fifteen_minute,
                3,
            )[-requested_limit:]

        # -----------------------------------------------------
        # Native Binance timeframe
        # -----------------------------------------------------

        if timeframe not in self.NATIVE_TIMEFRAMES:

            raise ValueError(
                f"Unsupported timeframe: {timeframe}"
            )

        return await self.get_klines(
            symbol=symbol,
            market=market,
            interval=timeframe,
            limit=requested_limit,
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

            opens = [
                float(
                    candle[1]
                )
                for candle in klines
            ]

            highs = [
                float(
                    candle[2]
                )
                for candle in klines
            ]

            lows = [
                float(
                    candle[3]
                )
                for candle in klines
            ]

            closes = [
                float(
                    candle[4]
                )
                for candle in klines
            ]

            volumes = [
                float(
                    candle[5]
                )
                for candle in klines
            ]

            quote_volumes = [
                float(
                    candle[7]
                )
                for candle in klines
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

        # -----------------------------------------------------
        # MOMENTUM
        # -----------------------------------------------------

        lookback = min(
            5,
            len(closes) - 1,
        )

        previous_price = closes[
            -1 - lookback
        ]

        if previous_price == 0:

            momentum_pct = 0.0

        else:

            momentum_pct = (
                (
                    price
                    - previous_price
                )
                / previous_price
            ) * 100

        # -----------------------------------------------------
        # VOLUME
        # -----------------------------------------------------

        if len(volumes) >= 21:

            previous_volumes = (
                volumes[-21:-1]
            )

        else:

            previous_volumes = (
                volumes[:-1]
            )

        avg_volume = (
            statistics.mean(
                previous_volumes
            )
            if previous_volumes
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

        # -----------------------------------------------------
        # QUOTE VOLUME
        # -----------------------------------------------------

        if len(
            quote_volumes
        ) >= 21:

            previous_quote = (
                quote_volumes[
                    -21:-1
                ]
            )

        else:

            previous_quote = (
                quote_volumes[:-1]
            )

        avg_quote_volume = (
            statistics.mean(
                previous_quote
            )
            if previous_quote
            else 0.0
        )

        current_quote_volume = (
            quote_volumes[-1]
        )

        if avg_quote_volume > 0:

            quote_volume_ratio = (
                current_quote_volume
                / avg_quote_volume
            )

        else:

            quote_volume_ratio = 1.0

        # -----------------------------------------------------
        # STRUCTURE
        # -----------------------------------------------------

        recent_high = max(
            highs[-20:]
        )

        recent_low = min(
            lows[-20:]
        )

        # -----------------------------------------------------
        # CANDLE BODY
        # -----------------------------------------------------

        body = abs(
            closes[-1]
            - opens[-1]
        )

        candle_range = max(
            highs[-1]
            - lows[-1],
            1e-12,
        )

        body_ratio = (
            body
            / candle_range
        )

        # -----------------------------------------------------
        # TREND
        # -----------------------------------------------------

        ema_bullish = (
            price > ema20
            and ema20 > ema50
        )

        ema_bearish = (
            price < ema20
            and ema20 < ema50
        )

        momentum_bullish = (
            momentum_pct > 0
        )

        momentum_bearish = (
            momentum_pct < 0
        )

        bullish = (
            ema_bullish
            and momentum_bullish
        )

        bearish = (
            ema_bearish
            and momentum_bearish
        )

        if bullish:

            direction = "LONG"

        elif bearish:

            direction = "SHORT"

        else:

            direction = "NEUTRAL"

        # -----------------------------------------------------
        # TREND STRENGTH
        # -----------------------------------------------------

        if ema50 != 0:

            ema_distance_pct = (
                (
                    price
                    - ema50
                )
                / ema50
            ) * 100

        else:

            ema_distance_pct = 0.0

        return {
            "valid": True,
            "price": price,
            "ema20": round(
                ema20,
                8,
            ),
            "ema50": round(
                ema50,
                8,
            ),
            "momentum": round(
                momentum_pct,
                6,
            ),
            "volume_ratio": round(
                volume_ratio,
                6,
            ),
            "quote_volume_ratio": round(
                quote_volume_ratio,
                6,
            ),
            "current_volume": current_volume,
            "average_volume": avg_volume,
            "current_quote_volume": (
                current_quote_volume
            ),
            "average_quote_volume": (
                avg_quote_volume
            ),
            "recent_high": recent_high,
            "recent_low": recent_low,
            "body_ratio": round(
                body_ratio,
                4,
            ),
            "ema_distance_pct": round(
                ema_distance_pct,
                6,
            ),
            "bullish": bullish,
            "bearish": bearish,
            "direction": direction,
            "atr": round(
                cls.atr(klines),
                8,
            ),
        }

    # =========================================================
    # TIMEFRAME SCORING
    # =========================================================

    @staticmethod
    def score_timeframe(
        timeframe: str,
        analysis: Dict[str, Any],
    ) -> Dict[str, Any]:

        if not analysis.get(
            "valid"
        ):

            return {
                "timeframe": timeframe,
                "direction": "NEUTRAL",
                "confidence": 0.0,
                "score": 0.0,
                "volume_score": 0.0,
                "reasons": [
                    analysis.get(
                        "reason",
                        "invalid",
                    )
                ],
            }

        bullish_score = 0.0
        bearish_score = 0.0

        reasons: List[str] = []

        # -----------------------------------------------------
        # EMA
        # -----------------------------------------------------

        if analysis.get(
            "ema20",
            0,
        ) > analysis.get(
            "ema50",
            0,
        ):

            bullish_score += 30

            reasons.append(
                "EMA20 above EMA50"
            )

        elif analysis.get(
            "ema20",
            0,
        ) < analysis.get(
            "ema50",
            0,
        ):

            bearish_score += 30

            reasons.append(
                "EMA20 below EMA50"
            )

        # -----------------------------------------------------
        # PRICE VS EMA20
        # -----------------------------------------------------

        if analysis.get(
            "price",
            0,
        ) > analysis.get(
            "ema20",
            0,
        ):

            bullish_score += 15

            reasons.append(
                "price above EMA20"
            )

        elif analysis.get(
            "price",
            0,
        ) < analysis.get(
            "ema20",
            0,
        ):

            bearish_score += 15

            reasons.append(
                "price below EMA20"
            )

        # -----------------------------------------------------
        # MOMENTUM
        # -----------------------------------------------------

        momentum = float(
            analysis.get(
                "momentum",
                0,
            )
        )

        if momentum > 0:

            bullish_score += 20

            reasons.append(
                "positive momentum"
            )

        elif momentum < 0:

            bearish_score += 20

            reasons.append(
                "negative momentum"
            )

        # -----------------------------------------------------
        # VOLUME
        # -----------------------------------------------------

        volume_ratio = float(
            analysis.get(
                "volume_ratio",
                1.0,
            )
        )

        volume_score = 0.0

        if volume_ratio >= 1.50:

            volume_score = 15

            if momentum > 0:

                bullish_score += volume_score

                reasons.append(
                    "strong bullish volume confirmation"
                )

            elif momentum < 0:

                bearish_score += volume_score

                reasons.append(
                    "strong bearish volume confirmation"
                )

        elif volume_ratio >= 1.20:

            volume_score = 10

            if momentum > 0:

                bullish_score += volume_score

                reasons.append(
                    "volume confirmation"
                )

            elif momentum < 0:

                bearish_score += volume_score

                reasons.append(
                    "volume confirmation"
                )

        elif volume_ratio >= 1.00:

            volume_score = 5

            reasons.append(
                "normal volume"
            )

        else:

            reasons.append(
                "volume below average"
            )

        # -----------------------------------------------------
        # FINAL TIMEFRAME DIRECTION
        # -----------------------------------------------------

        if (
            bullish_score
            > bearish_score
        ):

            direction = "LONG"

            confidence = min(
                100.0,
                bullish_score,
            )

        elif (
            bearish_score
            > bullish_score
        ):

            direction = "SHORT"

            confidence = min(
                100.0,
                bearish_score,
            )

        else:

            direction = "NEUTRAL"

            confidence = 0.0

        return {
            "timeframe": timeframe,
            "direction": direction,
            "confidence": round(
                confidence,
                2,
            ),
            "score": round(
                max(
                    bullish_score,
                    bearish_score,
                ),
                2,
            ),
            "bullish_score": round(
                bullish_score,
                2,
            ),
            "bearish_score": round(
                bearish_score,
                2,
            ),
            "volume_score": round(
                volume_score,
                2,
            ),
            "reasons": reasons,
        }

    # =========================================================
    # 24H LIQUIDITY
    # =========================================================

    @staticmethod
    def analyze_24h(
        ticker: Dict[str, Any],
    ) -> Dict[str, Any]:

        price_change = MarketScanner._float(
            ticker.get(
                "priceChangePercent",
                0,
            )
        )

        quote_volume = MarketScanner._float(
            ticker.get(
                "quoteVolume",
                0,
            )
        )

        last_price = MarketScanner._float(
            ticker.get(
                "lastPrice",
                0,
            )
        )

        # -----------------------------------------------------
        # Liquidity score
        # -----------------------------------------------------

        if quote_volume >= 1_000_000_000:

            liquidity = 25
            liquidity_label = "extreme"

        elif quote_volume >= 100_000_000:

            liquidity = 20
            liquidity_label = "very_high"

        elif quote_volume >= 25_000_000:

            liquidity = 15
            liquidity_label = "high"

        elif quote_volume >= 10_000_000:

            liquidity = 10
            liquidity_label = "good"

        elif quote_volume >= 2_000_000:

            liquidity = 5
            liquidity_label = "moderate"

        else:

            liquidity = 0
            liquidity_label = "low"

        # -----------------------------------------------------
        # 24H direction
        # -----------------------------------------------------

        if price_change > 0:

            direction = "LONG"

        elif price_change < 0:

            direction = "SHORT"

        else:

            direction = "NEUTRAL"

        return {
            "price": last_price,
            "price_change_24h": round(
                price_change,
                4,
            ),
            "quote_volume_24h": quote_volume,
            "liquidity_score": liquidity,
            "liquidity": liquidity_label,
            "direction": direction,
        }

    # =========================================================
    # MULTI-TIMEFRAME AGGREGATION
    # =========================================================

    @classmethod
    def combine_timeframes(
        cls,
        timeframe_scores: Dict[
            str,
            Dict[str, Any],
        ],
    ) -> Dict[str, Any]:

        long_score = 0.0
        short_score = 0.0

        active_weight = 0.0

        long_timeframes: List[str] = []
        short_timeframes: List[str] = []
        neutral_timeframes: List[str] = []

        weighted_details: Dict[
            str,
            Dict[str, Any],
        ] = {}

        for timeframe in cls.TIMEFRAMES:

            item = timeframe_scores.get(
                timeframe
            )

            if not item:
                continue

            direction = item.get(
                "direction",
                "NEUTRAL",
            )

            confidence = float(
                item.get(
                    "confidence",
                    0,
                )
            )

            weight = float(
                cls.TIMEFRAME_WEIGHTS.get(
                    timeframe,
                    0,
                )
            )

            if direction not in {
                "LONG",
                "SHORT",
            }:

                neutral_timeframes.append(
                    timeframe
                )

                continue

            contribution = (
                confidence
                * weight
            )

            active_weight += weight

            if direction == "LONG":

                long_score += (
                    contribution
                )

                long_timeframes.append(
                    timeframe
                )

            else:

                short_score += (
                    contribution
                )

                short_timeframes.append(
                    timeframe
                )

            weighted_details[
                timeframe
            ] = {
                "direction": direction,
                "confidence": round(
                    confidence,
                    2,
                ),
                "weight": weight,
                "contribution": round(
                    contribution,
                    2,
                ),
            }

        if active_weight <= 0:

            return {
                "direction": "NEUTRAL",
                "confidence": 0.0,
                "long_score": 0.0,
                "short_score": 0.0,
                "long_timeframes": [],
                "short_timeframes": [],
                "neutral_timeframes": neutral_timeframes,
                "details": weighted_details,
            }

        # Normalize weighted score.
        normalized_long = (
            long_score
            / active_weight
        )

        normalized_short = (
            short_score
            / active_weight
        )

        if (
            normalized_long
            > normalized_short
        ):

            direction = "LONG"

            base_confidence = (
                normalized_long
            )

        elif (
            normalized_short
            > normalized_long
        ):

            direction = "SHORT"

            base_confidence = (
                normalized_short
            )

        else:

            direction = "NEUTRAL"
            base_confidence = 0.0

        # -----------------------------------------------------
        # Conflict penalty
        # -----------------------------------------------------

        directional_count = (
            len(long_timeframes)
            + len(short_timeframes)
        )

        if directional_count > 0:

            dominant_count = max(
                len(long_timeframes),
                len(short_timeframes),
            )

            agreement_ratio = (
                dominant_count
                / directional_count
            )

        else:

            agreement_ratio = 0.0

        conflict_penalty = 0.0

        if agreement_ratio < 0.55:

            conflict_penalty = 20.0

        elif agreement_ratio < 0.65:

            conflict_penalty = 12.0

        elif agreement_ratio < 0.75:

            conflict_penalty = 6.0

        final_confidence = max(
            0.0,
            min(
                100.0,
                base_confidence
                - conflict_penalty,
            ),
        )

        return {
            "direction": direction,
            "confidence": round(
                final_confidence,
                2,
            ),
            "long_score": round(
                normalized_long,
                2,
            ),
            "short_score": round(
                normalized_short,
                2,
            ),
            "agreement_ratio": round(
                agreement_ratio,
                4,
            ),
            "conflict_penalty": round(
                conflict_penalty,
                2,
            ),
            "long_timeframes": long_timeframes,
            "short_timeframes": short_timeframes,
            "neutral_timeframes": neutral_timeframes,
            "details": weighted_details,
        }

    # =========================================================
    # TRADE LEVELS
    # =========================================================

    @staticmethod
    def calculate_trade_levels(
        direction: str,
        price: float,
        atr_value: float,
    ) -> Dict[str, Optional[float]]:

        if price <= 0:

            return {
                "entry": None,
                "stop_loss": None,
                "tp1": None,
                "tp2": None,
                "tp3": None,
                "risk_reward": 0.0,
            }

        if atr_value <= 0:

            atr_value = (
                price * 0.01
            )

        entry = price

        if direction == "LONG":

            stop_loss = (
                entry
                - (
                    atr_value
                    * 1.2
                )
            )

            risk = (
                entry
                - stop_loss
            )

            tp1 = (
                entry
                + risk * 1.5
            )

            tp2 = (
                entry
                + risk * 2.5
            )

            tp3 = (
                entry
                + risk * 3.5
            )

        elif direction == "SHORT":

            stop_loss = (
                entry
                + (
                    atr_value
                    * 1.2
                )
            )

            risk = (
                stop_loss
                - entry
            )

            tp1 = (
                entry
                - risk * 1.5
            )

            tp2 = (
                entry
                - risk * 2.5
            )

            tp3 = (
                entry
                - risk * 3.5
            )

        else:

            return {
                "entry": None,
                "stop_loss": None,
                "tp1": None,
                "tp2": None,
                "tp3": None,
                "risk_reward": 0.0,
            }

        risk_reward = (
            abs(
                tp2 - entry
            )
            / risk
            if risk > 0
            else 0.0
        )

        return {
            "entry": round(
                entry,
                8,
            ),
            "stop_loss": round(
                stop_loss,
                8,
            ),
            "tp1": round(
                tp1,
                8,
            ),
            "tp2": round(
                tp2,
                8,
            ),
            "tp3": round(
                tp3,
                8,
            ),
            "risk_reward": round(
                risk_reward,
                2,
            ),
        }

    # =========================================================
    # BUILD REASONS
    # =========================================================

    @staticmethod
    def build_final_reasons(
        combined: Dict[str, Any],
        analysis_15m: Dict[str, Any],
        liquidity: Dict[str, Any],
    ) -> List[str]:

        reasons: List[str] = []

        direction = combined.get(
            "direction",
            "NEUTRAL",
        )

        long_tfs = combined.get(
            "long_timeframes",
            [],
        )

        short_tfs = combined.get(
            "short_timeframes",
            [],
        )

        agreement = float(
            combined.get(
                "agreement_ratio",
                0,
            )
        )

        liquidity_score = float(
            liquidity.get(
                "liquidity_score",
                0,
            )
        )

        volume_ratio = float(
            analysis_15m.get(
                "volume_ratio",
                1,
            )
        )

        if direction == "LONG":

            if long_tfs:

                reasons.append(
                    "multi-timeframe bullish confirmation: "
                    + ", ".join(
                        long_tfs
                    )
                )

            if short_tfs:

                reasons.append(
                    "timeframe conflict: "
                    + ", ".join(
                        short_tfs
                    )
                )

            if (
                volume_ratio >= 1.5
            ):

                reasons.append(
                    "strong 15m volume confirmation"
                )

            elif (
                volume_ratio >= 1.2
            ):

                reasons.append(
                    "15m volume confirmation"
                )

        elif direction == "SHORT":

            if short_tfs:

                reasons.append(
                    "multi-timeframe bearish confirmation: "
                    + ", ".join(
                        short_tfs
                    )
                )

            if long_tfs:

                reasons.append(
                    "timeframe conflict: "
                    + ", ".join(
                        long_tfs
                    )
                )

            if (
                volume_ratio >= 1.5
            ):

                reasons.append(
                    "strong 15m volume confirmation"
                )

            elif (
                volume_ratio >= 1.2
            ):

                reasons.append(
                    "15m volume confirmation"
                )

        else:

            reasons.append(
                "timeframes are not sufficiently aligned"
            )

        if liquidity_score >= 15:

            reasons.append(
                "high liquidity"
            )

        elif liquidity_score >= 10:

            reasons.append(
                "good liquidity"
            )

        elif liquidity_score <= 0:

            reasons.append(
                "low liquidity"
            )

        if (
            agreement >= 0.75
        ):

            reasons.append(
                "strong timeframe agreement"
            )

        elif (
            agreement < 0.60
        ):

            reasons.append(
                "significant timeframe conflict"
            )

        return reasons

    # =========================================================
    # SINGLE SYMBOL SCAN
    # =========================================================

    async def scan_symbol(
        self,
        symbol: str,
        market: str = "futures",
        interval: str = "15m",
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:

        market = self.validate_market(
            market
        )

        symbol = self.normalize_symbol(
            symbol
        )

        if not symbol.endswith(
            "USDT"
        ):

            raise ValueError(
                "Only USDT pairs are supported."
            )

        requested_limit = (
            int(limit)
            if limit is not None
            else self.base_candle_limit
        )

        requested_limit = max(
            80,
            min(
                requested_limit,
                300,
            ),
        )

        # -----------------------------------------------------
        # Get 24H ticker first.
        # -----------------------------------------------------

        ticker_task = (
            self.get_ticker(
                symbol,
                market,
            )
        )

        # -----------------------------------------------------
        # Fetch all native timeframes concurrently.
        # -----------------------------------------------------

        native_tasks = {
            timeframe: asyncio.create_task(
                self.get_timeframe_klines(
                    symbol=symbol,
                    market=market,
                    timeframe=timeframe,
                    limit=requested_limit,
                )
            )
            for timeframe in self.NATIVE_TIMEFRAMES
        }

        ticker = await ticker_task

        native_results: Dict[
            str,
            List[List[Any]],
        ] = {}

        for timeframe, task in (
            native_tasks.items()
        ):

            try:

                native_results[
                    timeframe
                ] = await task

            except Exception:

                native_results[
                    timeframe
                ] = []

        # -----------------------------------------------------
        # Build synthetic timeframes.
        # -----------------------------------------------------

        one_minute = native_results.get(
            "1m",
            [],
        )

        fifteen_minute = native_results.get(
            "15m",
            [],
        )

        timeframe_klines: Dict[
            str,
            List[List[Any]],
        ] = {}

        for timeframe in (
            "1m",
            "3m",
            "5m",
            "15m",
            "30m",
            "1h",
            "4h",
        ):

            timeframe_klines[
                timeframe
            ] = native_results.get(
                timeframe,
                [],
            )

        timeframe_klines[
            "2m"
        ] = self.aggregate_klines(
            one_minute,
            2,
        )[-requested_limit:]

        timeframe_klines[
            "45m"
        ] = self.aggregate_klines(
            fifteen_minute,
            3,
        )[-requested_limit:]

        # -----------------------------------------------------
        # Analyze every timeframe.
        # -----------------------------------------------------

        timeframe_analysis: Dict[
            str,
            Dict[str, Any],
        ] = {}

        timeframe_scores: Dict[
            str,
            Dict[str, Any],
        ] = {}

        for timeframe in self.TIMEFRAMES:

            klines = timeframe_klines.get(
                timeframe,
                [],
            )

            analysis = (
                self.analyze_candles(
                    klines
                )
            )

            score = (
                self.score_timeframe(
                    timeframe,
                    analysis,
                )
            )

            timeframe_analysis[
                timeframe
            ] = analysis

            timeframe_scores[
                timeframe
            ] = score

        # -----------------------------------------------------
        # 24H analysis
        # -----------------------------------------------------

        liquidity = (
            self.analyze_24h(
                ticker
            )
        )

        # -----------------------------------------------------
        # Final multi-timeframe result
        # -----------------------------------------------------

        combined = (
            self.combine_timeframes(
                timeframe_scores
            )
        )

        direction = combined.get(
            "direction",
            "NEUTRAL",
        )

        confidence = float(
            combined.get(
                "confidence",
                0,
            )
        )

        # -----------------------------------------------------
        # Liquidity adjustment.
        # -----------------------------------------------------

        liquidity_score = float(
            liquidity.get(
                "liquidity_score",
                0,
            )
        )

        if liquidity_score >= 15:

            confidence += 4

        elif liquidity_score >= 10:

            confidence += 2

        elif liquidity_score <= 0:

            confidence -= 5

        confidence = max(
            0.0,
            min(
                confidence,
                100.0,
            ),
        )

        # -----------------------------------------------------
        # 15m is the execution/reference timeframe.
        # -----------------------------------------------------

        analysis_15m = (
            timeframe_analysis.get(
                "15m",
                {},
            )
        )

        atr_15m = float(
            analysis_15m.get(
                "atr",
                0,
            )
        )

        current_price = self._float(
            ticker.get(
                "lastPrice",
                analysis_15m.get(
                    "price",
                    0,
                ),
            )
        )

        trade_levels = (
            self.calculate_trade_levels(
                direction=direction,
                price=current_price,
                atr_value=atr_15m,
            )
        )

        # -----------------------------------------------------
        # Final reasons
        # -----------------------------------------------------

        reasons = (
            self.build_final_reasons(
                combined=combined,
                analysis_15m=analysis_15m,
                liquidity=liquidity,
            )
        )

        # -----------------------------------------------------
        # Publishable signal
        # -----------------------------------------------------

        publishable = (
            direction
            in {
                "LONG",
                "SHORT",
            }
            and confidence
            >= self.min_confidence
        )

        # If timeframe agreement is weak,
        # do not publish regardless of raw score.
        agreement_ratio = float(
            combined.get(
                "agreement_ratio",
                0,
            )
        )

        if agreement_ratio < 0.55:

            publishable = False

        # -----------------------------------------------------
        # 24H data
        # -----------------------------------------------------

        price_change_24h = self._float(
            ticker.get(
                "priceChangePercent",
                0,
            )
        )

        quote_volume_24h = self._float(
            ticker.get(
                "quoteVolume",
                0,
            )
        )

        # -----------------------------------------------------
        # Result
        # -----------------------------------------------------

        return {
            "success": True,
            "symbol": symbol,
            "market": market,
            "interval": interval,
            "price": current_price,
            "price_change_24h": round(
                price_change_24h,
                4,
            ),
            "quote_volume_24h": quote_volume_24h,
            "direction": direction,
            "confidence": round(
                confidence,
                2,
            ),
            "publishable": publishable,
            "reasons": reasons,

            # Trade plan
            "entry": trade_levels.get(
                "entry"
            ),
            "stop_loss": trade_levels.get(
                "stop_loss"
            ),
            "tp1": trade_levels.get(
                "tp1"
            ),
            "tp2": trade_levels.get(
                "tp2"
            ),
            "tp3": trade_levels.get(
                "tp3"
            ),
            "risk_reward": trade_levels.get(
                "risk_reward",
                0.0,
            ),

            # 24H analysis
            "market_24h": liquidity,

            # Multi-timeframe scores
            "multi_timeframe": combined,

            # Every timeframe
            "timeframes": {
                timeframe: {
                    "analysis": timeframe_analysis.get(
                        timeframe,
                        {},
                    ),
                    "score": timeframe_scores.get(
                        timeframe,
                        {},
                    ),
                }
                for timeframe in self.TIMEFRAMES
            },

            # Keep compatibility with the old API
            # which expected `analysis`.
            "analysis": analysis_15m,
        }

    # =========================================================
    # GENERAL MARKET SCAN
    # =========================================================

    async def scan(
        self,
        market: str = "futures",
        interval: str = "15m",
        limit: Optional[int] = None,
        max_candidates: Optional[int] = None,
    ) -> Dict[str, Any]:

        market = self.validate_market(
            market
        )

        if max_candidates is None:

            max_candidates = int(
                self.settings.auto_scan_coins
            )

        max_candidates = max(
            1,
            min(
                max_candidates,
                30,
            ),
        )

        tickers = await self.get_24h_tickers(
            market
        )

        valid_tickers = [
            ticker
            for ticker in tickers
            if self.is_valid_usdt_pair(
                ticker
            )
        ]

        # -----------------------------------------------------
        # Highest 24H quote-volume first.
        # -----------------------------------------------------

        valid_tickers.sort(
            key=lambda item: self._float(
                item.get(
                    "quoteVolume",
                    0,
                )
            ),
            reverse=True,
        )

        candidates = valid_tickers[
            :max_candidates
        ]

        async def analyze_candidate(
            ticker: Dict[str, Any],
        ) -> Dict[str, Any]:

            symbol = self.normalize_symbol(
                str(
                    ticker.get(
                        "symbol",
                        "",
                    )
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
                    "publishable": False,
                    "error": str(exc),
                }

        results = await asyncio.gather(
            *[
                analyze_candidate(
                    ticker
                )
                for ticker in candidates
            ]
        )

        results = list(
            results
        )

        # -----------------------------------------------------
        # Sort by confidence.
        # -----------------------------------------------------

        results.sort(
            key=lambda item: float(
                item.get(
                    "confidence",
                    0,
                )
            ),
            reverse=True,
        )

        publishable = [
            item
            for item in results
            if item.get(
                "publishable",
                False,
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

    # =========================================================
    # COMPATIBILITY METHODS
    # =========================================================

    async def scan_market(
        self,
        market: str = "futures",
    ) -> Dict[str, Any]:

        return await self.scan(
            market=market
        )

    async def scan_markets(
        self,
        market: str = "futures",
    ) -> Dict[str, Any]:

        return await self.scan(
            market=market
        )

    async def run(
        self,
        market: str = "futures",
    ) -> Dict[str, Any]:

        return await self.scan(
            market=market
        )

    async def execute(
        self,
        market: str = "futures",
    ) -> Dict[str, Any]:

        return await self.scan(
            market=market
        )

    # =========================================================
    # AI / APP FRIENDLY SUMMARY
    # =========================================================

    async def analyze(
        self,
        symbol: str,
        market: str = "futures",
    ) -> Dict[str, Any]:

        return await self.scan_symbol(
            symbol=symbol,
            market=market,
        )

    async def analyze_symbol(
        self,
        symbol: str,
        market: str = "futures",
    ) -> Dict[str, Any]:

        return await self.scan_symbol(
            symbol=symbol,
            market=market,
        )


# =============================================================
# MODULE HELPER
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


__all__ = [
    "MarketScanner",
    "scan_market",
]
