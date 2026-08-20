from __future__ import annotations

from typing import Any


class MarketStructureEngine:
    """
    RR Trader Market Structure + Support/Resistance Engine.

    This engine is deterministic and is designed to find the type of
    market location RR Trader actually wants:

    LONG:
        - price is near a meaningful support zone
        - support has been tested repeatedly
        - tests are separated into genuine retests
        - rejection / bullish response is present
        - higher-low structure can confirm the bounce

    SHORT:
        - price is near a meaningful resistance zone
        - resistance has been tested repeatedly
        - tests are separated into genuine retests
        - rejection / bearish response is present
        - lower-high structure can confirm the rejection

    It does NOT use 24h top-gainer/top-loser ranking to create setups.

    Compatibility:
        Existing public method names and important result fields are
        preserved so downstream engines can consume this result.
    """

    # =====================================================
    # CONFIGURATION
    # =====================================================

    DEFAULT_SWING_WINDOW = 2

    SR_LOOKBACK = 120
    RECENT_TEST_LOOKBACK = 60

    MIN_REPEATED_TESTS = 2
    STRONG_TESTS = 3

    DEFAULT_ZONE_TOLERANCE_PCT = 0.35
    ACTIVE_ZONE_DISTANCE_PCT = 0.60

    MIN_REJECTION_WICK_RATIO = 0.35
    MIN_REJECTION_BODY_RATIO = 0.20

    # A single candle is not allowed to create multiple "touches".
    # After a touch, price must move away from the zone by at least
    # this amount before another touch can be counted.
    MIN_TEST_SEPARATION_CANDLES = 3
    MIN_TEST_SEPARATION_PCT = 0.15

    # A test should not be ancient relative to the requested lookback.
    FRESH_TEST_LOOKBACK = 36

    # How close price should be before a zone is considered actionable.
    SETUP_ZONE_DISTANCE_PCT = 0.60

    # A bounce/rejection should have some movement away from the level.
    MIN_RESPONSE_MOVE_PCT = 0.20

    # Used for location classification.
    NEAR_SUPPORT_POSITION_PCT = 35.0
    NEAR_RESISTANCE_POSITION_PCT = 85.0

    # =====================================================
    # SAFE HELPERS
    # =====================================================

    @staticmethod
    def _float(
        value: Any,
        default: float = 0.0,
    ) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _bool(value: Any) -> bool:
        return bool(value)

    @classmethod
    def _percentage_distance(
        cls,
        price: float,
        level: float,
    ) -> float:
        if price <= 0 or level <= 0:
            return 999.0

        return abs(
            (price - level)
            / level
            * 100.0
        )

    @classmethod
    def _directional_distance(
        cls,
        price: float,
        level: float,
    ) -> float:
        if price <= 0 or level <= 0:
            return 999.0

        return (
            (price - level)
            / level
            * 100.0
        )

    @classmethod
    def _clamp(
        cls,
        value: float,
        low: float,
        high: float,
    ) -> float:
        return max(low, min(high, value))

    # =====================================================
    # CANDLE VALIDATION
    # =====================================================

    @classmethod
    def _safe_ohlc(
        cls,
        highs: list[float],
        lows: list[float],
        closes: list[float],
        opens: list[float] | None = None,
    ) -> tuple[
        list[float],
        list[float],
        list[float],
        list[float],
    ]:
        safe_highs = [
            cls._float(value)
            for value in highs
        ]

        safe_lows = [
            cls._float(value)
            for value in lows
        ]

        safe_closes = [
            cls._float(value)
            for value in closes
        ]

        if opens is None:
            safe_opens = safe_closes.copy()
        else:
            safe_opens = [
                cls._float(value)
                for value in opens
            ]

        length = min(
            len(safe_highs),
            len(safe_lows),
            len(safe_closes),
            len(safe_opens),
        )

        return (
            safe_highs[:length],
            safe_lows[:length],
            safe_closes[:length],
            safe_opens[:length],
        )

    # =====================================================
    # SWING POINTS
    # =====================================================

    @classmethod
    def swing_points(
        cls,
        highs: list[float],
        lows: list[float],
        window: int = DEFAULT_SWING_WINDOW,
    ) -> dict[str, list[float]]:
        if not highs or not lows:
            return {
                "swing_highs": [],
                "swing_lows": [],
            }

        window = max(1, int(window))

        length = min(
            len(highs),
            len(lows),
        )

        if length < window * 2 + 1:
            return {
                "swing_highs": [],
                "swing_lows": [],
            }

        swing_highs: list[float] = []
        swing_lows: list[float] = []

        for index in range(
            window,
            length - window,
        ):
            current_high = cls._float(
                highs[index]
            )
            current_low = cls._float(
                lows[index]
            )

            left_highs = highs[
                index - window:index
            ]
            right_highs = highs[
                index + 1:index + window + 1
            ]

            left_lows = lows[
                index - window:index
            ]
            right_lows = lows[
                index + 1:index + window + 1
            ]

            if (
                current_high > 0
                and current_high >= max(
                    cls._float(value)
                    for value in (
                        left_highs
                        + right_highs
                    )
                )
            ):
                swing_highs.append(
                    current_high
                )

            if (
                current_low > 0
                and current_low <= min(
                    cls._float(value)
                    for value in (
                        left_lows
                        + right_lows
                    )
                )
            ):
                swing_lows.append(
                    current_low
                )

        return {
            "swing_highs": swing_highs,
            "swing_lows": swing_lows,
        }

    @classmethod
    def swing_points_with_indices(
        cls,
        highs: list[float],
        lows: list[float],
        window: int = DEFAULT_SWING_WINDOW,
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Same swing detection as swing_points(), but preserves candle
        indices. This is useful for genuine retest counting.
        """
        if not highs or not lows:
            return {
                "swing_highs": [],
                "swing_lows": [],
            }

        window = max(1, int(window))

        length = min(
            len(highs),
            len(lows),
        )

        if length < window * 2 + 1:
            return {
                "swing_highs": [],
                "swing_lows": [],
            }

        swing_highs: list[dict[str, Any]] = []
        swing_lows: list[dict[str, Any]] = []

        for index in range(
            window,
            length - window,
        ):
            current_high = cls._float(
                highs[index]
            )
            current_low = cls._float(
                lows[index]
            )

            left_highs = highs[
                index - window:index
            ]
            right_highs = highs[
                index + 1:index + window + 1
            ]

            left_lows = lows[
                index - window:index
            ]
            right_lows = lows[
                index + 1:index + window + 1
            ]

            if (
                current_high > 0
                and current_high >= max(
                    cls._float(value)
                    for value in (
                        left_highs
                        + right_highs
                    )
                )
            ):
                swing_highs.append(
                    {
                        "index": index,
                        "price": current_high,
                    }
                )

            if (
                current_low > 0
                and current_low <= min(
                    cls._float(value)
                    for value in (
                        left_lows
                        + right_lows
                    )
                )
            ):
                swing_lows.append(
                    {
                        "index": index,
                        "price": current_low,
                    }
                )

        return {
            "swing_highs": swing_highs,
            "swing_lows": swing_lows,
        }

    # =====================================================
    # STRUCTURE CLASSIFICATION
    # =====================================================

    @classmethod
    def classify_structure(
        cls,
        swing_highs: list[float],
        swing_lows: list[float],
    ) -> dict[str, Any]:
        if (
            len(swing_highs) < 2
            or len(swing_lows) < 2
        ):
            return {
                "direction": "NEUTRAL",
                "structure": "INSUFFICIENT_DATA",
                "higher_high": False,
                "higher_low": False,
                "lower_high": False,
                "lower_low": False,
            }

        previous_high = cls._float(
            swing_highs[-2]
        )
        current_high = cls._float(
            swing_highs[-1]
        )

        previous_low = cls._float(
            swing_lows[-2]
        )
        current_low = cls._float(
            swing_lows[-1]
        )

        higher_high = current_high > previous_high
        higher_low = current_low > previous_low
        lower_high = current_high < previous_high
        lower_low = current_low < previous_low

        if higher_high and higher_low:
            direction = "LONG"
            structure = "BULLISH"
        elif lower_high and lower_low:
            direction = "SHORT"
            structure = "BEARISH"
        elif higher_high:
            direction = "LONG"
            structure = "BULLISH_HH"
        elif higher_low:
            direction = "LONG"
            structure = "BULLISH_HL"
        elif lower_high:
            direction = "SHORT"
            structure = "BEARISH_LH"
        elif lower_low:
            direction = "SHORT"
            structure = "BEARISH_LL"
        else:
            direction = "NEUTRAL"
            structure = "RANGE"

        return {
            "direction": direction,
            "structure": structure,
            "higher_high": higher_high,
            "higher_low": higher_low,
            "lower_high": lower_high,
            "lower_low": lower_low,
            "previous_swing_high": previous_high,
            "current_swing_high": current_high,
            "previous_swing_low": previous_low,
            "current_swing_low": current_low,
        }

    # =====================================================
    # BREAK OF STRUCTURE
    # =====================================================

    @classmethod
    def break_of_structure(
        cls,
        closes: list[float],
        swing_highs: list[float],
        swing_lows: list[float],
    ) -> dict[str, Any]:
        if not closes:
            return {
                "direction": "NONE",
                "break": False,
                "level": 0.0,
                "type": "NONE",
            }

        current_close = cls._float(
            closes[-1]
        )

        latest_high = (
            cls._float(swing_highs[-1])
            if swing_highs
            else 0.0
        )

        latest_low = (
            cls._float(swing_lows[-1])
            if swing_lows
            else 0.0
        )

        if (
            latest_high > 0
            and current_close > latest_high
        ):
            return {
                "direction": "LONG",
                "break": True,
                "level": latest_high,
                "type": "BOS_UP",
            }

        if (
            latest_low > 0
            and current_close < latest_low
        ):
            return {
                "direction": "SHORT",
                "break": True,
                "level": latest_low,
                "type": "BOS_DOWN",
            }

        return {
            "direction": "NONE",
            "break": False,
            "level": 0.0,
            "type": "NONE",
        }

    # =====================================================
    # ZONE CLUSTERING
    # =====================================================

    @classmethod
    def _cluster_levels(
        cls,
        levels: list[float],
        tolerance_pct: float,
    ) -> list[dict[str, Any]]:
        clean_levels = sorted(
            [
                cls._float(level)
                for level in levels
                if cls._float(level) > 0
            ]
        )

        if not clean_levels:
            return []

        tolerance_pct = max(
            0.01,
            float(tolerance_pct),
        )

        clusters: list[
            dict[str, Any]
        ] = []

        for level in clean_levels:
            if not clusters:
                clusters.append(
                    {
                        "levels": [level],
                    }
                )
                continue

            last_cluster = clusters[-1]
            cluster_levels = (
                last_cluster["levels"]
            )

            cluster_average = (
                sum(cluster_levels)
                / len(cluster_levels)
            )

            distance = (
                cls._percentage_distance(
                    level,
                    cluster_average,
                )
            )

            if distance <= tolerance_pct:
                cluster_levels.append(level)
            else:
                clusters.append(
                    {
                        "levels": [level],
                    }
                )

        output: list[dict[str, Any]] = []

        for cluster in clusters:
            values = cluster["levels"]

            output.append(
                {
                    "level": round(
                        sum(values)
                        / len(values),
                        8,
                    ),
                    "touches": len(values),
                    "min": round(
                        min(values),
                        8,
                    ),
                    "max": round(
                        max(values),
                        8,
                    ),
                }
            )

        return output

    # =====================================================
    # SUPPORT / RESISTANCE ZONES
    # =====================================================

    @classmethod
    def detect_zones(
        cls,
        highs: list[float],
        lows: list[float],
        current_price: float,
        *,
        swing_window: int = DEFAULT_SWING_WINDOW,
        lookback: int = SR_LOOKBACK,
        tolerance_pct: float = DEFAULT_ZONE_TOLERANCE_PCT,
    ) -> dict[str, Any]:
        if (
            not highs
            or not lows
            or current_price <= 0
        ):
            return {
                "support_zones": [],
                "resistance_zones": [],
                "active_support": None,
                "active_resistance": None,
            }

        lookback = max(
            20,
            int(lookback),
        )

        recent_highs = highs[-lookback:]
        recent_lows = lows[-lookback:]

        swings = cls.swing_points_with_indices(
            recent_highs,
            recent_lows,
            window=swing_window,
        )

        swing_high_records = swings[
            "swing_highs"
        ]
        swing_low_records = swings[
            "swing_lows"
        ]

        swing_highs = [
            item["price"]
            for item in swing_high_records
        ]

        swing_lows = [
            item["price"]
            for item in swing_low_records
        ]

        support_levels = [
            level
            for level in swing_lows
            if level < current_price
        ]

        resistance_levels = [
            level
            for level in swing_highs
            if level > current_price
        ]

        if recent_lows:
            recent_support = min(
                cls._float(value)
                for value in recent_lows
            )

            if (
                recent_support > 0
                and recent_support < current_price
            ):
                support_levels.append(
                    recent_support
                )

        if recent_highs:
            recent_resistance = max(
                cls._float(value)
                for value in recent_highs
            )

            if (
                recent_resistance > 0
                and recent_resistance > current_price
            ):
                resistance_levels.append(
                    recent_resistance
                )

        support_clusters = (
            cls._cluster_levels(
                support_levels,
                tolerance_pct,
            )
        )

        resistance_clusters = (
            cls._cluster_levels(
                resistance_levels,
                tolerance_pct,
            )
        )

        support_zones: list[
            dict[str, Any]
        ] = []

        for zone in support_clusters:
            level = zone["level"]

            if level < current_price:
                distance = (
                    cls._percentage_distance(
                        current_price,
                        level,
                    )
                )

                enriched = {
                    **zone,
                    "distance_pct": round(
                        distance,
                        4,
                    ),
                    "active": (
                        distance
                        <= cls.ACTIVE_ZONE_DISTANCE_PCT
                    ),
                    "strength": cls._zone_strength(
                        zone["touches"]
                    ),
                }

                support_zones.append(
                    enriched
                )

        resistance_zones: list[
            dict[str, Any]
        ] = []

        for zone in resistance_clusters:
            level = zone["level"]

            if level > current_price:
                distance = (
                    cls._percentage_distance(
                        current_price,
                        level,
                    )
                )

                enriched = {
                    **zone,
                    "distance_pct": round(
                        distance,
                        4,
                    ),
                    "active": (
                        distance
                        <= cls.ACTIVE_ZONE_DISTANCE_PCT
                    ),
                    "strength": cls._zone_strength(
                        zone["touches"]
                    ),
                }

                resistance_zones.append(
                    enriched
                )

        support_zones.sort(
            key=lambda item: item[
                "distance_pct"
            ]
        )

        resistance_zones.sort(
            key=lambda item: item[
                "distance_pct"
            ]
        )

        active_support = (
            support_zones[0]
            if support_zones
            else None
        )

        active_resistance = (
            resistance_zones[0]
            if resistance_zones
            else None
        )

        return {
            "support_zones": support_zones,
            "resistance_zones": resistance_zones,
            "active_support": active_support,
            "active_resistance": active_resistance,
        }

    # =====================================================
    # ZONE STRENGTH
    # =====================================================

    @staticmethod
    def _zone_strength(
        touches: int,
    ) -> str:
        if touches >= 3:
            return "STRONG"

        if touches >= 2:
            return "CONFIRMED"

        return "WEAK"

    # =====================================================
    # GENUINE TEST DETECTION
    # =====================================================

    @classmethod
    def _count_separated_tests(
        cls,
        highs: list[float],
        lows: list[float],
        level: float,
        *,
        zone_type: str,
        tolerance_pct: float,
        lookback: int,
        closes: list[float] | None = None,
    ) -> dict[str, Any]:
        """
        Count genuine zone tests.

        Important improvement:
        Consecutive candles touching the same zone are treated as one
        interaction until price has moved away sufficiently and time
        has passed. This prevents a noisy candle cluster from becoming
        a fake "3-touch support".
        """
        if level <= 0:
            return {
                "tests": 0,
                "recent_tests": 0,
                "last_test_index": None,
                "test_indices": [],
                "test_prices": [],
                "repeated": False,
                "strong": False,
            }

        zone_type = (
            str(zone_type)
            .upper()
            .strip()
        )

        length = min(
            len(highs),
            len(lows),
        )

        if length <= 0:
            return {
                "tests": 0,
                "recent_tests": 0,
                "last_test_index": None,
                "test_indices": [],
                "test_prices": [],
                "repeated": False,
                "strong": False,
            }

        start = max(
            0,
            length - max(1, int(lookback)),
        )

        tolerance_pct = max(
            0.01,
            float(tolerance_pct),
        )

        test_indices: list[int] = []
        test_prices: list[float] = []

        last_test_index: int | None = None
        last_test_price = 0.0

        # Price must first leave the zone before a new test counts.
        away_since_last_test = True

        for index in range(
            start,
            length,
        ):
            high = cls._float(
                highs[index]
            )
            low = cls._float(
                lows[index]
            )

            if zone_type == "SUPPORT":
                distance = (
                    cls._percentage_distance(
                        low,
                        level,
                    )
                )
                test_price = low

                # For support, price is considered "away" when the
                # candle closes sufficiently above the support.
                close = (
                    cls._float(
                        closes[index]
                    )
                    if closes is not None
                    and index < len(closes)
                    else 0.0
                )

                if (
                    close > 0
                    and cls._percentage_distance(
                        close,
                        level,
                    ) >= cls.MIN_TEST_SEPARATION_PCT
                    and close > level
                ):
                    away_since_last_test = True

            elif zone_type == "RESISTANCE":
                distance = (
                    cls._percentage_distance(
                        high,
                        level,
                    )
                )
                test_price = high

                close = (
                    cls._float(
                        closes[index]
                    )
                    if closes is not None
                    and index < len(closes)
                    else 0.0
                )

                if (
                    close > 0
                    and cls._percentage_distance(
                        close,
                        level,
                    ) >= cls.MIN_TEST_SEPARATION_PCT
                    and close < level
                ):
                    away_since_last_test = True
            else:
                continue

            if distance > tolerance_pct:
                continue

            if (
                last_test_index is not None
                and index - last_test_index
                < cls.MIN_TEST_SEPARATION_CANDLES
            ):
                continue

            if not away_since_last_test:
                continue

            test_indices.append(index)
            test_prices.append(
                round(test_price, 8)
            )

            last_test_index = index
            last_test_price = test_price
            away_since_last_test = False

        recent_cutoff = max(
            start,
            length - cls.FRESH_TEST_LOOKBACK,
        )

        recent_tests = sum(
            1
            for index in test_indices
            if index >= recent_cutoff
        )

        return {
            "tests": len(test_indices),
            "recent_tests": recent_tests,
            "last_test_index": last_test_index,
            "test_indices": test_indices,
            "test_prices": test_prices,
            "last_test_price": (
                round(last_test_price, 8)
                if last_test_price > 0
                else 0.0
            ),
            "repeated": (
                len(test_indices)
                >= cls.MIN_REPEATED_TESTS
            ),
            "strong": (
                len(test_indices)
                >= cls.STRONG_TESTS
            ),
        }

    @classmethod
    def count_zone_tests(
        cls,
        highs: list[float],
        lows: list[float],
        level: float,
        *,
        zone_type: str,
        tolerance_pct: float = DEFAULT_ZONE_TOLERANCE_PCT,
        lookback: int = RECENT_TEST_LOOKBACK,
        closes: list[float] | None = None,
    ) -> dict[str, Any]:
        return cls._count_separated_tests(
            highs=highs,
            lows=lows,
            level=level,
            zone_type=zone_type,
            tolerance_pct=tolerance_pct,
            lookback=lookback,
            closes=closes,
        )

    # =====================================================
    # REJECTION / RESPONSE
    # =====================================================

    @classmethod
    def rejection_analysis(
        cls,
        opens: list[float],
        highs: list[float],
        lows: list[float],
        closes: list[float],
        level: float,
        zone_type: str,
        tolerance_pct: float = DEFAULT_ZONE_TOLERANCE_PCT,
    ) -> dict[str, Any]:
        if (
            not opens
            or not highs
            or not lows
            or not closes
            or level <= 0
        ):
            return {
                "rejection": False,
                "direction": "NEUTRAL",
                "wick_ratio": 0.0,
                "body_ratio": 0.0,
                "distance_pct": 999.0,
                "type": "NONE",
                "response_move_pct": 0.0,
            }

        open_price = cls._float(
            opens[-1]
        )
        high_price = cls._float(
            highs[-1]
        )
        low_price = cls._float(
            lows[-1]
        )
        close_price = cls._float(
            closes[-1]
        )

        candle_range = (
            high_price
            - low_price
        )

        if candle_range <= 0:
            return {
                "rejection": False,
                "direction": "NEUTRAL",
                "wick_ratio": 0.0,
                "body_ratio": 0.0,
                "distance_pct": 999.0,
                "type": "NONE",
                "response_move_pct": 0.0,
            }

        body = abs(
            close_price
            - open_price
        )

        body_ratio = (
            body
            / candle_range
        )

        upper_wick = max(
            0.0,
            high_price
            - max(
                open_price,
                close_price,
            ),
        )

        lower_wick = max(
            0.0,
            min(
                open_price,
                close_price,
            )
            - low_price,
        )

        zone_type = (
            str(zone_type)
            .upper()
            .strip()
        )

        if zone_type == "SUPPORT":
            distance = cls._percentage_distance(
                low_price,
                level,
            )

            bullish_close = (
                close_price > open_price
            )

            wick_ratio = (
                lower_wick
                / candle_range
            )

            response_move_pct = (
                cls._percentage_distance(
                    close_price,
                    level,
                )
            )

            rejection = (
                distance <= tolerance_pct
                and bullish_close
                and wick_ratio
                >= cls.MIN_REJECTION_WICK_RATIO
                and body_ratio
                >= cls.MIN_REJECTION_BODY_RATIO
                and response_move_pct
                >= cls.MIN_RESPONSE_MOVE_PCT
            )

            return {
                "rejection": rejection,
                "direction": (
                    "LONG"
                    if rejection
                    else "NEUTRAL"
                ),
                "wick_ratio": round(
                    wick_ratio,
                    4,
                ),
                "body_ratio": round(
                    body_ratio,
                    4,
                ),
                "distance_pct": round(
                    distance,
                    4,
                ),
                "response_move_pct": round(
                    response_move_pct,
                    4,
                ),
                "type": (
                    "BULLISH_SUPPORT_REJECTION"
                    if rejection
                    else "NONE"
                ),
            }

        if zone_type == "RESISTANCE":
            distance = cls._percentage_distance(
                high_price,
                level,
            )

            bearish_close = (
                close_price < open_price
            )

            wick_ratio = (
                upper_wick
                / candle_range
            )

            response_move_pct = (
                cls._percentage_distance(
                    close_price,
                    level,
                )
            )

            rejection = (
                distance <= tolerance_pct
                and bearish_close
                and wick_ratio
                >= cls.MIN_REJECTION_WICK_RATIO
                and body_ratio
                >= cls.MIN_REJECTION_BODY_RATIO
                and response_move_pct
                >= cls.MIN_RESPONSE_MOVE_PCT
            )

            return {
                "rejection": rejection,
                "direction": (
                    "SHORT"
                    if rejection
                    else "NEUTRAL"
                ),
                "wick_ratio": round(
                    wick_ratio,
                    4,
                ),
                "body_ratio": round(
                    body_ratio,
                    4,
                ),
                "distance_pct": round(
                    distance,
                    4,
                ),
                "response_move_pct": round(
                    response_move_pct,
                    4,
                ),
                "type": (
                    "BEARISH_RESISTANCE_REJECTION"
                    if rejection
                    else "NONE"
                ),
            }

        return {
            "rejection": False,
            "direction": "NEUTRAL",
            "wick_ratio": 0.0,
            "body_ratio": 0.0,
            "distance_pct": 999.0,
            "response_move_pct": 0.0,
            "type": "NONE",
        }

    # =====================================================
    # MULTI-CANDLE RESPONSE
    # =====================================================

    @classmethod
    def zone_response(
        cls,
        closes: list[float],
        level: float,
        *,
        zone_type: str,
        lookahead_candles: int = 5,
    ) -> dict[str, Any]:
        """
        Measures whether price actually moved away from a tested
        zone after the latest interaction.

        This is structural evidence only, not a trade signal.
        """
        if (
            not closes
            or level <= 0
        ):
            return {
                "confirmed": False,
                "direction": "NEUTRAL",
                "move_pct": 0.0,
                "candles": 0,
            }

        zone_type = (
            str(zone_type)
            .upper()
            .strip()
        )

        current = cls._float(
            closes[-1]
        )

        if current <= 0:
            return {
                "confirmed": False,
                "direction": "NEUTRAL",
                "move_pct": 0.0,
                "candles": 0,
            }

        candles = max(
            1,
            int(lookahead_candles),
        )

        start_index = max(
            0,
            len(closes) - candles,
        )

        recent = [
            cls._float(value)
            for value in closes[start_index:]
            if cls._float(value) > 0
        ]

        if not recent:
            return {
                "confirmed": False,
                "direction": "NEUTRAL",
                "move_pct": 0.0,
                "candles": 0,
            }

        if zone_type == "SUPPORT":
            response_price = max(recent)
            move_pct = (
                (response_price - level)
                / level
                * 100.0
            )
            confirmed = (
                response_price > level
                and move_pct
                >= cls.MIN_RESPONSE_MOVE_PCT
            )
            direction = (
                "LONG"
                if confirmed
                else "NEUTRAL"
            )

        elif zone_type == "RESISTANCE":
            response_price = min(recent)
            move_pct = (
                (level - response_price)
                / level
                * 100.0
            )
            confirmed = (
                response_price < level
                and move_pct
                >= cls.MIN_RESPONSE_MOVE_PCT
            )
            direction = (
                "SHORT"
                if confirmed
                else "NEUTRAL"
            )
        else:
            return {
                "confirmed": False,
                "direction": "NEUTRAL",
                "move_pct": 0.0,
                "candles": len(recent),
            }

        return {
            "confirmed": confirmed,
            "direction": direction,
            "move_pct": round(
                max(0.0, move_pct),
                4,
            ),
            "candles": len(recent),
        }

    # =====================================================
    # SUPPORT / RESISTANCE LOCATION
    # =====================================================

    @classmethod
    def support_resistance(
        cls,
        highs: list[float],
        lows: list[float],
        current_price: float,
    ) -> dict[str, Any]:
        if (
            not highs
            or not lows
            or current_price <= 0
        ):
            return {
                "support": 0.0,
                "resistance": 0.0,
                "position_percent": 50.0,
                "location": "UNKNOWN",
                "support_tests": 0,
                "resistance_tests": 0,
            }

        recent_highs = highs[-20:]
        recent_lows = lows[-20:]

        support = min(
            cls._float(value)
            for value in recent_lows
        )

        resistance = max(
            cls._float(value)
            for value in recent_highs
        )

        if resistance <= support:
            return {
                "support": support,
                "resistance": resistance,
                "position_percent": 50.0,
                "location": "RANGE",
                "support_tests": 0,
                "resistance_tests": 0,
            }

        position_percent = (
            (
                current_price
                - support
            )
            / (
                resistance
                - support
            )
            * 100.0
        )

        if (
            position_percent
            <= cls.NEAR_SUPPORT_POSITION_PCT
        ):
            location = "NEAR_SUPPORT"
        elif (
            position_percent
            >= cls.NEAR_RESISTANCE_POSITION_PCT
        ):
            location = "NEAR_RESISTANCE"
        else:
            location = "MID_RANGE"

        return {
            "support": round(
                support,
                8,
            ),
            "resistance": round(
                resistance,
                8,
            ),
            "position_percent": round(
                cls._clamp(
                    position_percent,
                    0.0,
                    100.0,
                ),
                4,
            ),
            "location": location,
            "support_tests": 0,
            "resistance_tests": 0,
        }

    # =====================================================
    # SETUP QUALITY
    # =====================================================

    @classmethod
    def _setup_quality(
        cls,
        *,
        zone: dict[str, Any] | None,
        tests: dict[str, Any],
        rejection: dict[str, Any],
        structure: dict[str, Any],
        bos: dict[str, Any],
        response: dict[str, Any],
        direction: str,
    ) -> dict[str, Any]:
        """
        Produces structural quality only.

        It intentionally does not claim a final trading confidence.
        The confidence engine remains responsible for the final score.
        """
        direction = (
            str(direction)
            .upper()
            .strip()
        )

        score = 0.0
        reasons: list[str] = []

        if not zone:
            return {
                "score": 0.0,
                "grade": "NONE",
                "eligible": False,
                "reasons": [],
            }

        distance = cls._float(
            zone.get(
                "distance_pct",
                999.0,
            )
        )

        touches = int(
            tests.get(
                "tests",
                0,
            )
            or 0
        )

        recent_tests = int(
            tests.get(
                "recent_tests",
                0,
            )
            or 0
        )

        if (
            distance
            <= cls.SETUP_ZONE_DISTANCE_PCT
        ):
            score += 20
            reasons.append(
                "price_near_zone"
            )

        if touches >= 2:
            score += 20
            reasons.append(
                "repeated_zone_tests"
            )

        if touches >= 3:
            score += 10
            reasons.append(
                "strong_three_test_zone"
            )

        if recent_tests >= 2:
            score += 10
            reasons.append(
                "recent_retests"
            )

        if rejection.get(
            "rejection",
            False,
        ):
            score += 20
            reasons.append(
                "confirmed_rejection"
            )

        if response.get(
            "confirmed",
            False,
        ):
            score += 10
            reasons.append(
                "price_responded_from_zone"
            )

        if direction == "LONG":
            if structure.get(
                "higher_low",
                False,
            ):
                score += 5
                reasons.append(
                    "higher_low"
                )

            if bos.get(
                "direction"
            ) == "LONG":
                score += 5
                reasons.append(
                    "bullish_bos"
                )

        elif direction == "SHORT":
            if structure.get(
                "lower_high",
                False,
            ):
                score += 5
                reasons.append(
                    "lower_high"
                )

            if bos.get(
                "direction"
            ) == "SHORT":
                score += 5
                reasons.append(
                    "bearish_bos"
                )

        eligible = (
            distance
            <= cls.SETUP_ZONE_DISTANCE_PCT
            and touches
            >= cls.MIN_REPEATED_TESTS
        )

        if score >= 80:
            grade = "A"
        elif score >= 65:
            grade = "B"
        elif score >= 50:
            grade = "C"
        elif score > 0:
            grade = "D"
        else:
            grade = "NONE"

        return {
            "score": round(
                min(score, 100.0),
                2,
            ),
            "grade": grade,
            "eligible": eligible,
            "reasons": reasons,
        }

    # =====================================================
    # COMPLETE STRUCTURE ANALYSIS
    # =====================================================

    @classmethod
    def analyze(
        cls,
        highs: list[float],
        lows: list[float],
        closes: list[float],
        window: int = DEFAULT_SWING_WINDOW,
        opens: list[float] | None = None,
    ) -> dict[str, Any]:
        if not (
            highs
            and lows
            and closes
        ):
            return {
                "success": False,
                "direction": "NEUTRAL",
                "structure": "NO_DATA",
                "setup_candidates": {
                    "long": False,
                    "short": False,
                },
            }

        highs, lows, closes, opens = (
            cls._safe_ohlc(
                highs=highs,
                lows=lows,
                closes=closes,
                opens=opens,
            )
        )

        if not closes:
            return {
                "success": False,
                "direction": "NEUTRAL",
                "structure": "NO_DATA",
                "setup_candidates": {
                    "long": False,
                    "short": False,
                },
            }

        current_price = cls._float(
            closes[-1]
        )

        if current_price <= 0:
            return {
                "success": False,
                "direction": "NEUTRAL",
                "structure": "INVALID_PRICE",
                "setup_candidates": {
                    "long": False,
                    "short": False,
                },
            }

        # -------------------------------------------------
        # Swing analysis
        # -------------------------------------------------

        swings = cls.swing_points(
            highs=highs,
            lows=lows,
            window=window,
        )

        swing_highs = swings[
            "swing_highs"
        ]
        swing_lows = swings[
            "swing_lows"
        ]

        structure = (
            cls.classify_structure(
                swing_highs=swing_highs,
                swing_lows=swing_lows,
            )
        )

        # -------------------------------------------------
        # Break of structure
        # -------------------------------------------------

        bos = cls.break_of_structure(
            closes=closes,
            swing_highs=swing_highs,
            swing_lows=swing_lows,
        )

        # -------------------------------------------------
        # Traditional local S/R
        # -------------------------------------------------

        basic_sr = (
            cls.support_resistance(
                highs=highs,
                lows=lows,
                current_price=current_price,
            )
        )

        # -------------------------------------------------
        # Repeated S/R zones
        # -------------------------------------------------

        zones = cls.detect_zones(
            highs=highs,
            lows=lows,
            current_price=current_price,
            swing_window=window,
        )

        active_support = zones[
            "active_support"
        ]

        active_resistance = zones[
            "active_resistance"
        ]

        # -------------------------------------------------
        # Support test analysis
        # -------------------------------------------------

        support_tests = {
            "tests": 0,
            "recent_tests": 0,
            "last_test_index": None,
            "test_indices": [],
            "test_prices": [],
            "repeated": False,
            "strong": False,
        }

        support_rejection = {
            "rejection": False,
            "direction": "NEUTRAL",
            "type": "NONE",
            "response_move_pct": 0.0,
        }

        support_response = {
            "confirmed": False,
            "direction": "NEUTRAL",
            "move_pct": 0.0,
            "candles": 0,
        }

        if active_support:
            support_level = cls._float(
                active_support.get(
                    "level",
                    0,
                )
            )

            support_tests = (
                cls.count_zone_tests(
                    highs=highs,
                    lows=lows,
                    closes=closes,
                    level=support_level,
                    zone_type="SUPPORT",
                )
            )

            support_rejection = (
                cls.rejection_analysis(
                    opens=opens,
                    highs=highs,
                    lows=lows,
                    closes=closes,
                    level=support_level,
                    zone_type="SUPPORT",
                )
            )

            support_response = (
                cls.zone_response(
                    closes=closes,
                    level=support_level,
                    zone_type="SUPPORT",
                )
            )

        # -------------------------------------------------
        # Resistance test analysis
        # -------------------------------------------------

        resistance_tests = {
            "tests": 0,
            "recent_tests": 0,
            "last_test_index": None,
            "test_indices": [],
            "test_prices": [],
            "repeated": False,
            "strong": False,
        }

        resistance_rejection = {
            "rejection": False,
            "direction": "NEUTRAL",
            "type": "NONE",
            "response_move_pct": 0.0,
        }

        resistance_response = {
            "confirmed": False,
            "direction": "NEUTRAL",
            "move_pct": 0.0,
            "candles": 0,
        }

        if active_resistance:
            resistance_level = cls._float(
                active_resistance.get(
                    "level",
                    0,
                )
            )

            resistance_tests = (
                cls.count_zone_tests(
                    highs=highs,
                    lows=lows,
                    closes=closes,
                    level=resistance_level,
                    zone_type="RESISTANCE",
                )
            )

            resistance_rejection = (
                cls.rejection_analysis(
                    opens=opens,
                    highs=highs,
                    lows=lows,
                    closes=closes,
                    level=resistance_level,
                    zone_type="RESISTANCE",
                )
            )

            resistance_response = (
                cls.zone_response(
                    closes=closes,
                    level=resistance_level,
                    zone_type="RESISTANCE",
                )
            )

        # -------------------------------------------------
        # Structural setup candidates
        # -------------------------------------------------

        support_repeated = bool(
            support_tests.get(
                "repeated",
                False,
            )
        )

        resistance_repeated = bool(
            resistance_tests.get(
                "repeated",
                False,
            )
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

        higher_low = bool(
            structure.get(
                "higher_low",
                False,
            )
        )

        lower_high = bool(
            structure.get(
                "lower_high",
                False,
            )
        )

        # Primary setup rule:
        # Do not create a structural LONG merely because the coin is
        # moving up. It must be located at repeated support.
        long_setup_candidate = (
            active_support is not None
            and support_repeated
            and (
                support_rejected
                or higher_low
                or support_response.get(
                    "confirmed",
                    False,
                )
            )
        )

        # Primary SHORT rule:
        # Do not create a structural SHORT merely because the coin is
        # falling. It must be located at repeated resistance.
        short_setup_candidate = (
            active_resistance is not None
            and resistance_repeated
            and (
                resistance_rejected
                or lower_high
                or resistance_response.get(
                    "confirmed",
                    False,
                )
            )
        )

        # Explicitly reject mid-range structural setups.
        if (
            basic_sr.get("location")
            == "MID_RANGE"
        ):
            long_setup_candidate = False
            short_setup_candidate = False

        # -------------------------------------------------
        # Setup quality
        # -------------------------------------------------

        long_quality = cls._setup_quality(
            zone=active_support,
            tests=support_tests,
            rejection=support_rejection,
            structure=structure,
            bos=bos,
            response=support_response,
            direction="LONG",
        )

        short_quality = cls._setup_quality(
            zone=active_resistance,
            tests=resistance_tests,
            rejection=resistance_rejection,
            structure=structure,
            bos=bos,
            response=resistance_response,
            direction="SHORT",
        )

        # Keep the structural candidate flags stricter than the
        # quality score. Quality is evidence; candidate is eligibility.
        long_setup_candidate = bool(
            long_setup_candidate
            and long_quality.get(
                "eligible",
                False,
            )
        )

        short_setup_candidate = bool(
            short_setup_candidate
            and short_quality.get(
                "eligible",
                False,
            )
        )

        # -------------------------------------------------
        # Evidence scores
        # -------------------------------------------------

        long_evidence = 0

        if support_repeated:
            long_evidence += 1

        if support_tests.get(
            "strong",
            False,
        ):
            long_evidence += 1

        if support_rejected:
            long_evidence += 1

        if support_response.get(
            "confirmed",
            False,
        ):
            long_evidence += 1

        if higher_low:
            long_evidence += 1

        if bos.get(
            "direction"
        ) == "LONG":
            long_evidence += 1

        short_evidence = 0

        if resistance_repeated:
            short_evidence += 1

        if resistance_tests.get(
            "strong",
            False,
        ):
            short_evidence += 1

        if resistance_rejected:
            short_evidence += 1

        if resistance_response.get(
            "confirmed",
            False,
        ):
            short_evidence += 1

        if lower_high:
            short_evidence += 1

        if bos.get(
            "direction"
        ) == "SHORT":
            short_evidence += 1

        # -------------------------------------------------
        # Final structural bias
        # -------------------------------------------------

        if long_setup_candidate and not short_setup_candidate:
            structural_bias = "LONG"
        elif short_setup_candidate and not long_setup_candidate:
            structural_bias = "SHORT"
        elif long_evidence > short_evidence:
            structural_bias = "LONG"
        elif short_evidence > long_evidence:
            structural_bias = "SHORT"
        else:
            structural_bias = (
                structure.get(
                    "direction",
                    "NEUTRAL",
                )
            )

        # Never expose a directional setup from a pure mid-range
        # location.
        if (
            basic_sr.get("location")
            == "MID_RANGE"
        ):
            structural_bias = "NEUTRAL"

        # -------------------------------------------------
        # Enhanced S/R result
        # -------------------------------------------------

        enhanced_sr = {
            **basic_sr,
            "active_support": active_support,
            "active_resistance": active_resistance,
            "support_tests": support_tests.get(
                "tests",
                0,
            ),
            "resistance_tests": resistance_tests.get(
                "tests",
                0,
            ),
            "support_recent_tests": support_tests.get(
                "recent_tests",
                0,
            ),
            "resistance_recent_tests": resistance_tests.get(
                "recent_tests",
                0,
            ),
            "support_repeated": support_repeated,
            "resistance_repeated": resistance_repeated,
        }

        return {
            "success": True,

            # Existing compatibility fields
            "direction": structure[
                "direction"
            ],
            "structure": structure[
                "structure"
            ],
            "swing_points": swings,
            "structure_details": structure,
            "break_of_structure": bos,
            "support_resistance": enhanced_sr,

            # Repeated-zone data
            "support_zones": zones[
                "support_zones"
            ],
            "resistance_zones": zones[
                "resistance_zones"
            ],
            "active_support": active_support,
            "active_resistance": active_resistance,

            # Test data
            "support_test_analysis": support_tests,
            "resistance_test_analysis": resistance_tests,

            # Rejection data
            "support_rejection": support_rejection,
            "resistance_rejection": resistance_rejection,

            # Response data
            "support_response": support_response,
            "resistance_response": resistance_response,

            # Setup flags
            "setup_candidates": {
                "long": long_setup_candidate,
                "short": short_setup_candidate,
            },

            "structural_bias": structural_bias,

            # Numeric structural evidence
            "long_evidence_score": long_evidence,
            "short_evidence_score": short_evidence,

            # New setup-quality fields
            "setup_quality": {
                "long": long_quality,
                "short": short_quality,
            },

            # Explicit location gate
            "location_gate": {
                "location": basic_sr.get(
                    "location",
                    "UNKNOWN",
                ),
                "mid_range_blocked": (
                    basic_sr.get(
                        "location"
                    )
                    == "MID_RANGE"
                ),
                "long_requires_support": True,
                "short_requires_resistance": True,
            },

            # Configuration metadata
            "configuration": {
                "swing_window": window,
                "sr_lookback": cls.SR_LOOKBACK,
                "recent_test_lookback": (
                    cls.RECENT_TEST_LOOKBACK
                ),
                "min_repeated_tests": (
                    cls.MIN_REPEATED_TESTS
                ),
                "strong_tests": (
                    cls.STRONG_TESTS
                ),
                "zone_tolerance_pct": (
                    cls.DEFAULT_ZONE_TOLERANCE_PCT
                ),
                "active_zone_distance_pct": (
                    cls.ACTIVE_ZONE_DISTANCE_PCT
                ),
                "setup_zone_distance_pct": (
                    cls.SETUP_ZONE_DISTANCE_PCT
                ),
                "min_test_separation_candles": (
                    cls.MIN_TEST_SEPARATION_CANDLES
                ),
                "min_test_separation_pct": (
                    cls.MIN_TEST_SEPARATION_PCT
                ),
                "fresh_test_lookback": (
                    cls.FRESH_TEST_LOOKBACK
                ),
                "min_response_move_pct": (
                    cls.MIN_RESPONSE_MOVE_PCT
                ),
            },
        }


# =========================================================
# SHARED INSTANCE
# =========================================================

market_structure_engine = (
    MarketStructureEngine()
)


# =========================================================
# EXPORTS
# =========================================================

__all__ = [
    "MarketStructureEngine",
    "market_structure_engine",
]
