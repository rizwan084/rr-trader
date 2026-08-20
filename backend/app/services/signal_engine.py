from __future__ import annotations

import asyncio
from typing import Any

from app.services.indicators import indicator_engine
from app.services.market_data import market_data_service
from app.services.market_structure import market_structure_engine
from app.services.mtf_engine import mtf_engine


class SignalEngine:
    """
    RR Trader deterministic signal engine.

    IMPORTANT:
    This engine does NOT select coins because they are simply
    top gainers / top losers.

    The signal must come from an actual trade location:

    LONG:
        - repeated support interaction
        - price currently near support
        - bullish rejection / recovery
        - bullish market structure
        - positive momentum
        - useful volume
        - MTF confirmation

    SHORT:
        - repeated resistance interaction
        - price currently near resistance
        - bearish rejection / rejection from resistance
        - bearish market structure
        - negative momentum
        - useful volume
        - MTF confirmation

    A coin sitting in the middle of a range is intentionally
    rejected even if it is moving strongly.

    This layer only creates a preliminary deterministic signal.
    It does not execute trades.
    """

    CORE_TIMEFRAMES = (
        "15m",
        "1h",
        "4h",
    )

    MIN_SUPPORT_TOUCHES = 2
    MIN_RESISTANCE_TOUCHES = 2
    IDEAL_SUPPORT_TOUCHES = 3
    IDEAL_RESISTANCE_TOUCHES = 3

    SUPPORT_LOOKBACK = 80
    RESISTANCE_LOOKBACK = 80

    # Percentage of ATR used as a price-location tolerance.
    # The effective tolerance is also capped by a percentage
    # of price so extremely volatile coins do not create huge zones.
    LEVEL_ATR_TOLERANCE = 0.45
    LEVEL_PRICE_TOLERANCE = 0.012

    MIN_VOLUME_RATIO = 1.0
    STRONG_VOLUME_RATIO = 1.20

    # A setup must have a real location before momentum/volume
    # can turn it into a publishable candidate.
    MIN_SETUP_SCORE = 70.0
    PUBLISH_CONFIDENCE = 85.0

    # =====================================================
    # HELPERS
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
    def _direction(
        value: Any,
    ) -> str:
        value = str(value or "NEUTRAL").upper().strip()

        if value not in {"LONG", "SHORT", "NEUTRAL"}:
            return "NEUTRAL"

        return value

    @staticmethod
    def _dedupe(
        values: list[str],
    ) -> list[str]:
        return list(dict.fromkeys(values))

    @staticmethod
    def _safe_list(
        value: Any,
    ) -> list[Any]:
        return value if isinstance(value, list) else []

    # =====================================================
    # LEVEL DETECTION
    # =====================================================

    def _level_tolerance(
        self,
        price: float,
        atr: float,
    ) -> float:
        if price <= 0:
            return 0.0

        atr_component = (
            atr * self.LEVEL_ATR_TOLERANCE
            if atr > 0
            else 0.0
        )

        price_component = price * self.LEVEL_PRICE_TOLERANCE

        if atr_component <= 0:
            return price_component

        return min(
            max(atr_component, price_component * 0.35),
            price_component,
        )

    @staticmethod
    def _cluster_levels(
        levels: list[float],
        tolerance: float,
    ) -> list[dict[str, Any]]:
        """
        Cluster nearby swing prices into actual support/resistance
        zones.

        We intentionally use swing-derived prices instead of simply
        taking the highest/lowest candle. This makes the repeated
        interaction count meaningful.
        """
        clean = sorted(
            [
                float(level)
                for level in levels
                if isinstance(level, (int, float))
                and float(level) > 0
            ]
        )

        if not clean:
            return []

        tolerance = max(float(tolerance), 0.0)

        clusters: list[list[float]] = []

        for level in clean:
            if not clusters:
                clusters.append([level])
                continue

            current = clusters[-1]
            center = sum(current) / len(current)

            if abs(level - center) <= tolerance:
                current.append(level)
            else:
                clusters.append([level])

        result = []

        for cluster in clusters:
            center = sum(cluster) / len(cluster)
            result.append(
                {
                    "level": center,
                    "touches": len(cluster),
                    "min": min(cluster),
                    "max": max(cluster),
                }
            )

        return result

    def _support_resistance_setup(
        self,
        candles: list[Any],
        indicators: dict[str, Any],
        structure: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Detect the actual trade location.

        The key requirement is repeated interaction:
            support -> 2+ meaningful tests -> current price near support
        or
            resistance -> 2+ meaningful tests -> current price near resistance

        This is deliberately independent from 24h gain/loss ranking.
        """
        parsed = indicator_engine.parse_candles(candles)

        highs = self._safe_list(parsed.get("highs"))
        lows = self._safe_list(parsed.get("lows"))
        closes = self._safe_list(parsed.get("closes"))

        if len(highs) < 15 or len(lows) < 15 or len(closes) < 15:
            return {
                "available": False,
                "setup": "NONE",
                "support": {},
                "resistance": {},
                "reason": "Insufficient candles for level detection.",
            }

        current_price = self._float(closes[-1])
        atr = self._float(indicators.get("atr"))

        tolerance = self._level_tolerance(
            current_price,
            atr,
        )

        # Prefer swing levels from the deterministic market-structure
        # engine. Fall back to recent extrema if necessary.
        swing_points = structure.get(
            "swing_points",
            {},
        )

        swing_highs = self._safe_list(
            swing_points.get("swing_highs")
            if isinstance(swing_points, dict)
            else []
        )

        swing_lows = self._safe_list(
            swing_points.get("swing_lows")
            if isinstance(swing_points, dict)
            else []
        )

        # Only recent history is relevant to the current setup.
        recent_highs = highs[-self.RESISTANCE_LOOKBACK:]
        recent_lows = lows[-self.SUPPORT_LOOKBACK:]

        if not swing_highs:
            swing_highs = recent_highs

        if not swing_lows:
            swing_lows = recent_lows

        # Use the most recent portion of swing lists when available.
        swing_highs = swing_highs[-self.RESISTANCE_LOOKBACK:]
        swing_lows = swing_lows[-self.SUPPORT_LOOKBACK:]

        support_clusters = self._cluster_levels(
            swing_lows,
            tolerance,
        )

        resistance_clusters = self._cluster_levels(
            swing_highs,
            tolerance,
        )

        # Keep only levels that are relevant to current price.
        support_candidates = [
            item
            for item in support_clusters
            if item["level"] <= current_price + tolerance
        ]

        resistance_candidates = [
            item
            for item in resistance_clusters
            if item["level"] >= current_price - tolerance
        ]

        support = (
            max(
                support_candidates,
                key=lambda item: item["level"],
            )
            if support_candidates
            else None
        )

        resistance = (
            min(
                resistance_candidates,
                key=lambda item: item["level"],
            )
            if resistance_candidates
            else None
        )

        # Direct candle interaction count is more useful than merely
        # counting swing points. It checks how often price actually
        # came back to the zone.
        def count_low_tests(level: float) -> int:
            count = 0

            start = max(0, len(lows) - self.SUPPORT_LOOKBACK)

            for index in range(start, len(lows)):
                distance = abs(lows[index] - level)
                if distance <= tolerance:
                    count += 1

            return count

        def count_high_tests(level: float) -> int:
            count = 0

            start = max(0, len(highs) - self.RESISTANCE_LOOKBACK)

            for index in range(start, len(highs)):
                distance = abs(highs[index] - level)
                if distance <= tolerance:
                    count += 1

            return count

        if support:
            support["candle_tests"] = count_low_tests(
                support["level"]
            )
            support["touches"] = max(
                int(support["touches"]),
                int(support["candle_tests"]),
            )

        if resistance:
            resistance["candle_tests"] = count_high_tests(
                resistance["level"]
            )
            resistance["touches"] = max(
                int(resistance["touches"]),
                int(resistance["candle_tests"]),
            )

        support_distance = (
            abs(current_price - support["level"])
            if support
            else float("inf")
        )

        resistance_distance = (
            abs(current_price - resistance["level"])
            if resistance
            else float("inf")
        )

        near_support = (
            support is not None
            and support_distance <= tolerance
        )

        near_resistance = (
            resistance is not None
            and resistance_distance <= tolerance
        )

        # Price must be close to one side of the range. If both are
        # simultaneously near, it is too compressed to treat as a
        # clean support/resistance setup.
        if near_support and near_resistance:
            setup = "RANGE_COMPRESSION"
        elif near_support and support["touches"] >= self.MIN_SUPPORT_TOUCHES:
            setup = "SUPPORT"
        elif (
            near_resistance
            and resistance["touches"] >= self.MIN_RESISTANCE_TOUCHES
        ):
            setup = "RESISTANCE"
        else:
            setup = "NONE"

        # Use the original structure engine's location as an additional
        # sanity check, but do not let it replace repeated-touch logic.
        sr = structure.get(
            "support_resistance",
            {},
        )

        structure_location = (
            str(
                sr.get("location", "UNKNOWN")
            ).upper()
            if isinstance(sr, dict)
            else "UNKNOWN"
        )

        return {
            "available": True,
            "setup": setup,
            "current_price": current_price,
            "atr": atr,
            "tolerance": round(tolerance, 10),
            "support": (
                {
                    **support,
                    "distance": round(
                        support_distance,
                        10,
                    ),
                    "near": near_support,
                }
                if support
                else {}
            ),
            "resistance": (
                {
                    **resistance,
                    "distance": round(
                        resistance_distance,
                        10,
                    ),
                    "near": near_resistance,
                }
                if resistance
                else {}
            ),
            "structure_location": structure_location,
        }

    # =====================================================
    # REJECTION / RECOVERY
    # =====================================================

    def _location_confirmation(
        self,
        direction: str,
        indicators: dict[str, Any],
        setup: dict[str, Any],
    ) -> tuple[float, list[str]]:
        """
        Score the actual reaction from the level.

        LONG wants:
            support + lower wick + bullish close/recovery

        SHORT wants:
            resistance + upper wick + bearish close/rejection
        """
        reasons: list[str] = []

        if not setup.get("available"):
            return 0.0, reasons

        candle = indicators.get(
            "candle_structure",
            {},
        )

        if not isinstance(candle, dict):
            return 0.0, reasons

        candle_direction = self._direction(
            candle.get("direction")
        )

        body_ratio = self._float(
            candle.get("body_ratio")
        )

        upper_wick = self._float(
            candle.get("upper_wick")
        )

        lower_wick = self._float(
            candle.get("lower_wick")
        )

        candle_range = self._float(
            candle.get("range")
        )

        if direction == "LONG":
            if setup.get("setup") != "SUPPORT":
                return 0.0, reasons

            score = 25.0
            reasons.append(
                "Price is testing a repeatedly respected support zone."
            )

            if lower_wick > 0 and candle_range > 0:
                wick_ratio = lower_wick / candle_range

                if wick_ratio >= 0.30:
                    score += 20.0
                    reasons.append(
                        "Lower-wick rejection shows buyers defending support."
                    )
                elif wick_ratio >= 0.15:
                    score += 10.0
                    reasons.append(
                        "Some lower-wick rejection is visible at support."
                    )

            if candle_direction == "LONG":
                score += 20.0
                reasons.append(
                    "The latest candle closed bullish after the support test."
                )

            if body_ratio >= 0.45 and candle_direction == "LONG":
                score += 10.0
                reasons.append(
                    "The bullish candle has a meaningful body."
                )

            return min(score, 100.0), reasons

        if direction == "SHORT":
            if setup.get("setup") != "RESISTANCE":
                return 0.0, reasons

            score = 25.0
            reasons.append(
                "Price is testing a repeatedly respected resistance zone."
            )

            if upper_wick > 0 and candle_range > 0:
                wick_ratio = upper_wick / candle_range

                if wick_ratio >= 0.30:
                    score += 20.0
                    reasons.append(
                        "Upper-wick rejection shows sellers defending resistance."
                    )
                elif wick_ratio >= 0.15:
                    score += 10.0
                    reasons.append(
                        "Some upper-wick rejection is visible at resistance."
                    )

            if candle_direction == "SHORT":
                score += 20.0
                reasons.append(
                    "The latest candle closed bearish after the resistance test."
                )

            if body_ratio >= 0.45 and candle_direction == "SHORT":
                score += 10.0
                reasons.append(
                    "The bearish candle has a meaningful body."
                )

            return min(score, 100.0), reasons

        return 0.0, reasons

    # =====================================================
    # REPEATED LEVEL SCORE
    # =====================================================

    def _retest_score(
        self,
        direction: str,
        setup: dict[str, Any],
    ) -> tuple[float, list[str]]:
        reasons: list[str] = []

        if direction == "LONG":
            level = setup.get("support", {})

            if not isinstance(level, dict):
                return 0.0, reasons

            touches = int(
                self._float(
                    level.get("touches")
                )
            )

            if setup.get("setup") != "SUPPORT":
                return 0.0, reasons

            if touches < self.MIN_SUPPORT_TOUCHES:
                return 0.0, reasons

            if touches >= self.IDEAL_SUPPORT_TOUCHES:
                score = 100.0
                reasons.append(
                    f"Support has been tested {touches} times; buyers have repeatedly defended it."
                )
            else:
                score = 75.0
                reasons.append(
                    f"Support has been tested {touches} times."
                )

            return score, reasons

        if direction == "SHORT":
            level = setup.get("resistance", {})

            if not isinstance(level, dict):
                return 0.0, reasons

            touches = int(
                self._float(
                    level.get("touches")
                )
            )

            if setup.get("setup") != "RESISTANCE":
                return 0.0, reasons

            if touches < self.MIN_RESISTANCE_TOUCHES:
                return 0.0, reasons

            if touches >= self.IDEAL_RESISTANCE_TOUCHES:
                score = 100.0
                reasons.append(
                    f"Resistance has been tested {touches} times; sellers have repeatedly defended it."
                )
            else:
                score = 75.0
                reasons.append(
                    f"Resistance has been tested {touches} times."
                )

            return score, reasons

        return 0.0, reasons

    # =====================================================
    # TIMEFRAME ANALYSIS
    # =====================================================

    def analyze_timeframe(
        self,
        timeframe: str,
        candles: list[Any],
    ) -> dict[str, Any]:
        indicators = indicator_engine.calculate(
            candles
        )

        if not indicators.get("success", False):
            return {
                "success": False,
                "timeframe": timeframe,
                "direction": "NEUTRAL",
                "confidence": 0.0,
                "indicators": {},
                "structure": {},
                "setup": {},
                "reason": indicators.get(
                    "error",
                    "Indicator calculation failed.",
                ),
            }

        parsed = indicator_engine.parse_candles(
            candles
        )

        structure = market_structure_engine.analyze(
            highs=parsed["highs"],
            lows=parsed["lows"],
            closes=parsed["closes"],
        )

        direction_scores = {
            "LONG": 0.0,
            "SHORT": 0.0,
        }

        reasons: list[str] = []

        # -------------------------------------------------
        # PRICE / EMA TREND
        # -------------------------------------------------

        price = self._float(
            indicators.get("price")
        )
        ema20 = self._float(
            indicators.get("ema20")
        )
        ema50 = self._float(
            indicators.get("ema50")
        )

        if price > ema20 > ema50 and price > 0:
            direction_scores["LONG"] += 15.0
            reasons.append(
                "Price is above EMA20 and EMA50."
            )

        elif price < ema20 < ema50 and price > 0:
            direction_scores["SHORT"] += 15.0
            reasons.append(
                "Price is below EMA20 and EMA50."
            )

        # -------------------------------------------------
        # RSI
        # -------------------------------------------------

        rsi = self._float(
            indicators.get("rsi"),
            50.0,
        )

        if 50 < rsi < 70:
            direction_scores["LONG"] += 8.0
            reasons.append(
                "RSI supports bullish momentum without being in an extreme zone."
            )

        elif 30 < rsi < 50:
            direction_scores["SHORT"] += 8.0
            reasons.append(
                "RSI supports bearish momentum without being in an extreme zone."
            )

        # -------------------------------------------------
        # MOMENTUM
        # -------------------------------------------------

        momentum = self._float(
            indicators.get("momentum")
        )

        if momentum > 0:
            direction_scores["LONG"] += min(
                12.0,
                abs(momentum) * 3.0,
            )
            reasons.append(
                "Momentum is positive."
            )

        elif momentum < 0:
            direction_scores["SHORT"] += min(
                12.0,
                abs(momentum) * 3.0,
            )
            reasons.append(
                "Momentum is negative."
            )

        # -------------------------------------------------
        # VOLUME
        # -------------------------------------------------

        volume_ratio = self._float(
            indicators.get("volume_ratio")
        )

        candle_structure = indicators.get(
            "candle_structure",
            {},
        )

        candle_direction = self._direction(
            candle_structure.get("direction")
            if isinstance(candle_structure, dict)
            else "NEUTRAL"
        )

        if volume_ratio >= self.MIN_VOLUME_RATIO:
            if candle_direction == "LONG":
                direction_scores["LONG"] += 8.0

                if volume_ratio >= self.STRONG_VOLUME_RATIO:
                    direction_scores["LONG"] += 4.0

                reasons.append(
                    "Bullish candle is supported by useful volume."
                )

            elif candle_direction == "SHORT":
                direction_scores["SHORT"] += 8.0

                if volume_ratio >= self.STRONG_VOLUME_RATIO:
                    direction_scores["SHORT"] += 4.0

                reasons.append(
                    "Bearish candle is supported by useful volume."
                )

        # -------------------------------------------------
        # MARKET STRUCTURE
        # -------------------------------------------------

        structure_direction = self._direction(
            structure.get("direction")
        )

        if structure_direction == "LONG":
            direction_scores["LONG"] += 15.0
            reasons.append(
                "Market structure is bullish."
            )

        elif structure_direction == "SHORT":
            direction_scores["SHORT"] += 15.0
            reasons.append(
                "Market structure is bearish."
            )

        # -------------------------------------------------
        # BREAK OF STRUCTURE
        # -------------------------------------------------

        bos = structure.get(
            "break_of_structure",
            {},
        )

        bos_direction = self._direction(
            bos.get("direction")
            if isinstance(bos, dict)
            else "NEUTRAL"
        )

        if bos_direction == "LONG":
            direction_scores["LONG"] += 10.0
            reasons.append(
                "Bullish break of structure detected."
            )

        elif bos_direction == "SHORT":
            direction_scores["SHORT"] += 10.0
            reasons.append(
                "Bearish break of structure detected."
            )

        # -------------------------------------------------
        # VWAP
        # -------------------------------------------------

        vwap = self._float(
            indicators.get("vwap")
        )

        if vwap > 0 and price > vwap:
            direction_scores["LONG"] += 5.0
            reasons.append(
                "Price is above VWAP."
            )

        elif vwap > 0 and price < vwap:
            direction_scores["SHORT"] += 5.0
            reasons.append(
                "Price is below VWAP."
            )

        # -------------------------------------------------
        # ACTUAL SUPPORT / RESISTANCE SETUP
        # -------------------------------------------------

        setup = self._support_resistance_setup(
            candles,
            indicators,
            structure,
        )

        retest_long_score, retest_long_reasons = (
            self._retest_score(
                "LONG",
                setup,
            )
        )

        retest_short_score, retest_short_reasons = (
            self._retest_score(
                "SHORT",
                setup,
            )
        )

        location_long_score, location_long_reasons = (
            self._location_confirmation(
                "LONG",
                indicators,
                setup,
            )
        )

        location_short_score, location_short_reasons = (
            self._location_confirmation(
                "SHORT",
                indicators,
                setup,
            )
        )

        # A support/resistance setup is not just another small
        # confirmation. It is the entry-location gate.
        if retest_long_score > 0:
            direction_scores["LONG"] += 25.0
            reasons.extend(retest_long_reasons)

            if location_long_score >= 45:
                direction_scores["LONG"] += 20.0
                reasons.extend(location_long_reasons)

        if retest_short_score > 0:
            direction_scores["SHORT"] += 25.0
            reasons.extend(retest_short_reasons)

            if location_short_score >= 45:
                direction_scores["SHORT"] += 20.0
                reasons.extend(location_short_reasons)

        # -------------------------------------------------
        # RANGE / MID-RANGE PROTECTION
        # -------------------------------------------------

        sr = structure.get(
            "support_resistance",
            {},
        )

        location = (
            str(
                sr.get("location", "UNKNOWN")
            ).upper()
            if isinstance(sr, dict)
            else "UNKNOWN"
        )

        # If there is no repeated level setup, do not create a
        # signal merely because the coin has moved.
        if setup.get("setup") not in {
            "SUPPORT",
            "RESISTANCE",
        }:
            reasons.append(
                "No repeated support/resistance entry location was confirmed."
            )

        if location == "MID_RANGE":
            reasons.append(
                "Current price is in the middle of the recent range."
            )

        # -------------------------------------------------
        # FINAL TIMEFRAME DIRECTION
        # -------------------------------------------------

        long_score = direction_scores["LONG"]
        short_score = direction_scores["SHORT"]

        if long_score > short_score:
            direction = "LONG"
            score = long_score

        elif short_score > long_score:
            direction = "SHORT"
            score = short_score

        else:
            direction = "NEUTRAL"
            score = 0.0

        # Hard entry-location gate.
        if direction == "LONG" and setup.get("setup") != "SUPPORT":
            direction = "NEUTRAL"
            score = 0.0

        if direction == "SHORT" and setup.get("setup") != "RESISTANCE":
            direction = "NEUTRAL"
            score = 0.0

        confidence = min(
            100.0,
            score,
        )

        return {
            "success": True,
            "timeframe": timeframe,
            "direction": direction,
            "confidence": round(confidence, 2),
            "score": round(score, 2),
            "indicators": indicators,
            "structure": structure,
            "setup": setup,
            "entry_location": {
                "setup": setup.get("setup", "NONE"),
                "support_touches": int(
                    self._float(
                        setup.get("support", {}).get("touches")
                        if isinstance(setup.get("support"), dict)
                        else 0
                    )
                ),
                "resistance_touches": int(
                    self._float(
                        setup.get("resistance", {}).get("touches")
                        if isinstance(setup.get("resistance"), dict)
                        else 0
                    )
                ),
                "location_long_score": round(
                    location_long_score,
                    2,
                ),
                "location_short_score": round(
                    location_short_score,
                    2,
                ),
                "retest_long_score": round(
                    retest_long_score,
                    2,
                ),
                "retest_short_score": round(
                    retest_short_score,
                    2,
                ),
            },
            "reasons": self._dedupe(reasons),
        }

    # =====================================================
    # MULTI-TIMEFRAME ANALYSIS
    # =====================================================

    async def analyze_symbol(
        self,
        symbol: str,
        market: str = "futures",
        candle_limit: int = 200,
    ) -> dict[str, Any]:
        symbol = str(symbol).upper().strip()
        market = str(market).lower().strip()

        if market not in {"spot", "futures"}:
            raise ValueError(
                "market must be 'spot' or 'futures'"
            )

        market_data = await market_data_service.core_timeframes(
            symbol=symbol,
            market=market,
            limit=candle_limit,
        )

        timeframe_tasks = []

        for timeframe in self.CORE_TIMEFRAMES:
            item = market_data.get(
                timeframe,
                {},
            )

            candles = []

            if isinstance(item, dict):
                candles = item.get(
                    "candles",
                    [],
                )

            timeframe_tasks.append(
                asyncio.to_thread(
                    self.analyze_timeframe,
                    timeframe,
                    candles,
                )
            )

        timeframe_results = await asyncio.gather(
            *timeframe_tasks,
            return_exceptions=True,
        )

        timeframe_analysis: dict[
            str,
            dict[str, Any],
        ] = {}

        for timeframe, result in zip(
            self.CORE_TIMEFRAMES,
            timeframe_results,
        ):
            if isinstance(result, Exception):
                timeframe_analysis[timeframe] = {
                    "success": False,
                    "timeframe": timeframe,
                    "direction": "NEUTRAL",
                    "confidence": 0.0,
                    "error": str(result),
                }
            else:
                timeframe_analysis[timeframe] = result

        # -------------------------------------------------
        # MTF ENGINE
        # -------------------------------------------------

        mtf = mtf_engine.analyze(
            timeframe_analysis
        )

        direction = self._direction(
            mtf.get("direction")
        )

        # -------------------------------------------------
        # STRICT ENTRY-LOCATION AGREEMENT
        # -------------------------------------------------

        entry_15m = timeframe_analysis.get(
            "15m",
            {},
        )

        entry_setup = (
            entry_15m.get("setup", {})
            if isinstance(entry_15m, dict)
            else {}
        )

        entry_location = (
            entry_15m.get("entry_location", {})
            if isinstance(entry_15m, dict)
            else {}
        )

        setup_type = str(
            entry_setup.get(
                "setup",
                "NONE",
            )
        ).upper()

        support_touches = int(
            self._float(
                entry_location.get(
                    "support_touches",
                    0,
                )
            )
        )

        resistance_touches = int(
            self._float(
                entry_location.get(
                    "resistance_touches",
                    0,
                )
            )
        )

        # The actual entry location decides whether the MTF
        # direction is allowed to become a signal.
        location_matches = (
            (
                direction == "LONG"
                and setup_type == "SUPPORT"
                and support_touches >= self.MIN_SUPPORT_TOUCHES
            )
            or
            (
                direction == "SHORT"
                and setup_type == "RESISTANCE"
                and resistance_touches >= self.MIN_RESISTANCE_TOUCHES
            )
        )

        # All three core timeframes must agree before publication.
        mtf_strict = bool(
            mtf.get(
                "publishable_mtf",
                False,
            )
        )

        confidence = self._float(
            mtf.get(
                "weighted_confidence",
                0,
            )
        )

        if not location_matches:
            confidence *= 0.35

        if not mtf_strict:
            confidence *= 0.60

        # Entry-location reaction is a major confidence component.
        if isinstance(entry_location, dict):
            if direction == "LONG":
                reaction = max(
                    self._float(
                        entry_location.get(
                            "retest_long_score"
                        )
                    ),
                    self._float(
                        entry_location.get(
                            "location_long_score"
                        )
                    ),
                )
            elif direction == "SHORT":
                reaction = max(
                    self._float(
                        entry_location.get(
                            "retest_short_score"
                        )
                    ),
                    self._float(
                        entry_location.get(
                            "location_short_score"
                        )
                    ),
                )
            else:
                reaction = 0.0

            confidence = (
                confidence * 0.65
                + reaction * 0.35
            )

        confidence = round(
            min(
                100.0,
                max(
                    0.0,
                    confidence,
                ),
            ),
            2,
        )

        # -------------------------------------------------
        # HARD PUBLISH GATE
        # -------------------------------------------------

        publishable = (
            direction in {"LONG", "SHORT"}
            and mtf_strict
            and location_matches
            and confidence >= self.PUBLISH_CONFIDENCE
        )

        reasons: list[str] = []

        for timeframe in self.CORE_TIMEFRAMES:
            item = timeframe_analysis.get(
                timeframe,
                {},
            )

            if isinstance(item, dict):
                reasons.extend(
                    item.get(
                        "reasons",
                        [],
                    )
                )

        if setup_type == "SUPPORT":
            reasons.append(
                f"15m entry location is repeated support with {support_touches} touches."
            )

        elif setup_type == "RESISTANCE":
            reasons.append(
                f"15m entry location is repeated resistance with {resistance_touches} touches."
            )

        else:
            reasons.append(
                "No valid repeated support/resistance entry location."
            )

        if mtf_strict:
            reasons.append(
                "15m, 1h and 4h are aligned."
            )
        else:
            reasons.append(
                "Core MTF alignment is not fully confirmed."
            )

        if not location_matches:
            reasons.append(
                "Entry-location gate failed; top-gainer/top-loser style movement is not enough."
            )

        if confidence < self.PUBLISH_CONFIDENCE:
            reasons.append(
                f"Confidence is below the {self.PUBLISH_CONFIDENCE:.0f}% publication threshold."
            )

        return {
            "success": True,
            "symbol": symbol,
            "market": market,
            "direction": direction,
            "confidence": confidence,
            "publishable": publishable,
            "signal_type": (
                "SUPPORT_LONG"
                if direction == "LONG"
                and setup_type == "SUPPORT"
                else "RESISTANCE_SHORT"
                if direction == "SHORT"
                and setup_type == "RESISTANCE"
                else "NO_VALID_LOCATION"
            ),
            "entry_location": {
                "setup": setup_type,
                "location_matches": location_matches,
                "support_touches": support_touches,
                "resistance_touches": resistance_touches,
                "support": entry_setup.get(
                    "support",
                    {},
                ),
                "resistance": entry_setup.get(
                    "resistance",
                    {},
                ),
            },
            "timeframes": timeframe_analysis,
            "multi_timeframe": mtf,
            "gates": {
                "mtf_strict": mtf_strict,
                "entry_location": location_matches,
                "minimum_support_touches": self.MIN_SUPPORT_TOUCHES,
                "minimum_resistance_touches": self.MIN_RESISTANCE_TOUCHES,
                "confidence_threshold": self.PUBLISH_CONFIDENCE,
            },
            "reasons": self._dedupe(reasons),
        }


signal_engine = SignalEngine()


__all__ = [
    "SignalEngine",
    "signal_engine",
]
