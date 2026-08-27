from __future__ import annotations

from typing import Any


class MarketScanner:
    """
    RR Trader Setup-Aware Market Scanner.

    Responsibilities:
    - Retrieve the full USDT market universe.
    - Filter valid and liquid markets.
    - Avoid using Top Gainers / Top Losers as trade signals.
    - Inspect recent price structure.
    - Detect repeated support tests.
    - Detect repeated resistance tests.
    - Detect support/resistance rejection.
    - Detect basic volume and momentum confirmation.
    - Return setup candidates for deep analysis.

    This service DOES NOT generate final trade signals.

    Final signal validation remains the responsibility of:
        - MarketStructureEngine
        - IndicatorEngine
        - MTFEngine
        - Liquidity / Derivatives engines
        - ConfidenceEngine
        - SignalEngine
    """

    QUOTE_ASSET = "USDT"

    # =====================================================
    # DEFAULT SETTINGS
    # =====================================================

    DEFAULT_INTERVAL = "15m"

    DEFAULT_CANDLE_LIMIT = 120

    # Only the most liquid markets are inspected deeply.
    # This protects Binance/API rate limits while still
    # searching a broad market universe.
    DEFAULT_DISCOVERY_LIMIT = 80

    # Minimum 24h quote volume required before setup scan.
    DEFAULT_MIN_QUOTE_VOLUME = 5_000_000.0

    # Minimum number of candles required for setup detection.
    MIN_CANDLES_REQUIRED = 50

    # Number of recent candles used to determine
    # support / resistance.
    ZONE_LOOKBACK = 80

    # A support/resistance touch is accepted when price
    # is within this percentage of the zone.
    DEFAULT_ZONE_TOLERANCE = 0.006

    # Minimum repeated tests required.
    MIN_SUPPORT_TESTS = 2
    MIN_RESISTANCE_TESTS = 2

    # Stronger setup when 3+ tests occur.
    STRONG_TEST_COUNT = 3

    # Minimum volume ratio for confirmation.
    MIN_VOLUME_RATIO = 1.05

    # Minimum momentum required for directional setup.
    MIN_MOMENTUM_PERCENT = 0.10

    # Recent candles used for rejection detection.
    REJECTION_LOOKBACK = 5

    # =====================================================
    # INITIALIZATION
    # =====================================================

    def __init__(
        self,
        market_data: Any,
        *,
        discovery_limit: int = DEFAULT_DISCOVERY_LIMIT,
        min_quote_volume: float = DEFAULT_MIN_QUOTE_VOLUME,
        candle_limit: int = DEFAULT_CANDLE_LIMIT,
        interval: str = DEFAULT_INTERVAL,
        zone_tolerance: float = DEFAULT_ZONE_TOLERANCE,
    ) -> None:

        self.market_data = market_data

        self.discovery_limit = max(
            1,
            int(discovery_limit),
        )

        self.min_quote_volume = max(
            0.0,
            float(min_quote_volume),
        )

        self.candle_limit = max(
            self.MIN_CANDLES_REQUIRED,
            int(candle_limit),
        )

        self.interval = str(
            interval
        ).strip().lower()

        self.zone_tolerance = max(
            0.001,
            float(zone_tolerance),
        )

    # =====================================================
    # NORMALIZATION
    # =====================================================

    @staticmethod
    def _symbol(
        item: dict[str, Any],
    ) -> str:

        return str(
            item.get(
                "symbol",
                "",
            )
        ).upper().strip()

    @staticmethod
    def _float(
        value: Any,
        default: float = 0.0,
    ) -> float:

        try:
            return float(
                value
            )

        except (
            TypeError,
            ValueError,
        ):
            return default

    @staticmethod
    def _direction(
        value: Any,
    ) -> str:

        direction = str(
            value
            or "NEUTRAL"
        ).upper().strip()

        if direction not in {
            "LONG",
            "SHORT",
            "NEUTRAL",
        }:
            return "NEUTRAL"

        return direction

    # =====================================================
    # MARKET FILTER
    # =====================================================

    def is_valid_market(
        self,
        item: dict[str, Any],
    ) -> bool:

        symbol = self._symbol(
            item
        )

        if not symbol:
            return False

        if not symbol.endswith(
            self.QUOTE_ASSET
        ):
            return False

        status = str(
            item.get(
                "status",
                "TRADING",
            )
        ).upper().strip()

        if status not in {
            "",
            "TRADING",
        }:
            return False

        quote_volume = self._float(
            item.get(
                "quoteVolume",
                item.get(
                    "quote_volume",
                    0,
                ),
            )
        )

        if (
            quote_volume
            < self.min_quote_volume
        ):
            return False

        return True

    # =====================================================
    # LIQUIDITY SCORE
    # =====================================================

    def liquidity_score(
        self,
        item: dict[str, Any],
    ) -> float:

        quote_volume = self._float(
            item.get(
                "quoteVolume",
                item.get(
                    "quote_volume",
                    0,
                ),
            )
        )

        if quote_volume <= 0:
            return 0.0

        # Logarithmic-style tiers.
        # This avoids gigantic-volume coins dominating
        # the entire ranking.

        if quote_volume >= 1_000_000_000:
            return 100.0

        if quote_volume >= 500_000_000:
            return 95.0

        if quote_volume >= 250_000_000:
            return 90.0

        if quote_volume >= 100_000_000:
            return 85.0

        if quote_volume >= 50_000_000:
            return 80.0

        if quote_volume >= 25_000_000:
            return 75.0

        if quote_volume >= 10_000_000:
            return 65.0

        if quote_volume >= 5_000_000:
            return 55.0

        return 40.0

    # =====================================================
    # OLD ACTIVITY SCORE
    #
    # Kept for backward compatibility.
    #
    # IMPORTANT:
    # This is no longer used as the primary setup
    # ranking mechanism.
    # =====================================================

    def activity_score(
        self,
        item: dict[str, Any],
    ) -> float:

        quote_volume = self._float(
            item.get(
                "quoteVolume",
                item.get(
                    "quote_volume",
                    0,
                ),
            )
        )

        price_change = abs(
            self._float(
                item.get(
                    "priceChangePercent",
                    item.get(
                        "price_change_percent",
                        0,
                    ),
                )
            )
        )

        trades = self._float(
            item.get(
                "count",
                item.get(
                    "trade_count",
                    0,
                ),
            )
        )

        volume_component = min(
            quote_volume / 1_000_000_000,
            100.0,
        )

        movement_component = min(
            price_change,
            20.0,
        )

        trade_component = min(
            trades / 100_000,
            20.0,
        )

        return (
            volume_component
            + movement_component
            + trade_component
        )

    # =====================================================
    # LIQUIDITY FILTER + BASE RANKING
    # =====================================================

    def rank_markets(
        self,
        ticker_data: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:

        candidates: list[
            dict[str, Any]
        ] = []

        for item in ticker_data:

            if not isinstance(
                item,
                dict,
            ):
                continue

            if not self.is_valid_market(
                item
            ):
                continue

            symbol = self._symbol(
                item
            )

            quote_volume = self._float(
                item.get(
                    "quoteVolume",
                    item.get(
                        "quote_volume",
                        0,
                    ),
                )
            )

            liquidity = (
                self.liquidity_score(
                    item
                )
            )

            candidates.append(
                {
                    **item,
                    "symbol": symbol,
                    "quote_volume": round(
                        quote_volume,
                        2,
                    ),
                    "liquidity_score": round(
                        liquidity,
                        2,
                    ),
                }
            )

        # IMPORTANT:
        #
        # We do NOT sort by priceChangePercent.
        #
        # The initial universe is selected primarily by
        # liquidity. Setup quality is calculated later
        # using actual candles.

        candidates.sort(
            key=lambda x:
                (
                    x.get(
                        "liquidity_score",
                        0.0,
                    ),
                    x.get(
                        "quote_volume",
                        0.0,
                    ),
                ),
            reverse=True,
        )

        return candidates

    # =====================================================
    # SAFE KLINE FETCH
    # =====================================================

    async def _fetch_klines(
        self,
        symbol: str,
        market: str,
    ) -> list[Any]:

        try:

            raw = await self.market_data.klines(
                symbol,
                self.interval,
                market=market,
                limit=self.candle_limit,
            )

        except Exception:

            return []

        if isinstance(
            raw,
            dict,
        ):

            raw = raw.get(
                "data",
                raw.get(
                    "result",
                    [],
                ),
            )

        if not isinstance(
            raw,
            list,
        ):

            return []

        return raw

    # =====================================================
    # CANDLE PARSER
    # =====================================================

    def _parse_candles(
        self,
        candles: list[Any],
    ) -> dict[str, list[float]]:

        opens: list[float] = []
        highs: list[float] = []
        lows: list[float] = []
        closes: list[float] = []
        volumes: list[float] = []

        for candle in candles:

            if not isinstance(
                candle,
                (list, tuple),
            ):
                continue

            if len(candle) < 6:
                continue

            try:

                opens.append(
                    float(candle[1])
                )

                highs.append(
                    float(candle[2])
                )

                lows.append(
                    float(candle[3])
                )

                closes.append(
                    float(candle[4])
                )

                volumes.append(
                    float(candle[5])
                )

            except (
                TypeError,
                ValueError,
                IndexError,
            ):

                continue

        return {
            "opens": opens,
            "highs": highs,
            "lows": lows,
            "closes": closes,
            "volumes": volumes,
        }

    # =====================================================
    # SAFE AVERAGE
    # =====================================================

    @staticmethod
    def _average(
        values: list[float],
    ) -> float:

        if not values:
            return 0.0

        return (
            sum(values)
            / len(values)
        )

    # =====================================================
    # SUPPORT ZONE
    # =====================================================

    def _support_zone(
        self,
        lows: list[float],
        closes: list[float],
    ) -> dict[str, Any]:

        if len(lows) < 20:
            return {
                "valid": False,
                "level": 0.0,
                "tests": 0,
            }

        lookback = min(
            self.ZONE_LOOKBACK,
            len(lows),
        )

        recent_lows = lows[
            -lookback:
        ]

        recent_closes = closes[
            -lookback:
        ]

        level = min(
            recent_lows
        )

        if level <= 0:
            return {
                "valid": False,
                "level": 0.0,
                "tests": 0,
            }

        tolerance = (
            level
            * self.zone_tolerance
        )

        tests = 0
        test_indices: list[int] = []

        for index, low in enumerate(
            recent_lows
        ):

            distance = abs(
                low - level
            )

            if distance <= tolerance:

                tests += 1
                test_indices.append(
                    index
                )

        current_price = (
            recent_closes[-1]
            if recent_closes
            else 0.0
        )

        distance_percent = (
            abs(
                current_price
                - level
            )
            / level
            * 100.0
            if level > 0
            else 999.0
        )

        return {
            "valid": tests >= 1,
            "level": round(
                level,
                8,
            ),
            "tests": tests,
            "test_indices": test_indices,
            "distance_percent": round(
                distance_percent,
                4,
            ),
            "tolerance_percent": (
                self.zone_tolerance
                * 100.0
            ),
        }

    # =====================================================
    # RESISTANCE ZONE
    # =====================================================

    def _resistance_zone(
        self,
        highs: list[float],
        closes: list[float],
    ) -> dict[str, Any]:

        if len(highs) < 20:
            return {
                "valid": False,
                "level": 0.0,
                "tests": 0,
            }

        lookback = min(
            self.ZONE_LOOKBACK,
            len(highs),
        )

        recent_highs = highs[
            -lookback:
        ]

        recent_closes = closes[
            -lookback:
        ]

        level = max(
            recent_highs
        )

        if level <= 0:
            return {
                "valid": False,
                "level": 0.0,
                "tests": 0,
            }

        tolerance = (
            level
            * self.zone_tolerance
        )

        tests = 0
        test_indices: list[int] = []

        for index, high in enumerate(
            recent_highs
        ):

            distance = abs(
                high - level
            )

            if distance <= tolerance:

                tests += 1
                test_indices.append(
                    index
                )

        current_price = (
            recent_closes[-1]
            if recent_closes
            else 0.0
        )

        distance_percent = (
            abs(
                current_price
                - level
            )
            / level
            * 100.0
            if level > 0
            else 999.0
        )

        return {
            "valid": tests >= 1,
            "level": round(
                level,
                8,
            ),
            "tests": tests,
            "test_indices": test_indices,
            "distance_percent": round(
                distance_percent,
                4,
            ),
            "tolerance_percent": (
                self.zone_tolerance
                * 100.0
            ),
        }

    # =====================================================
    # SUPPORT REJECTION
    # =====================================================

    def _support_rejection(
        self,
        opens: list[float],
        highs: list[float],
        lows: list[float],
        closes: list[float],
        support: float,
    ) -> dict[str, Any]:

        if not support:
            return {
                "rejection": False,
                "strength": 0.0,
            }

        start = max(
            0,
            len(closes)
            - self.REJECTION_LOOKBACK,
        )

        strongest = 0.0

        for index in range(
            start,
            len(closes),
        ):

            open_price = opens[index]
            high_price = highs[index]
            low_price = lows[index]
            close_price = closes[index]

            candle_range = (
                high_price
                - low_price
            )

            if candle_range <= 0:
                continue

            distance = abs(
                low_price
                - support
            )

            tolerance = (
                support
                * self.zone_tolerance
            )

            if distance > tolerance:
                continue

            lower_wick = (
                min(
                    open_price,
                    close_price,
                )
                - low_price
            )

            bullish_close = (
                close_price
                > open_price
            )

            wick_ratio = (
                lower_wick
                / candle_range
            )

            strength = (
                wick_ratio
                * 70.0
            )

            if bullish_close:
                strength += 30.0

            strongest = max(
                strongest,
                strength,
            )

        return {
            "rejection": (
                strongest >= 50.0
            ),
            "strength": round(
                min(
                    100.0,
                    strongest,
                ),
                2,
            ),
        }

    # =====================================================
    # RESISTANCE REJECTION
    # =====================================================

    def _resistance_rejection(
        self,
        opens: list[float],
        highs: list[float],
        lows: list[float],
        closes: list[float],
        resistance: float,
    ) -> dict[str, Any]:

        if not resistance:
            return {
                "rejection": False,
                "strength": 0.0,
            }

        start = max(
            0,
            len(closes)
            - self.REJECTION_LOOKBACK,
        )

        strongest = 0.0

        for index in range(
            start,
            len(closes),
        ):

            open_price = opens[index]
            high_price = highs[index]
            low_price = lows[index]
            close_price = closes[index]

            candle_range = (
                high_price
                - low_price
            )

            if candle_range <= 0:
                continue

            distance = abs(
                high_price
                - resistance
            )

            tolerance = (
                resistance
                * self.zone_tolerance
            )

            if distance > tolerance:
                continue

            upper_wick = (
                high_price
                - max(
                    open_price,
                    close_price,
                )
            )

            bearish_close = (
                close_price
                < open_price
            )

            wick_ratio = (
                upper_wick
                / candle_range
            )

            strength = (
                wick_ratio
                * 70.0
            )

            if bearish_close:
                strength += 30.0

            strongest = max(
                strongest,
                strength,
            )

        return {
            "rejection": (
                strongest >= 50.0
            ),
            "strength": round(
                min(
                    100.0,
                    strongest,
                ),
                2,
            ),
        }

    # =====================================================
    # MOMENTUM
    # =====================================================

    def _momentum(
        self,
        closes: list[float],
        lookback: int = 5,
    ) -> float:

        if len(closes) <= lookback:
            return 0.0

        previous = closes[
            -lookback - 1
        ]

        current = closes[-1]

        if previous <= 0:
            return 0.0

        return (
            (
                current
                - previous
            )
            / previous
        ) * 100.0

    # =====================================================
    # VOLUME CONFIRMATION
    # =====================================================

    def _volume_ratio(
        self,
        volumes: list[float],
        period: int = 20,
    ) -> float:

        if len(volumes) < 2:
            return 0.0

        previous = volumes[
            -period - 1:
            -1
        ]

        if not previous:
            return 0.0

        average = self._average(
            previous
        )

        if average <= 0:
            return 0.0

        return (
            volumes[-1]
            / average
        )

    # =====================================================
    # STRUCTURE BIAS
    # =====================================================

    def _recent_structure(
        self,
        highs: list[float],
        lows: list[float],
    ) -> str:

        if len(highs) < 10:
            return "NEUTRAL"

        recent_highs = highs[
            -10:
        ]

        recent_lows = lows[
            -10:
        ]

        midpoint = 5

        old_high = max(
            recent_highs[
                :midpoint
            ]
        )

        new_high = max(
            recent_highs[
                midpoint:
            ]
        )

        old_low = min(
            recent_lows[
                :midpoint
            ]
        )

        new_low = min(
            recent_lows[
                midpoint:
            ]
        )

        higher_high = (
            new_high
            > old_high
        )

        higher_low = (
            new_low
            > old_low
        )

        lower_high = (
            new_high
            < old_high
        )

        lower_low = (
            new_low
            < old_low
        )

        if (
            higher_high
            and higher_low
        ):
            return "LONG"

        if (
            lower_high
            and lower_low
        ):
            return "SHORT"

        return "NEUTRAL"

    # =====================================================
    # SETUP QUALITY
    # =====================================================

    def _setup_quality(
        self,
        *,
        support_tests: int,
        resistance_tests: int,
        support_rejection: bool,
        resistance_rejection: bool,
        volume_ratio: float,
        momentum: float,
        structure: str,
    ) -> dict[str, Any]:

        long_score = 0.0
        short_score = 0.0

        # -------------------------------------------------
        # Support evidence
        # -------------------------------------------------

        if support_tests >= 2:

            long_score += 25.0

        if support_tests >= 3:

            long_score += 10.0

        if support_rejection:

            long_score += 25.0

        # -------------------------------------------------
        # Resistance evidence
        # -------------------------------------------------

        if resistance_tests >= 2:

            short_score += 25.0

        if resistance_tests >= 3:

            short_score += 10.0

        if resistance_rejection:

            short_score += 25.0

        # -------------------------------------------------
        # Volume
        # -------------------------------------------------

        if volume_ratio >= 1.0:

            if momentum > 0:

                long_score += 10.0

            elif momentum < 0:

                short_score += 10.0

        if volume_ratio >= (
            self.MIN_VOLUME_RATIO
        ):

            if momentum > 0:

                long_score += 10.0

            elif momentum < 0:

                short_score += 10.0

        # -------------------------------------------------
        # Momentum
        # -------------------------------------------------

        if momentum >= (
            self.MIN_MOMENTUM_PERCENT
        ):

            long_score += 10.0

        elif momentum <= (
            -self.MIN_MOMENTUM_PERCENT
        ):

            short_score += 10.0

        # -------------------------------------------------
        # Structure
        # -------------------------------------------------

        if structure == "LONG":

            long_score += 20.0

        elif structure == "SHORT":

            short_score += 20.0

        # -------------------------------------------------
        # Direction
        # -------------------------------------------------

        if long_score > short_score:

            direction = "LONG"
            score = long_score

        elif short_score > long_score:

            direction = "SHORT"
            score = short_score

        else:

            direction = "NEUTRAL"
            score = max(
                long_score,
                short_score,
            )

        return {
            "direction": direction,
            "setup_score": round(
                min(
                    100.0,
                    score,
                ),
                2,
            ),
            "long_score": round(
                min(
                    100.0,
                    long_score,
                ),
                2,
            ),
            "short_score": round(
                min(
                    100.0,
                    short_score,
                ),
                2,
            ),
        }

    # =====================================================
    # ANALYZE ONE MARKET
    # =====================================================

    async def analyze_market(
        self,
        item: dict[str, Any],
        *,
        market: str = "futures",
    ) -> dict[str, Any]:

        symbol = self._symbol(
            item
        )

        if not symbol:

            return {
                "success": False,
                "symbol": "",
                "setup_type": "NO_SETUP",
            }

        candles = await self._fetch_klines(
            symbol,
            market,
        )

        parsed = self._parse_candles(
            candles
        )

        opens = parsed["opens"]
        highs = parsed["highs"]
        lows = parsed["lows"]
        closes = parsed["closes"]
        volumes = parsed["volumes"]

        if len(closes) < (
            self.MIN_CANDLES_REQUIRED
        ):

            return {
                "success": False,
                "symbol": symbol,
                "setup_type": "INSUFFICIENT_DATA",
                "candle_count": len(
                    closes
                ),
            }

        current_price = closes[-1]

        support = self._support_zone(
            lows,
            closes,
        )

        resistance = (
            self._resistance_zone(
                highs,
                closes,
            )
        )

        support_rejection = (
            self._support_rejection(
                opens,
                highs,
                lows,
                closes,
                support.get(
                    "level",
                    0,
                ),
            )
        )

        resistance_rejection = (
            self._resistance_rejection(
                opens,
                highs,
                lows,
                closes,
                resistance.get(
                    "level",
                    0,
                ),
            )
        )

        momentum = self._momentum(
            closes
        )

        volume_ratio = (
            self._volume_ratio(
                volumes
            )
        )

        structure = (
            self._recent_structure(
                highs,
                lows,
            )
        )

        quality = self._setup_quality(
            support_tests=int(
                support.get(
                    "tests",
                    0,
                )
            ),
            resistance_tests=int(
                resistance.get(
                    "tests",
                    0,
                )
            ),
            support_rejection=bool(
                support_rejection.get(
                    "rejection",
                    False,
                )
            ),
            resistance_rejection=bool(
                resistance_rejection.get(
                    "rejection",
                    False,
                )
            ),
            volume_ratio=volume_ratio,
            momentum=momentum,
            structure=structure,
        )

        direction = quality[
            "direction"
        ]

        support_tests = int(
            support.get(
                "tests",
                0,
            )
        )

        resistance_tests = int(
            resistance.get(
                "tests",
                0,
            )
        )

        support_valid = (
            support_tests
            >= self.MIN_SUPPORT_TESTS
        )

        resistance_valid = (
            resistance_tests
            >= self.MIN_RESISTANCE_TESTS
        )

        support_rejected = bool(
            support_rejection.get(
                "rejection",
                False,
            )
        )

        resistance_rejected = bool(
            resistance_rejection.get(
                "rejection",
                False,
            )
        )

        # -------------------------------------------------
        # LONG setup
        #
        # Price has repeatedly interacted with support,
        # support is holding, and price is showing signs
        # of moving away from support.
        # -------------------------------------------------

        long_setup = (
            support_valid
            and support_rejected
            and direction == "LONG"
        )

        # -------------------------------------------------
        # SHORT setup
        #
        # Price has repeatedly interacted with resistance,
        # resistance is holding, and price is showing signs
        # of rejection.
        # -------------------------------------------------

        short_setup = (
            resistance_valid
            and resistance_rejected
            and direction == "SHORT"
        )

        if long_setup:

            setup_type = "LONG_SETUP"

        elif short_setup:

            setup_type = "SHORT_SETUP"

        elif (
            support_valid
            or resistance_valid
        ):

            setup_type = "WATCH"

        else:

            setup_type = "NO_SETUP"

        # -------------------------------------------------
        # Setup confidence is NOT final trading confidence.
        #
        # This is only discovery quality.
        # ConfidenceEngine will later perform the
        # final weighted validation.
        # -------------------------------------------------

        return {
            "success": True,
            "symbol": symbol,
            "market": market,
            "interval": self.interval,
            "candle_count": len(
                closes
            ),
            "current_price": current_price,
            "setup_type": setup_type,
            "direction": direction,
            "setup_score": quality[
                "setup_score"
            ],
            "long_score": quality[
                "long_score"
            ],
            "short_score": quality[
                "short_score"
            ],
            "support": {
                **support,
                "rejection": (
                    support_rejection
                ),
            },
            "resistance": {
                **resistance,
                "rejection": (
                    resistance_rejection
                ),
            },
            "momentum_percent": round(
                momentum,
                6,
            ),
            "volume_ratio": round(
                volume_ratio,
                4,
            ),
            "structure": structure,
            "repeated_support_tests": (
                support_tests
            ),
            "repeated_resistance_tests": (
                resistance_tests
            ),
            "support_confirmed": (
                support_valid
                and support_rejected
            ),
            "resistance_confirmed": (
                resistance_valid
                and resistance_rejected
            ),
        }

    # =====================================================
    # FULL MARKET SCAN
    # =====================================================

    async def scan_market(
        self,
        market: str = "futures",
    ) -> dict[str, Any]:

        raw_data = (
            await self.market_data.ticker_24h(
                market=market
            )
        )

        if isinstance(
            raw_data,
            dict,
        ):

            ticker_data = raw_data.get(
                "data",
                raw_data.get(
                    "result",
                    [],
                ),
            )

        else:

            ticker_data = raw_data

        if not isinstance(
            ticker_data,
            list,
        ):

            ticker_data = []

        ranked = self.rank_markets(
            ticker_data
        )

        # -------------------------------------------------
        # IMPORTANT
        #
        # Do not inspect every coin's candles.
        # First select the liquid universe.
        #
        # This is NOT Top Gainers / Top Losers.
        # It is liquidity-first candidate discovery.
        # -------------------------------------------------

        discovery_pool = ranked[
            : self.discovery_limit
        ]

        analyzed: list[
            dict[str, Any]
        ] = []

        for item in discovery_pool:

            result = (
                await self.analyze_market(
                    item,
                    market=market,
                )
            )

            if result.get(
                "success",
                False,
            ):

                merged = {
                    **item,
                    **result,
                }

                analyzed.append(
                    merged
                )

        # -------------------------------------------------
        # Only real setup candidates should be prioritized.
        # -------------------------------------------------

        setup_candidates = [
            item
            for item in analyzed
            if item.get(
                "setup_type"
            )
            in {
                "LONG_SETUP",
                "SHORT_SETUP",
            }
        ]

        watch_candidates = [
            item
            for item in analyzed
            if item.get(
                "setup_type"
            )
            == "WATCH"
        ]

        # Setup score first.
        # Liquidity second.
        #
        # 24h price change is intentionally NOT used
        # as the setup ranking signal.
        setup_candidates.sort(
            key=lambda x:
                (
                    x.get(
                        "setup_score",
                        0.0,
                    ),
                    x.get(
                        "liquidity_score",
                        0.0,
                    ),
                ),
            reverse=True,
        )

        watch_candidates.sort(
            key=lambda x:
                (
                    x.get(
                        "setup_score",
                        0.0,
                    ),
                    x.get(
                        "liquidity_score",
                        0.0,
                    ),
                ),
            reverse=True,
        )

        return {
            "success": True,
            "market": market,
            "universe_mode": (
                "SETUP_DISCOVERY"
            ),
            "scanner_version": "3.0.0",
            "total_markets": len(
                ticker_data
            ),
            "eligible_markets": len(
                ranked
            ),
            "discovery_pool_size": len(
                discovery_pool
            ),
            "analyzed_markets": len(
                analyzed
            ),
            "setup_candidates_count": len(
                setup_candidates
            ),
            "watch_candidates_count": len(
                watch_candidates
            ),
            "markets": ranked,
            "analyzed": analyzed,
            "setup_candidates": (
                setup_candidates
            ),
            "watch_candidates": (
                watch_candidates
            ),
        }

    # =====================================================
    # TOP CANDIDATES
    # =====================================================

    async def top_candidates(
        self,
        market: str = "futures",
        limit: int = 20,
    ) -> dict[str, Any]:
        """Return a liquidity-first universe for the Core-7 engine.

        No support/rejection/setup score is used here. Those older discovery
        gates were causing good signals to be discarded before the real
        Core-7 analysis could score them.
        """
        limit = max(1, int(limit))
        raw_data = await self.market_data.ticker_24h(market=market)
        if isinstance(raw_data, dict):
            ticker_data = raw_data.get("data", raw_data.get("result", []))
        else:
            ticker_data = raw_data
        if not isinstance(ticker_data, list):
            ticker_data = []

        ranked = self.rank_markets(ticker_data)
        selected = ranked[:limit]
        return {
            "success": True,
            "market": market,
            "universe_mode": "LIQUIDITY_FIRST_CORE_7",
            "scanner_version": "core-7",
            "total_markets": len(ticker_data),
            "eligible_markets": len(ranked),
            "candidates": selected,
            "candidate_mode": "LIQUIDITY_FIRST",
        }


