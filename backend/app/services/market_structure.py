from __future__ import annotations

from typing import Any


class MarketStructureEngine:
    """
    RR Trader Market Structure + Support/Resistance Engine.

    This engine is deterministic.

    It detects:
    - Higher High
    - Higher Low
    - Lower High
    - Lower Low
    - Bullish / Bearish / Neutral structure
    - Break of Structure
    - Support
    - Resistance
    - Repeated support tests
    - Repeated resistance tests
    - Support rejection
    - Resistance rejection
    - Higher-low confirmation
    - Lower-high confirmation
    - Consolidation near support/resistance
    - Breakout / retest context

    IMPORTANT:
    This engine does NOT force LONG or SHORT.

    It produces structural evidence for downstream engines.
    """

    # =====================================================
    # CONFIGURATION
    # =====================================================

    DEFAULT_SWING_WINDOW = 2

    # Number of recent candles used for S/R discovery.
    SR_LOOKBACK = 100

    # Number of candles used when looking for recent tests.
    RECENT_TEST_LOOKBACK = 50

    # Minimum number of touches required before a zone
    # becomes a meaningful repeated level.
    MIN_REPEATED_TESTS = 2

    # Three or more tests are considered strong.
    STRONG_TESTS = 3

    # Price-distance tolerance used to group nearby
    # swing points into the same support/resistance zone.
    DEFAULT_ZONE_TOLERANCE_PCT = 0.35

    # Current price proximity to a level.
    ACTIVE_ZONE_DISTANCE_PCT = 0.60

    # Rejection candle requirements.
    MIN_REJECTION_WICK_RATIO = 0.35
    MIN_REJECTION_BODY_RATIO = 0.20

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

        except (
            TypeError,
            ValueError,
        ):
            return default

    @staticmethod
    def _bool(
        value: Any,
    ) -> bool:

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

            safe_opens = (
                safe_closes.copy()
            )

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

        if (
            not highs
            or not lows
        ):

            return {
                "swing_highs": [],
                "swing_lows": [],
            }

        window = max(
            1,
            int(window),
        )

        length = min(
            len(highs),
            len(lows),
        )

        if length < (
            window * 2 + 1
        ):

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

            current_high = (
                cls._float(
                    highs[index]
                )
            )

            current_low = (
                cls._float(
                    lows[index]
                )
            )

            left_highs = highs[
                index - window:
                index
            ]

            right_highs = highs[
                index + 1:
                index + window + 1
            ]

            left_lows = lows[
                index - window:
                index
            ]

            right_lows = lows[
                index + 1:
                index + window + 1
            ]

            if (
                current_high
                >= max(
                    [
                        cls._float(value)
                        for value
                        in (
                            left_highs
                            + right_highs
                        )
                    ]
                )
            ):

                swing_highs.append(
                    current_high
                )

            if (
                current_low
                <= min(
                    [
                        cls._float(value)
                        for value
                        in (
                            left_lows
                            + right_lows
                        )
                    ]
                )
            ):

                swing_lows.append(
                    current_low
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

        previous_high = (
            cls._float(
                swing_highs[-2]
            )
        )

        current_high = (
            cls._float(
                swing_highs[-1]
            )
        )

        previous_low = (
            cls._float(
                swing_lows[-2]
            )
        )

        current_low = (
            cls._float(
                swing_lows[-1]
            )
        )

        higher_high = (
            current_high
            > previous_high
        )

        higher_low = (
            current_low
            > previous_low
        )

        lower_high = (
            current_high
            < previous_high
        )

        lower_low = (
            current_low
            < previous_low
        )

        if (
            higher_high
            and higher_low
        ):

            direction = "LONG"
            structure = "BULLISH"

        elif (
            lower_high
            and lower_low
        ):

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
            cls._float(
                swing_highs[-1]
            )
            if swing_highs
            else 0.0
        )

        latest_low = (
            cls._float(
                swing_lows[-1]
            )
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

            last_cluster = (
                clusters[-1]
            )

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

                cluster_levels.append(
                    level
                )

            else:

                clusters.append(
                    {
                        "levels": [level],
                    }
                )

        output = []

        for cluster in clusters:

            values = cluster[
                "levels"
            ]

            average = (
                sum(values)
                / len(values)
            )

            output.append(
                {
                    "level": round(
                        average,
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

        recent_highs = highs[
            -lookback:
        ]

        recent_lows = lows[
            -lookback:
        ]

        swings = cls.swing_points(
            recent_highs,
            recent_lows,
            window=swing_window,
        )

        swing_highs = swings[
            "swing_highs"
        ]

        swing_lows = swings[
            "swing_lows"
        ]

        # Use swing points as the main levels.
        # Fallback to recent extremes when insufficient
        # swing points exist.
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

        # Add recent extremes as contextual levels.
        if recent_lows:

            recent_support = min(
                [
                    cls._float(value)
                    for value
                    in recent_lows
                ]
            )

            if recent_support < current_price:

                support_levels.append(
                    recent_support
                )

        if recent_highs:

            recent_resistance = max(
                [
                    cls._float(value)
                    for value
                    in recent_highs
                ]
            )

            if recent_resistance > current_price:

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

        # Keep only levels that are actually on the
        # correct side of current price.
        support_zones = []

        for zone in support_clusters:

            level = zone["level"]

            if level < current_price:

                distance = (
                    cls._percentage_distance(
                        current_price,
                        level,
                    )
                )

                zone = {
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
                    zone
                )

        resistance_zones = []

        for zone in resistance_clusters:

            level = zone["level"]

            if level > current_price:

                distance = (
                    cls._percentage_distance(
                        current_price,
                        level,
                    )
                )

                zone = {
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
                    zone
                )

        # Nearest support.
        support_zones.sort(
            key=lambda item:
                item["distance_pct"]
        )

        # Nearest resistance.
        resistance_zones.sort(
            key=lambda item:
                item["distance_pct"]
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
    # REPEATED TEST DETECTION
    # =====================================================

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
    ) -> dict[str, Any]:

        if level <= 0:

            return {
                "tests": 0,
                "recent_tests": 0,
                "last_test_index": None,
            }

        zone_type = (
            str(zone_type)
            .upper()
            .strip()
        )

        highs = [
            cls._float(value)
            for value in highs
        ]

        lows = [
            cls._float(value)
            for value in lows
        ]

        length = min(
            len(highs),
            len(lows),
        )

        if length <= 0:

            return {
                "tests": 0,
                "recent_tests": 0,
                "last_test_index": None,
            }

        start = max(
            0,
            length - max(
                1,
                int(lookback),
            ),
        )

        tests = 0
        recent_tests = 0
        last_test_index = None

        for index in range(
            start,
            length,
        ):

            high = highs[index]
            low = lows[index]

            if zone_type == "SUPPORT":

                distance = (
                    cls._percentage_distance(
                        low,
                        level,
                    )
                )

            elif zone_type == "RESISTANCE":

                distance = (
                    cls._percentage_distance(
                        high,
                        level,
                    )
                )

            else:

                continue

            if distance <= tolerance_pct:

                tests += 1
                recent_tests += 1
                last_test_index = index

        return {
            "tests": tests,
            "recent_tests": recent_tests,
            "last_test_index": last_test_index,
            "repeated": (
                tests
                >= cls.MIN_REPEATED_TESTS
            ),
            "strong": (
                tests
                >= cls.STRONG_TESTS
            ),
        }

    # =====================================================
    # SUPPORT / RESISTANCE REJECTION
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

        if zone_type == "SUPPORT":

            distance = (
                cls._percentage_distance(
                    low_price,
                    level,
                )
            )

            bullish_close = (
                close_price
                > open_price
            )

            wick_ratio = (
                lower_wick
                / candle_range
            )

            rejection = (
                distance <= tolerance_pct
                and bullish_close
                and wick_ratio
                >= cls.MIN_REJECTION_WICK_RATIO
                and body_ratio
                >= cls.MIN_REJECTION_BODY_RATIO
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
                "type": (
                    "BULLISH_SUPPORT_REJECTION"
                    if rejection
                    else "NONE"
                ),
            }

        if zone_type == "RESISTANCE":

            distance = (
                cls._percentage_distance(
                    high_price,
                    level,
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

            rejection = (
                distance <= tolerance_pct
                and bearish_close
                and wick_ratio
                >= cls.MIN_REJECTION_WICK_RATIO
                and body_ratio
                >= cls.MIN_REJECTION_BODY_RATIO
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
            "type": "NONE",
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

        recent_highs = highs[
            -20:
        ]

        recent_lows = lows[
            -20:
        ]

        support = min(
            [
                cls._float(value)
                for value
                in recent_lows
            ]
        )

        resistance = max(
            [
                cls._float(value)
                for value
                in recent_highs
            ]
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

        if position_percent <= 35:

            location = "NEAR_SUPPORT"

        elif position_percent >= 85:

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
                max(
                    0.0,
                    min(
                        100.0,
                        position_percent,
                    ),
                ),
                4,
            ),
            "location": location,
            "support_tests": 0,
            "resistance_tests": 0,
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
            }

        current_price = cls._float(
            closes[-1]
        )

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
            "repeated": False,
            "strong": False,
        }

        support_rejection = {
            "rejection": False,
            "direction": "NEUTRAL",
            "type": "NONE",
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

        # -------------------------------------------------
        # Resistance test analysis
        # -------------------------------------------------

        resistance_tests = {
            "tests": 0,
            "recent_tests": 0,
            "last_test_index": None,
            "repeated": False,
            "strong": False,
        }

        resistance_rejection = {
            "rejection": False,
            "direction": "NEUTRAL",
            "type": "NONE",
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

        # -------------------------------------------------
        # Setup candidates
        #
        # These are NOT final signals.
        # They simply tell downstream engines that the
        # structure contains the type of setup we want.
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

        long_setup_candidate = (
            support_repeated
            and (
                support_rejected
                or higher_low
            )
        )

        short_setup_candidate = (
            resistance_repeated
            and (
                resistance_rejected
                or lower_high
            )
        )

        # -------------------------------------------------
        # Setup strength
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

        if lower_high:
            short_evidence += 1

        if bos.get(
            "direction"
        ) == "SHORT":

            short_evidence += 1

        # -------------------------------------------------
        # Final structural bias
        # -------------------------------------------------

        if (
            long_evidence
            > short_evidence
        ):

            structural_bias = "LONG"

        elif (
            short_evidence
            > long_evidence
        ):

            structural_bias = "SHORT"

        else:

            structural_bias = (
                structure.get(
                    "direction",
                    "NEUTRAL",
                )
            )

        # -------------------------------------------------
        # Enhanced S/R result
        # -------------------------------------------------

        enhanced_sr = {
            **basic_sr,
            "active_support": (
                active_support
            ),
            "active_resistance": (
                active_resistance
            ),
            "support_tests": (
                support_tests.get(
                    "tests",
                    0,
                )
            ),
            "resistance_tests": (
                resistance_tests.get(
                    "tests",
                    0,
                )
            ),
            "support_repeated": (
                support_repeated
            ),
            "resistance_repeated": (
                resistance_repeated
            ),
        }

        return {
            "success": True,

            # -------------------------------------------------
            # Existing compatibility fields
            # -------------------------------------------------

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

            # -------------------------------------------------
            # NEW REPEATED-ZONE DATA
            # -------------------------------------------------

            "support_zones": (
                zones[
                    "support_zones"
                ]
            ),

            "resistance_zones": (
                zones[
                    "resistance_zones"
                ]
            ),

            "active_support": (
                active_support
            ),

            "active_resistance": (
                active_resistance
            ),

            # -------------------------------------------------
            # NEW TEST DATA
            # -------------------------------------------------

            "support_test_analysis": (
                support_tests
            ),

            "resistance_test_analysis": (
                resistance_tests
            ),

            # -------------------------------------------------
            # NEW REJECTION DATA
            # -------------------------------------------------

            "support_rejection": (
                support_rejection
            ),

            "resistance_rejection": (
                resistance_rejection
            ),

            # -------------------------------------------------
            # NEW SETUP FLAGS
            # -------------------------------------------------

            "setup_candidates": {
                "long": (
                    long_setup_candidate
                ),
                "short": (
                    short_setup_candidate
                ),
            },

            "structural_bias": (
                structural_bias
            ),

            "long_evidence_score": (
                long_evidence
            ),

            "short_evidence_score": (
                short_evidence
            ),

            # -------------------------------------------------
            # Configuration metadata
            # -------------------------------------------------

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
