from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AnalysisPoint:
    number: int
    name: str
    category: str


class AnalysisEngine:
    """
    RR Trader 24-point market analysis engine.

    The engine converts available market evidence into
    structured confirmations.

    IMPORTANT:
    This engine does NOT publish trades and does NOT make
    the final confidence decision.

    It produces evidence for:
        - confidence_engine
        - signal_engine
        - risk_engine
        - trade_engine

    Core strategy priority:

        1. Market structure
        2. Support / resistance location
        3. Rejection / sweep
        4. Momentum
        5. Volume
        6. Multi-timeframe confirmation
        7. Derivatives / liquidity
        8. Risk / execution

    The scanner must NOT simply select top gainers
    or top losers and call them trade signals.
    """

    # =====================================================
    # CONFIGURATION
    # =====================================================

    MIN_CANDLE_COUNT = 50

    SUPPORT_TOUCH_TOLERANCE = 0.75
    RESISTANCE_TOUCH_TOLERANCE = 0.75

    STRONG_SUPPORT_TOUCHES = 2
    STRONG_RESISTANCE_TOUCHES = 2

    MIN_RR = 1.50
    GOOD_RR = 2.00

    MIN_VOLUME_RATIO = 1.20

    # =====================================================
    # 24 ANALYSIS POINTS
    # =====================================================

    MARKET_POINTS = (
        AnalysisPoint(
            1,
            "Market Regime",
            "market",
        ),
        AnalysisPoint(
            2,
            "Market Structure",
            "market",
        ),
        AnalysisPoint(
            3,
            "Multi-Timeframe Confirmation",
            "market",
        ),
        AnalysisPoint(
            4,
            "Entry Location",
            "market",
        ),
        AnalysisPoint(
            5,
            "Liquidity Sweep",
            "market",
        ),
        AnalysisPoint(
            6,
            "VWAP",
            "market",
        ),
        AnalysisPoint(
            7,
            "ATR / Volatility",
            "market",
        ),
        AnalysisPoint(
            8,
            "Momentum",
            "market",
        ),
        AnalysisPoint(
            9,
            "Divergence",
            "market",
        ),
        AnalysisPoint(
            10,
            "Breakout",
            "market",
        ),
        AnalysisPoint(
            11,
            "Retest",
            "market",
        ),
        AnalysisPoint(
            12,
            "Derivatives",
            "market",
        ),
        AnalysisPoint(
            13,
            "Liquidations",
            "market",
        ),
        AnalysisPoint(
            14,
            "Order Book",
            "market",
        ),
        AnalysisPoint(
            15,
            "Tradeability",
            "market",
        ),
        AnalysisPoint(
            16,
            "News / Event Risk",
            "market",
        ),
        AnalysisPoint(
            17,
            "BTC / Market Context",
            "market",
        ),
        AnalysisPoint(
            18,
            "Relative Strength",
            "market",
        ),
        AnalysisPoint(
            19,
            "Risk / Reward",
            "market",
        ),
        AnalysisPoint(
            20,
            "Stop Quality",
            "market",
        ),
    )

    RISK_POINTS = (
        AnalysisPoint(
            21,
            "Position Sizing",
            "risk",
        ),
        AnalysisPoint(
            22,
            "Portfolio Risk",
            "risk",
        ),
        AnalysisPoint(
            23,
            "Execution Quality",
            "risk",
        ),
        AnalysisPoint(
            24,
            "Signal Freshness",
            "risk",
        ),
    )

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
    def _upper(
        value: Any,
        default: str = "",
    ) -> str:

        return str(
            value or default
        ).upper().strip()

    @staticmethod
    def _lower(
        value: Any,
        default: str = "",
    ) -> str:

        return str(
            value or default
        ).lower().strip()

    @staticmethod
    def _bool(
        value: Any,
    ) -> bool:

        if isinstance(
            value,
            bool,
        ):
            return value

        if isinstance(
            value,
            str,
        ):

            return value.lower().strip() in {
                "true",
                "1",
                "yes",
                "confirmed",
                "valid",
                "strong",
            }

        return bool(value)

    # =====================================================
    # POINT DEFINITIONS
    # =====================================================

    @classmethod
    def all_points(
        cls,
    ) -> tuple[AnalysisPoint, ...]:

        return (
            cls.MARKET_POINTS
            + cls.RISK_POINTS
        )

    @classmethod
    def point_definitions(
        cls,
    ) -> list[dict[str, Any]]:

        return [
            {
                "number": point.number,
                "name": point.name,
                "category": point.category,
            }
            for point in cls.all_points()
        ]

    # =====================================================
    # EMPTY POINT
    # =====================================================

    @classmethod
    def _point(
        cls,
        point: AnalysisPoint,
        *,
        status: str = "PENDING",
        direction: str = "NEUTRAL",
        score: float = 0.0,
        reason: str = "",
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:

        return {
            "number": point.number,
            "name": point.name,
            "category": point.category,
            "status": status,
            "direction": direction,
            "score": round(
                score,
                4,
            ),
            "reason": reason,
            "evidence": evidence or {},
        }

    # =====================================================
    # EMPTY RESULT
    # =====================================================

    @classmethod
    def empty_result(
        cls,
        *,
        symbol: str,
        market: str,
        direction: str = "NEUTRAL",
    ) -> dict[str, Any]:

        points: dict[
            str,
            dict[str, Any],
        ] = {}

        for point in cls.all_points():

            points[
                str(point.number)
            ] = cls._point(
                point
            )

        return {
            "success": True,
            "symbol": symbol.upper(),
            "market": market.lower(),
            "direction": direction.upper(),
            "points": points,
            "market_confirmation_count": 0,
            "risk_gate_count": 0,
            "market_confirmation_total": 20,
            "risk_gate_total": 4,
            "critical_failures": [],
            "long_evidence": 0.0,
            "short_evidence": 0.0,
            "setup_type": "NONE",
            "status": "analysis_pending",
        }

    # =====================================================
    # MARKET DATA EXTRACTION
    # =====================================================

    @classmethod
    def _extract_indicators(
        cls,
        market_data: dict[str, Any],
        timeframe: str | None = None,
    ) -> dict[str, Any]:

        if not isinstance(
            market_data,
            dict,
        ):
            return {}

        # Direct indicator object.
        indicators = market_data.get(
            "indicators"
        )

        if isinstance(
            indicators,
            dict,
        ):
            return indicators

        # Timeframe-specific data.
        timeframes = market_data.get(
            "timeframes"
        )

        if isinstance(
            timeframes,
            dict,
        ):

            if timeframe:

                selected = timeframes.get(
                    timeframe
                )

                if isinstance(
                    selected,
                    dict,
                ):

                    nested = selected.get(
                        "indicators"
                    )

                    if isinstance(
                        nested,
                        dict,
                    ):
                        return nested

                    return selected

            for value in timeframes.values():

                if not isinstance(
                    value,
                    dict,
                ):
                    continue

                nested = value.get(
                    "indicators"
                )

                if isinstance(
                    nested,
                    dict,
                ):
                    return nested

        return {}

    # =====================================================
    # EXTRACT MARKET STRUCTURE
    # =====================================================

    @classmethod
    def _extract_structure(
        cls,
        market_data: dict[str, Any],
    ) -> dict[str, Any]:

        structure = market_data.get(
            "market_structure"
        )

        if isinstance(
            structure,
            dict,
        ):
            return structure

        structure = market_data.get(
            "structure"
        )

        if isinstance(
            structure,
            dict,
        ):
            return structure

        return {}

    # =====================================================
    # EXTRACT SUPPORT / RESISTANCE
    # =====================================================

    @classmethod
    def _extract_levels(
        cls,
        market_data: dict[str, Any],
        structure: dict[str, Any],
    ) -> tuple[float, float]:

        support = 0.0
        resistance = 0.0

        support_keys = (
            "support",
            "support_level",
            "nearest_support",
            "strongest_support",
        )

        resistance_keys = (
            "resistance",
            "resistance_level",
            "nearest_resistance",
            "strongest_resistance",
        )

        for key in support_keys:

            support = cls._float(
                structure.get(
                    key
                )
            )

            if support > 0:
                break

        if support <= 0:

            for key in support_keys:

                support = cls._float(
                    market_data.get(
                        key
                    )
                )

                if support > 0:
                    break

        for key in resistance_keys:

            resistance = cls._float(
                structure.get(
                    key
                )
            )

            if resistance > 0:
                break

        if resistance <= 0:

            for key in resistance_keys:

                resistance = cls._float(
                    market_data.get(
                        key
                    )
                )

                if resistance > 0:
                    break

        return (
            support,
            resistance,
        )

    # =====================================================
    # TOUCH COUNT
    # =====================================================

    @classmethod
    def _touch_count(
        cls,
        values: Any,
        level: float,
        tolerance_percent: float,
    ) -> int:

        if (
            level <= 0
            or not isinstance(
                values,
                list,
            )
        ):
            return 0

        count = 0

        tolerance = (
            tolerance_percent
            / 100.0
        )

        for value in values:

            price = cls._float(
                value
            )

            if price <= 0:
                continue

            distance = abs(
                price - level
            ) / level

            if distance <= tolerance:

                count += 1

        return count

    # =====================================================
    # DETERMINE SETUP
    # =====================================================

    @classmethod
    def _determine_setup(
        cls,
        *,
        direction: str,
        structure: dict[str, Any],
        indicators: dict[str, Any],
        support: float,
        resistance: float,
        current_price: float,
        market_data: dict[str, Any],
    ) -> dict[str, Any]:

        structure_state = cls._upper(
            structure.get(
                "state",
                structure.get(
                    "trend",
                    "",
                ),
            )
        )

        structure_direction = cls._upper(
            structure.get(
                "direction",
                structure.get(
                    "bias",
                    "",
                ),
            )
        )

        candle = indicators.get(
            "candle_structure",
            {}
        )

        if not isinstance(
            candle,
            dict,
        ):
            candle = {}

        bullish_rejection = (
            cls._bool(
                candle.get(
                    "bullish_rejection"
                )
            )
        )

        bearish_rejection = (
            cls._bool(
                candle.get(
                    "bearish_rejection"
                )
            )

        range_data = indicators.get(
            "recent_range",
            {}
        )

        if not isinstance(
            range_data,
            dict,
        ):
            range_data = {}

        position = cls._float(
            range_data.get(
                "position_percent"
            )
        )

        support_touches = cls._float(
            structure.get(
                "support_touches",
                structure.get(
                    "support_touch_count",
                    0,
                ),
            )
        )

        resistance_touches = cls._float(
            structure.get(
                "resistance_touches",
                structure.get(
                    "resistance_touch_count",
                    0,
                ),
            )
        )

        # -------------------------------------------------
        # LONG SUPPORT BOUNCE
        # -------------------------------------------------

        support_bounce = (
            support > 0
            and current_price >= support
            and (
                support_touches
                >= cls.STRONG_SUPPORT_TOUCHES
            )
            and (
                bullish_rejection
                or structure_direction
                == "LONG"
            )
        )

        if support_bounce:

            return {
                "type": "SUPPORT_BOUNCE",
                "direction": "LONG",
                "priority": "HIGH",
                "support": support,
                "resistance": resistance,
                "support_touches": int(
                    support_touches
                ),
                "reason": (
                    "Repeated support interaction "
                    "with bullish reaction."
                ),
            }

        # -------------------------------------------------
        # SHORT RESISTANCE REJECTION
        # -------------------------------------------------

        resistance_rejection = (
            resistance > 0
            and current_price <= resistance
            and (
                resistance_touches
                >= cls.STRONG_RESISTANCE_TOUCHES
            )
            and (
                bearish_rejection
                or structure_direction
                == "SHORT"
            )
        )

        if resistance_rejection:

            return {
                "type": (
                    "RESISTANCE_REJECTION"
                ),
                "direction": "SHORT",
                "priority": "HIGH",
                "support": support,
                "resistance": resistance,
                "resistance_touches": int(
                    resistance_touches
                ),
                "reason": (
                    "Repeated resistance interaction "
                    "with bearish reaction."
                ),
            }

        # -------------------------------------------------
        # RANGE LOCATION
        # -------------------------------------------------

        if (
            position <= 30
            and structure_direction
            == "LONG"
        ):

            return {
                "type": "RANGE_LOW_LONG",
                "direction": "LONG",
                "priority": "MEDIUM",
                "support": support,
                "resistance": resistance,
                "reason": (
                    "Price is located near "
                    "the lower range."
                ),
            }

        if (
            position >= 70
            and structure_direction
            == "SHORT"
        ):

            return {
                "type": "RANGE_HIGH_SHORT",
                "direction": "SHORT",
                "priority": "MEDIUM",
                "support": support,
                "resistance": resistance,
                "reason": (
                    "Price is located near "
                    "the upper range."
                ),
            }

        # -------------------------------------------------
        # BREAKOUT
        # -------------------------------------------------

        breakout = indicators.get(
            "breakout",
            {}
        )

        if isinstance(
            breakout,
            dict,
        ):

            breakout_direction = (
                cls._upper(
                    breakout.get(
                        "direction"
                    )
                )
            )

            if breakout_direction in {
                "LONG",
                "SHORT",
            }:

                return {
                    "type": (
                        "BREAKOUT_"
                        + breakout_direction
                    ),
                    "direction": (
                        breakout_direction
                    ),
                    "priority": "MEDIUM",
                    "support": support,
                    "resistance": resistance,
                    "reason": (
                        "Price has broken "
                        "the recent range."
                    ),
                }

        return {
            "type": "NONE",
            "direction": (
                direction
                if direction in {
                    "LONG",
                    "SHORT",
                }
                else "NEUTRAL"
            ),
            "priority": "LOW",
            "support": support,
            "resistance": resistance,
            "reason": (
                "No high-quality location "
                "setup detected."
            ),
        }

    # =====================================================
    # POINT 1 - MARKET REGIME
    # =====================================================

    @classmethod
    def _market_regime(
        cls,
        point: AnalysisPoint,
        indicators: dict[str, Any],
    ) -> dict[str, Any]:

        trend = indicators.get(
            "trend",
            {}
        )

        if not isinstance(
            trend,
            dict,
        ):
            trend = {}

        state = cls._upper(
            trend.get(
                "state"
            )
        )

        if state in {
            "STRONG_BULLISH",
            "BULLISH",
        }:

            return cls._point(
                point,
                status="CONFIRMED",
                direction="LONG",
                score=1.0,
                reason=(
                    "Market regime is bullish."
                ),
                evidence=trend,
            )

        if state in {
            "STRONG_BEARISH",
            "BEARISH",
        }:

            return cls._point(
                point,
                status="CONFIRMED",
                direction="SHORT",
                score=1.0,
                reason=(
                    "Market regime is bearish."
                ),
                evidence=trend,
            )

        return cls._point(
            point,
            status="NEUTRAL",
            reason=(
                "Market regime is not clearly "
                "directional."
            ),
            evidence=trend,
        )

    # =====================================================
    # POINT 2 - MARKET STRUCTURE
    # =====================================================

    @classmethod
    def _market_structure(
        cls,
        point: AnalysisPoint,
        structure: dict[str, Any],
    ) -> dict[str, Any]:

        if not structure:

            return cls._point(
                point,
                status="PENDING",
                reason=(
                    "Market structure data "
                    "is not available."
                ),
            )

        direction = cls._upper(
            structure.get(
                "direction",
                structure.get(
                    "bias",
                    "",
                ),
            )
        )

        state = cls._upper(
            structure.get(
                "state",
                structure.get(
                    "trend",
                    "",
                ),
            )
        )

        bullish = (
            direction == "LONG"
            or state in {
                "BULLISH",
                "STRONG_BULLISH",
            }
        )

        bearish = (
            direction == "SHORT"
            or state in {
                "BEARISH",
                "STRONG_BEARISH",
            }
        )

        if bullish and not bearish:

            return cls._point(
                point,
                status="CONFIRMED",
                direction="LONG",
                score=1.0,
                reason=(
                    "Bullish market structure "
                    "confirmed."
                ),
                evidence=structure,
            )

        if bearish and not bullish:

            return cls._point(
                point,
                status="CONFIRMED",
                direction="SHORT",
                score=1.0,
                reason=(
                    "Bearish market structure "
                    "confirmed."
                ),
                evidence=structure,
            )

        return cls._point(
            point,
            status="NEUTRAL",
            reason=(
                "Market structure is mixed."
            ),
            evidence=structure,
        )

    # =====================================================
    # POINT 3 - MTF
    # =====================================================

    @classmethod
    def _mtf_confirmation(
        cls,
        point: AnalysisPoint,
        market_data: dict[str, Any],
    ) -> dict[str, Any]:

        mtf = market_data.get(
            "multi_timeframe"
        )

        if not isinstance(
            mtf,
            dict,
        ):

            mtf = market_data.get(
                "mtf",
                {}
            )

        if not isinstance(
            mtf,
            dict,
        ):

            return cls._point(
                point,
                status="PENDING",
                reason=(
                    "Multi-timeframe data "
                    "is not available."
                ),
            )

        long_votes = 0
        short_votes = 0

        for value in mtf.values():

            if not isinstance(
                value,
                dict,
            ):
                continue

            direction = cls._upper(
                value.get(
                    "direction",
                    value.get(
                        "bias",
                        "",
                    ),
                )
            )

            if direction == "LONG":
                long_votes += 1

            elif direction == "SHORT":
                short_votes += 1

        if long_votes > short_votes:

            return cls._point(
                point,
                status="CONFIRMED",
                direction="LONG",
                score=1.0,
                reason=(
                    f"MTF bullish votes: "
                    f"{long_votes}."
                ),
                evidence={
                    "long_votes": long_votes,
                    "short_votes": short_votes,
                },
            )

        if short_votes > long_votes:

            return cls._point(
                point,
                status="CONFIRMED",
                direction="SHORT",
                score=1.0,
                reason=(
                    f"MTF bearish votes: "
                    f"{short_votes}."
                ),
                evidence={
                    "long_votes": long_votes,
                    "short_votes": short_votes,
                },
            )

        return cls._point(
            point,
            status="NEUTRAL",
            reason=(
                "MTF confirmation is mixed."
            ),
            evidence={
                "long_votes": long_votes,
                "short_votes": short_votes,
            },
        )

    # =====================================================
    # POINT 4 - ENTRY LOCATION
    # =====================================================

    @classmethod
    def _entry_location(
        cls,
        point: AnalysisPoint,
        setup: dict[str, Any],
    ) -> dict[str, Any]:

        setup_type = cls._upper(
            setup.get(
                "type"
            )
        )

        direction = cls._upper(
            setup.get(
                "direction"
            )
        )

        if setup_type in {
            "SUPPORT_BOUNCE",
            "RANGE_LOW_LONG",
        }:

            return cls._point(
                point,
                status="CONFIRMED",
                direction="LONG",
                score=1.0,
                reason=(
                    "Price is located in a "
                    "potential long entry area."
                ),
                evidence=setup,
            )

        if setup_type in {
            "RESISTANCE_REJECTION",
            "RANGE_HIGH_SHORT",
        }:

            return cls._point(
                point,
                status="CONFIRMED",
                direction="SHORT",
                score=1.0,
                reason=(
                    "Price is located in a "
                    "potential short entry area."
                ),
                evidence=setup,
            )

        return cls._point(
            point,
            status="NEUTRAL",
            direction=direction
            if direction in {
                "LONG",
                "SHORT",
            }
            else "NEUTRAL",
            reason=(
                "No high-quality entry "
                "location confirmed."
            ),
            evidence=setup,
        )

    # =====================================================
    # POINT 5 - LIQUIDITY SWEEP
    # =====================================================

    @classmethod
    def _liquidity_sweep(
        cls,
        point: AnalysisPoint,
        market_data: dict[str, Any],
    ) -> dict[str, Any]:

        sweep = market_data.get(
            "liquidity_sweep"
        )

        if not isinstance(
            sweep,
            dict,
        ):

            sweep = market_data.get(
                "sweep",
                {}
            )

        if not isinstance(
            sweep,
            dict,
        ):
            sweep = {}

        direction = cls._upper(
            sweep.get(
                "direction"
            )
        )

        confirmed = cls._bool(
            sweep.get(
                "confirmed",
                sweep.get(
                    "sweep",
                    False,
                ),
            )
        )

        if confirmed and direction in {
            "LONG",
            "SHORT",
        }:

            return cls._point(
                point,
                status="CONFIRMED",
                direction=direction,
                score=1.0,
                reason=(
                    "Liquidity sweep confirmed."
                ),
                evidence=sweep,
            )

        return cls._point(
            point,
            status="NEUTRAL",
            reason=(
                "No confirmed liquidity sweep."
            ),
            evidence=sweep,
        )

    # =====================================================
    # POINT 6 - VWAP
    # =====================================================

    @classmethod
    def _vwap(
        cls,
        point: AnalysisPoint,
        indicators: dict[str, Any],
    ) -> dict[str, Any]:

        price = cls._float(
            indicators.get(
                "price"
            )
        )

        vwap = cls._float(
            indicators.get(
                "vwap"
            )
        )

        if (
            price <= 0
            or vwap <= 0
        ):

            return cls._point(
                point,
                status="PENDING",
                reason=(
                    "VWAP data is not available."
                ),
            )

        if price > vwap:

            return cls._point(
                point,
                status="CONFIRMED",
                direction="LONG",
                score=1.0,
                reason=(
                    "Price is above VWAP."
                ),
                evidence={
                    "price": price,
                    "vwap": vwap,
                },
            )

        if price < vwap:

            return cls._point(
                point,
                status="CONFIRMED",
                direction="SHORT",
                score=1.0,
                reason=(
                    "Price is below VWAP."
                ),
                evidence={
                    "price": price,
                    "vwap": vwap,
                },
            )

        return cls._point(
            point,
            status="NEUTRAL",
            reason="Price is at VWAP.",
            evidence={
                "price": price,
                "vwap": vwap,
            },
        )

    # =====================================================
    # POINT 7 - ATR
    # =====================================================

    @classmethod
    def _atr(
        cls,
        point: AnalysisPoint,
        indicators: dict[str, Any],
    ) -> dict[str, Any]:

        atr = cls._float(
            indicators.get(
                "atr"
            )
        )

        atr_percent = cls._float(
            indicators.get(
                "atr_percent"
            )
        )

        if atr <= 0:

            return cls._point(
                point,
                status="PENDING",
                reason=(
                    "ATR data is not available."
                ),
            )

        if atr_percent > 0:

            reason = (
                f"ATR volatility is "
                f"{atr_percent:.3f}%."
            )

        else:

            reason = (
                "ATR volatility is available."
            )

        return cls._point(
            point,
            status="CONFIRMED",
            score=1.0,
            reason=reason,
            evidence={
                "atr": atr,
                "atr_percent": atr_percent,
            },
        )

    # =====================================================
    # POINT 8 - MOMENTUM
    # =====================================================

    @classmethod
    def _momentum(
        cls,
        point: AnalysisPoint,
        indicators: dict[str, Any],
    ) -> dict[str, Any]:

        momentum = cls._float(
            indicators.get(
                "momentum"
            )
        )

        analysis = indicators.get(
            "momentum_analysis",
            {}
        )

        if not isinstance(
            analysis,
            dict,
        ):
            analysis = {}

        state = cls._upper(
            analysis.get(
                "state"
            )
        )

        if (
            momentum > 0
            or state
            == "ACCELERATING_UP"
        ):

            return cls._point(
                point,
                status="CONFIRMED",
                direction="LONG",
                score=1.0,
                reason=(
                    "Positive momentum detected."
                ),
                evidence={
                    "momentum": momentum,
                    **analysis,
                },
            )

        if (
            momentum < 0
            or state
            == "ACCELERATING_DOWN"
        ):

            return cls._point(
                point,
                status="CONFIRMED",
                direction="SHORT",
                score=1.0,
                reason=(
                    "Negative momentum detected."
                ),
                evidence={
                    "momentum": momentum,
                    **analysis,
                },
            )

        return cls._point(
            point,
            status="NEUTRAL",
            reason=(
                "Momentum is neutral."
            ),
            evidence={
                "momentum": momentum,
                **analysis,
            },
        )

    # =====================================================
    # POINT 9 - DIVERGENCE
    # =====================================================

    @classmethod
    def _divergence(
        cls,
        point: AnalysisPoint,
        market_data: dict[str, Any],
    ) -> dict[str, Any]:

        divergence = market_data.get(
            "divergence"
        )

        if not isinstance(
            divergence,
            dict,
        ):
            divergence = {}

        direction = cls._upper(
            divergence.get(
                "direction"
            )
        )

        confirmed = cls._bool(
            divergence.get(
                "confirmed"
            )
        )

        if (
            confirmed
            and direction in {
                "LONG",
                "SHORT",
            }
        ):

            return cls._point(
                point,
                status="CONFIRMED",
                direction=direction,
                score=1.0,
                reason=(
                    "Divergence confirmation "
                    "is available."
                ),
                evidence=divergence,
            )

        return cls._point(
            point,
            status="NEUTRAL",
            reason=(
                "No confirmed divergence."
            ),
            evidence=divergence,
        )

    # =====================================================
    # POINT 10 - BREAKOUT
    # =====================================================

    @classmethod
    def _breakout(
        cls,
        point: AnalysisPoint,
        indicators: dict[str, Any],
    ) -> dict[str, Any]:

        breakout = indicators.get(
            "breakout",
            {}
        )

        if not isinstance(
            breakout,
            dict,
        ):
            breakout = {}

        direction = cls._upper(
            breakout.get(
                "direction"
            )
        )

        confirmed = cls._bool(
            breakout.get(
                "breakout"
            )
        )

        if (
            confirmed
            and direction in {
                "LONG",
                "SHORT",
            }
        ):

            return cls._point(
                point,
                status="CONFIRMED",
                direction=direction,
                score=1.0,
                reason=(
                    "Recent range breakout "
                    "detected."
                ),
                evidence=breakout,
            )

        return cls._point(
            point,
            status="NEUTRAL",
            reason=(
                "No active breakout."
            ),
            evidence=breakout,
        )

    # =====================================================
    # POINT 11 - RETEST
    # =====================================================

    @classmethod
    def _retest(
        cls,
        point: AnalysisPoint,
        market_data: dict[str, Any],
    ) -> dict[str, Any]:

        retest = market_data.get(
            "retest"
        )

        if not isinstance(
            retest,
            dict,
        ):
            retest = {}

        confirmed = cls._bool(
            retest.get(
                "confirmed"
            )
        )

        direction = cls._upper(
            retest.get(
                "direction"
            )
        )

        if (
            confirmed
            and direction in {
                "LONG",
                "SHORT",
            }
        ):

            return cls._point(
                point,
                status="CONFIRMED",
                direction=direction,
                score=1.0,
                reason=(
                    "Breakout/retest confirmation "
                    "is available."
                ),
                evidence=retest,
            )

        return cls._point(
            point,
            status="NEUTRAL",
            reason=(
                "No confirmed retest."
            ),
            evidence=retest,
        )

    # =====================================================
    # POINT 12 - DERIVATIVES
    # =====================================================

    @classmethod
    def _derivatives(
        cls,
        point: AnalysisPoint,
        market_data: dict[str, Any],
    ) -> dict[str, Any]:

        derivatives = market_data.get(
            "derivatives"
        )

        if not isinstance(
            derivatives,
            dict,
        ):
            derivatives = {}

        direction = cls._upper(
            derivatives.get(
                "direction",
                derivatives.get(
                    "bias",
                    "",
                ),
            )
        )

        confirmed = cls._bool(
            derivatives.get(
                "confirmed"
            )
        )

        if (
            confirmed
            and direction in {
                "LONG",
                "SHORT",
            }
        ):

            return cls._point(
                point,
                status="CONFIRMED",
                direction=direction,
                score=1.0,
                reason=(
                    "Derivatives data supports "
                    "the direction."
                ),
                evidence=derivatives,
            )

        return cls._point(
            point,
            status="NEUTRAL",
            reason=(
                "Derivatives confirmation "
                "is not available."
            ),
            evidence=derivatives,
        )

    # =====================================================
    # POINT 13 - LIQUIDATIONS
    # =====================================================

    @classmethod
    def _liquidations(
        cls,
        point: AnalysisPoint,
        market_data: dict[str, Any],
    ) -> dict[str, Any]:

        liquidations = market_data.get(
            "liquidations"
        )

        if not isinstance(
            liquidations,
            dict,
        ):
            liquidations = {}

        direction = cls._upper(
            liquidations.get(
                "direction"
            )
        )

        confirmed = cls._bool(
            liquidations.get(
                "confirmed"
            )
        )

        if (
            confirmed
            and direction in {
                "LONG",
                "SHORT",
            }
        ):

            return cls._point(
                point,
                status="CONFIRMED",
                direction=direction,
                score=1.0,
                reason=(
                    "Liquidation data provides "
                    "directional confirmation."
                ),
                evidence=liquidations,
            )

        return cls._point(
            point,
            status="NEUTRAL",
            reason=(
                "No confirmed liquidation "
                "signal."
            ),
            evidence=liquidations,
        )

    # =====================================================
    # POINT 14 - ORDER BOOK
    # =====================================================

    @classmethod
    def _order_book(
        cls,
        point: AnalysisPoint,
        market_data: dict[str, Any],
    ) -> dict[str, Any]:

        order_book = market_data.get(
            "order_book"
        )

        if not isinstance(
            order_book,
            dict,
        ):
            order_book = {}

        direction = cls._upper(
            order_book.get(
                "direction",
                order_book.get(
                    "bias",
                    "",
                ),
            )
        )

        confirmed = cls._bool(
            order_book.get(
                "confirmed"
            )
        )

        if (
            confirmed
            and direction in {
                "LONG",
                "SHORT",
            }
        ):

            return cls._point(
                point,
                status="CONFIRMED",
                direction=direction,
                score=1.0,
                reason=(
                    "Order-book imbalance "
                    "supports direction."
                ),
                evidence=order_book,
            )

        return cls._point(
            point,
            status="NEUTRAL",
            reason=(
                "No confirmed order-book "
                "direction."
            ),
            evidence=order_book,
        )

    # =====================================================
    # POINT 15 - TRADEABILITY
    # =====================================================

    @classmethod
    def _tradeability(
        cls,
        point: AnalysisPoint,
        market_data: dict[str, Any],
        indicators: dict[str, Any],
    ) -> dict[str, Any]:

        tradeability = market_data.get(
            "tradeability"
        )

        if isinstance(
            tradeability,
            dict,
        ):

            valid = cls._bool(
                tradeability.get(
                    "valid",
                    tradeability.get(
                        "confirmed"
                    ),
                )
            )

            if valid:

                return cls._point(
                    point,
                    status="CONFIRMED",
                    score=1.0,
                    reason=(
                        "Market is considered "
                        "tradeable."
                    ),
                    evidence=tradeability,
                )

        volume_ratio = cls._float(
            indicators.get(
                "volume_ratio"
            )
        )

        if volume_ratio >= (
            cls.MIN_VOLUME_RATIO
        ):

            return cls._point(
                point,
                status="CONFIRMED",
                score=1.0,
                reason=(
                    "Volume supports tradeability."
                ),
                evidence={
                    "volume_ratio": volume_ratio,
                },
            )

        return cls._point(
            point,
            status="NEUTRAL",
            reason=(
                "Tradeability has not been "
                "strongly confirmed."
            ),
            evidence={
                "volume_ratio": volume_ratio,
            },
        )

    # =====================================================
    # POINT 16 - NEWS RISK
    # =====================================================

    @classmethod
    def _news_risk(
        cls,
        point: AnalysisPoint,
        market_data: dict[str, Any],
    ) -> dict[str, Any]:

        news = market_data.get(
            "news_risk"
        )

        if not isinstance(
            news,
            dict,
        ):
            news = {}

        risk = cls._upper(
            news.get(
                "risk"
            )
        )

        blocked = cls._bool(
            news.get(
                "blocked"
            )
        )

        if (
            blocked
            or risk in {
                "HIGH",
                "CRITICAL",
            }
        ):

            return cls._point(
                point,
                status="FAILED",
                score=-1.0,
                reason=(
                    "High event/news risk "
                    "detected."
                ),
                evidence=news,
            )

        if risk in {
            "LOW",
            "NONE",
        }:

            return cls._point(
                point,
                status="CONFIRMED",
                score=1.0,
                reason=(
                    "No significant news "
                    "risk detected."
                ),
                evidence=news,
            )

        return cls._point(
            point,
            status="PENDING",
            reason=(
                "News/event risk data "
                "is unavailable."
            ),
            evidence=news,
        )

    # =====================================================
    # POINT 17 - BTC CONTEXT
    # =====================================================

    @classmethod
    def _btc_context(
        cls,
        point: AnalysisPoint,
        market_data: dict[str, Any],
    ) -> dict[str, Any]:

        btc = market_data.get(
            "btc_context"
        )

        if not isinstance(
            btc,
            dict,
        ):
            btc = {}

        direction = cls._upper(
            btc.get(
                "direction",
                btc.get(
                    "bias",
                    "",
                ),
            )
        )

        confirmed = cls._bool(
            btc.get(
                "confirmed"
            )
        )

        if (
            confirmed
            and direction in {
                "LONG",
                "SHORT",
            }
        ):

            return cls._point(
                point,
                status="CONFIRMED",
                direction=direction,
                score=1.0,
                reason=(
                    "BTC market context "
                    "provides direction."
                ),
                evidence=btc,
            )

        return cls._point(
            point,
            status="NEUTRAL",
            reason=(
                "BTC context is not "
                "directionally confirmed."
            ),
            evidence=btc,
        )

    # =====================================================
    # POINT 18 - RELATIVE STRENGTH
    # =====================================================

    @classmethod
    def _relative_strength(
        cls,
        point: AnalysisPoint,
        market_data: dict[str, Any],
    ) -> dict[str, Any]:

        relative = market_data.get(
            "relative_strength"
        )

        if not isinstance(
            relative,
            dict,
        ):
            relative = {}

        direction = cls._upper(
            relative.get(
                "direction",
                relative.get(
                    "bias",
                    "",
                ),
            )
        )

        confirmed = cls._bool(
            relative.get(
                "confirmed"
            )
        )

        if (
            confirmed
            and direction in {
                "LONG",
                "SHORT",
            }
        ):

            return cls._point(
                point,
                status="CONFIRMED",
                direction=direction,
                score=1.0,
                reason=(
                    "Relative strength supports "
                    "the direction."
                ),
                evidence=relative,
            )

        return cls._point(
            point,
            status="NEUTRAL",
            reason=(
                "Relative strength "
                "is not confirmed."
            ),
            evidence=relative,
        )

    # =====================================================
    # POINT 19 - RISK / REWARD
    # =====================================================

    @classmethod
    def _risk_reward(
        cls,
        point: AnalysisPoint,
        market_data: dict[str, Any],
    ) -> dict[str, Any]:

        risk_reward = market_data.get(
            "risk_reward"
        )

        if not isinstance(
            risk_reward,
            dict,
        ):
            risk_reward = {}

        rr = cls._float(
            risk_reward.get(
                "rr",
                risk_reward.get(
                    "risk_reward",
                    0,
                ),
            )
        )

        if rr >= cls.GOOD_RR:

            return cls._point(
                point,
                status="CONFIRMED",
                score=1.0,
                reason=(
                    f"Good risk/reward "
                    f"ratio: {rr:.2f}R."
                ),
                evidence=risk_reward,
            )

        if rr >= cls.MIN_RR:

            return cls._point(
                point,
                status="CONFIRMED",
                score=0.5,
                reason=(
                    f"Acceptable risk/reward "
                    f"ratio: {rr:.2f}R."
                ),
                evidence=risk_reward,
            )

        if rr > 0:

            return cls._point(
                point,
                status="FAILED",
                score=-1.0,
                reason=(
                    f"Risk/reward is too low: "
                    f"{rr:.2f}R."
                ),
                evidence=risk_reward,
            )

        return cls._point(
            point,
            status="PENDING",
            reason=(
                "Risk/reward has not yet "
                "been calculated."
            ),
            evidence=risk_reward,
        )

    # =====================================================
    # POINT 20 - STOP QUALITY
    # =====================================================

    @classmethod
    def _stop_quality(
        cls,
        point: AnalysisPoint,
        market_data: dict[str, Any],
    ) -> dict[str, Any]:

        stop = market_data.get(
            "stop_quality"
        )

        if not isinstance(
            stop,
            dict,
        ):
            stop = {}

        valid = cls._bool(
            stop.get(
                "valid",
                stop.get(
                    "confirmed"
                ),
            )
        )

        if valid:

            return cls._point(
                point,
                status="CONFIRMED",
                score=1.0,
                reason=(
                    "Stop placement is "
                    "structurally valid."
                ),
                evidence=stop,
            )

        if stop:

            return cls._point(
                point,
                status="FAILED",
                score=-1.0,
                reason=(
                    "Stop quality failed."
                ),
                evidence=stop,
            )

        return cls._point(
            point,
            status="PENDING",
            reason=(
                "Stop quality has not "
                "been calculated."
            ),
        )

    # =====================================================
    # POINT 21 - POSITION SIZING
    # =====================================================

    @classmethod
    def _position_sizing(
        cls,
        point: AnalysisPoint,
        market_data: dict[str, Any],
    ) -> dict[str, Any]:

        sizing = market_data.get(
            "position_sizing"
        )

        if not isinstance(
            sizing,
            dict,
        ):
            sizing = {}

        valid = cls._bool(
            sizing.get(
                "valid"
            )
        )

        if valid:

            return cls._point(
                point,
                status="CONFIRMED",
                score=1.0,
                reason=(
                    "Position sizing "
                    "is valid."
                ),
                evidence=sizing,
            )

        return cls._point(
            point,
            status="PENDING",
            reason=(
                "Position sizing gate "
                "is pending."
            ),
            evidence=sizing,
        )

    # =====================================================
    # POINT 22 - PORTFOLIO RISK
    # =====================================================

    @classmethod
    def _portfolio_risk(
        cls,
        point: AnalysisPoint,
        market_data: dict[str, Any],
    ) -> dict[str, Any]:

        portfolio = market_data.get(
            "portfolio_risk"
        )

        if not isinstance(
            portfolio,
            dict,
        ):
            portfolio = {}

        valid = cls._bool(
            portfolio.get(
                "valid"
            )
        )

        blocked = cls._bool(
            portfolio.get(
                "blocked"
            )
        )

        if blocked:

            return cls._point(
                point,
                status="FAILED",
                score=-1.0,
                reason=(
                    "Portfolio risk "
                    "gate blocked."
                ),
                evidence=portfolio,
            )

        if valid:

            return cls._point(
                point,
                status="CONFIRMED",
                score=1.0,
                reason=(
                    "Portfolio risk "
                    "is acceptable."
                ),
                evidence=portfolio,
            )

        return cls._point(
            point,
            status="PENDING",
            reason=(
                "Portfolio risk "
                "gate is pending."
            ),
            evidence=portfolio,
        )

    # =====================================================
    # POINT 23 - EXECUTION QUALITY
    # =====================================================

    @classmethod
    def _execution_quality(
        cls,
        point: AnalysisPoint,
        market_data: dict[str, Any],
    ) -> dict[str, Any]:

        execution = market_data.get(
            "execution_quality"
        )

        if not isinstance(
            execution,
            dict,
        ):
            execution = {}

        valid = cls._bool(
            execution.get(
                "valid"
            )
        )

        if valid:

            return cls._point(
                point,
                status="CONFIRMED",
                score=1.0,
                reason=(
                    "Execution quality "
                    "is acceptable."
                ),
                evidence=execution,
            )

        return cls._point(
            point,
            status="PENDING",
            reason=(
                "Execution quality "
                "gate is pending."
            ),
            evidence=execution,
        )

    # =====================================================
    # POINT 24 - SIGNAL FRESHNESS
    # =====================================================

    @classmethod
    def _signal_freshness(
        cls,
        point: AnalysisPoint,
        market_data: dict[str, Any],
    ) -> dict[str, Any]:

        freshness = market_data.get(
            "signal_freshness"
        )

        if not isinstance(
            freshness,
            dict,
        ):
            freshness = {}

        valid = cls._bool(
            freshness.get(
                "valid",
                freshness.get(
                    "fresh"
                ),
            )
        )

        if valid:

            return cls._point(
                point,
                status="CONFIRMED",
                score=1.0,
                reason=(
                    "Signal data is fresh."
                ),
                evidence=freshness,
            )

        return cls._point(
            point,
            status="PENDING",
            reason=(
                "Signal freshness "
                "has not been confirmed."
            ),
            evidence=freshness,
        )

    # =====================================================
    # AGGREGATE POINTS
    # =====================================================

    @classmethod
    def _aggregate(
        cls,
        result: dict[str, Any],
    ) -> dict[str, Any]:

        points = result.get(
            "points",
            {}
        )

        long_evidence = 0.0
        short_evidence = 0.0

        market_count = 0
        risk_count = 0

        critical_failures: list[str] = []

        for point in points.values():

            if not isinstance(
                point,
                dict,
            ):
                continue

            category = cls._lower(
                point.get(
                    "category"
                )
            )

            status = cls._upper(
                point.get(
                    "status"
                )
            )

            direction = cls._upper(
                point.get(
                    "direction"
                )
            )

            score = cls._float(
                point.get(
                    "score"
                )
            )

            if category == "market":

                if status == "CONFIRMED":

                    market_count += 1

            elif category == "risk":

                if status == "CONFIRMED":

                    risk_count += 1

            if direction == "LONG":

                long_evidence += max(
                    0.0,
                    score,
                )

            elif direction == "SHORT":

                short_evidence += max(
                    0.0,
                    score,
                )

            if status == "FAILED":

                critical_failures.append(
                    str(
                        point.get(
                            "name",
                            "Unknown",
                        )
                    )
                )

        result[
            "market_confirmation_count"
        ] = market_count

        result[
            "risk_gate_count"
        ] = risk_count

        result[
            "long_evidence"
        ] = round(
            long_evidence,
            4,
        )

        result[
            "short_evidence"
        ] = round(
            short_evidence,
            4,
        )

        result[
            "critical_failures"
        ] = critical_failures

        return result

    # =====================================================
    # MAIN ANALYSIS
    # =====================================================

    async def analyze(
        self,
        *,
        symbol: str,
        market: str,
        market_data: dict[str, Any] | None = None,
        direction: str = "NEUTRAL",
    ) -> dict[str, Any]:

        result = self.empty_result(
            symbol=symbol,
            market=market,
            direction=direction,
        )

        data = (
            market_data
            if isinstance(
                market_data,
                dict,
            )
            else {}
        )

        result[
            "market_data_received"
        ] = bool(data)

        result[
            "market_data_keys"
        ] = sorted(
            data.keys()
        )

        # -------------------------------------------------
        # EXTRACT CORE DATA
        # -------------------------------------------------

        indicators = (
            cls._extract_indicators(
                data
            )
            if hasattr(
                cls,
                "_extract_indicators",
            )
            else {}
        )

        structure = (
            cls._extract_structure(
                data
            )
        )

        price = cls._float(
            indicators.get(
                "price",
                data.get(
                    "price"
                ),
            )
        )

        support, resistance = (
            cls._extract_levels(
                data,
                structure,
            )
        )

        # -------------------------------------------------
        # SUPPORT / RESISTANCE TOUCH
        # -------------------------------------------------

        support_touches = cls._float(
            structure.get(
                "support_touches",
                structure.get(
                    "support_touch_count",
                    0,
                ),
            )
        )

        resistance_touches = cls._float(
            structure.get(
                "resistance_touches",
                structure.get(
                    "resistance_touch_count",
                    0,
                ),
            )
        )

        if (
            support_touches <= 0
            and support > 0
        ):

            lows = structure.get(
                "recent_lows",
                structure.get(
                    "lows",
                    [],
                ),
            )

            support_touches = (
                cls._touch_count(
                    lows,
                    support,
                    cls.SUPPORT_TOUCH_TOLERANCE,
                )
            )

        if (
            resistance_touches <= 0
            and resistance > 0
        ):

            highs = structure.get(
                "recent_highs",
                structure.get(
                    "highs",
                    [],
                ),
            )

            resistance_touches = (
                cls._touch_count(
                    highs,
                    resistance,
                    cls.RESISTANCE_TOUCH_TOLERANCE,
                )
            )

        structure = {
            **structure,
            "support": support,
            "resistance": resistance,
            "support_touches": int(
                support_touches
            ),
            "resistance_touches": int(
                resistance_touches
            ),
        }

        # -------------------------------------------------
        # SETUP
        # -------------------------------------------------

        setup = cls._determine_setup(
            direction=(
                cls._upper(
                    direction
                )
            ),
            structure=structure,
            indicators=indicators,
            support=support,
            resistance=resistance,
            current_price=price,
            market_data=data,
        )

        result[
            "setup_type"
        ] = setup.get(
            "type",
            "NONE",
        )

        result[
            "setup_priority"
        ] = setup.get(
            "priority",
            "LOW",
        )

        result[
            "setup"
        ] = setup

        result[
            "support"
        ] = support

        result[
            "resistance"
        ] = resistance

        result[
            "support_touches"
        ] = int(
            support_touches
        )

        result[
            "resistance_touches"
        ] = int(
            resistance_touches
        )

        # -------------------------------------------------
        # POINT 1
        # -------------------------------------------------

        result["points"]["1"] = (
            cls._market_regime(
                cls.MARKET_POINTS[0],
                indicators,
            )
        )

        # -------------------------------------------------
        # POINT 2
        # -------------------------------------------------

        result["points"]["2"] = (
            cls._market_structure(
                cls.MARKET_POINTS[1],
                structure,
            )
        )

        # -------------------------------------------------
        # POINT 3
        # -------------------------------------------------

        result["points"]["3"] = (
            cls._mtf_confirmation(
                cls.MARKET_POINTS[2],
                data,
            )
        )

        # -------------------------------------------------
        # POINT 4
        # -------------------------------------------------

        result["points"]["4"] = (
            cls._entry_location(
                cls.MARKET_POINTS[3],
                setup,
            )
        )

        # -------------------------------------------------
        # POINT 5
        # -------------------------------------------------

        result["points"]["5"] = (
            cls._liquidity_sweep(
                cls.MARKET_POINTS[4],
                data,
            )
        )

        # -------------------------------------------------
        # POINT 6
        # -------------------------------------------------

        result["points"]["6"] = (
            cls._vwap(
                cls.MARKET_POINTS[5],
                indicators,
            )
        )

        # -------------------------------------------------
        # POINT 7
        # -------------------------------------------------

        result["points"]["7"] = (
            cls._atr(
                cls.MARKET_POINTS[6],
                indicators,
            )
        )

        # -------------------------------------------------
        # POINT 8
        # -------------------------------------------------

        result["points"]["8"] = (
            cls._momentum(
                cls.MARKET_POINTS[7],
                indicators,
            )
        )

        # -------------------------------------------------
        # POINT 9
        # -------------------------------------------------

        result["points"]["9"] = (
            cls._divergence(
                cls.MARKET_POINTS[8],
                data,
            )
        )

        # -------------------------------------------------
        # POINT 10
        # -------------------------------------------------

        result["points"]["10"] = (
            cls._breakout(
                cls.MARKET_POINTS[9],
                indicators,
            )
        )

        # -------------------------------------------------
        # POINT 11
        # -------------------------------------------------

        result["points"]["11"] = (
            cls._retest(
                cls.MARKET_POINTS[10],
                data,
            )
        )

        # -------------------------------------------------
        # POINT 12
        # -------------------------------------------------

        result["points"]["12"] = (
            cls._derivatives(
                cls.MARKET_POINTS[11],
                data,
            )
        )

        # -------------------------------------------------
        # POINT 13
        # -------------------------------------------------

        result["points"]["13"] = (
            cls._liquidations(
                cls.MARKET_POINTS[12],
                data,
            )
        )

        # -------------------------------------------------
        # POINT 14
        # -------------------------------------------------

        result["points"]["14"] = (
            cls._order_book(
                cls.MARKET_POINTS[13],
                data,
            )
        )

        # -------------------------------------------------
        # POINT 15
        # -------------------------------------------------

        result["points"]["15"] = (
            cls._tradeability(
                cls.MARKET_POINTS[14],
                data,
                indicators,
            )
        )

        # -------------------------------------------------
        # POINT 16
        # -------------------------------------------------

        result["points"]["16"] = (
            cls._news_risk(
                cls.MARKET_POINTS[15],
                data,
            )
        )

        # -------------------------------------------------
        # POINT 17
        # -------------------------------------------------

        result["points"]["17"] = (
            cls._btc_context(
                cls.MARKET_POINTS[16],
                data,
            )
        )

        # -------------------------------------------------
        # POINT 18
        # -------------------------------------------------

        result["points"]["18"] = (
            cls._relative_strength(
                cls.MARKET_POINTS[17],
                data,
            )
        )

        # -------------------------------------------------
        # POINT 19
        # -------------------------------------------------

        result["points"]["19"] = (
            cls._risk_reward(
                cls.MARKET_POINTS[18],
                data,
            )
        )

        # -------------------------------------------------
        # POINT 20
        # -------------------------------------------------

        result["points"]["20"] = (
            cls._stop_quality(
                cls.MARKET_POINTS[19],
                data,
            )
        )

        # -------------------------------------------------
        # POINT 21
        # -------------------------------------------------

        result["points"]["21"] = (
            cls._position_sizing(
                cls.RISK_POINTS[0],
                data,
            )
        )

        # -------------------------------------------------
        # POINT 22
        # -------------------------------------------------

        result["points"]["22"] = (
            cls._portfolio_risk(
                cls.RISK_POINTS[1],
                data,
            )
        )

        # -------------------------------------------------
        # POINT 23
        # -------------------------------------------------

        result["points"]["23"] = (
            cls._execution_quality(
                cls.RISK_POINTS[2],
                data,
            )
        )

        # -------------------------------------------------
        # POINT 24
        # -------------------------------------------------

        result["points"]["24"] = (
            cls._signal_freshness(
                cls.RISK_POINTS[3],
                data,
            )
        )

        # -------------------------------------------------
        # AGGREGATION
        # -------------------------------------------------

        result = cls._aggregate(
            result
        )

        # -------------------------------------------------
        # SETUP-SPECIFIC PRIORITY
        # -------------------------------------------------

        if (
            result.get(
                "setup_type"
            )
            == "SUPPORT_BOUNCE"
        ):

            result[
                "setup_message"
            ] = (
                "Potential support bounce: "
                "repeated support interaction "
                "with bullish reaction."
            )

        elif (
            result.get(
                "setup_type"
            )
            == "RESISTANCE_REJECTION"
        ):

            result[
                "setup_message"
            ] = (
                "Potential resistance rejection: "
                "repeated resistance interaction "
                "with bearish reaction."
            )

        else:

            result[
                "setup_message"
            ] = (
                "No high-priority support/"
                "resistance setup confirmed."
            )

        # -------------------------------------------------
        # FINAL STATUS
        # -------------------------------------------------

        if result[
            "critical_failures"
        ]:

            result[
                "status"
            ] = "critical_failure"

        elif (
            result[
                "market_confirmation_count"
            ]
            > 0
        ):

            result[
                "status"
            ] = "analysis_complete"

        else:

            result[
                "status"
            ] = "insufficient_evidence"

        return result


# =========================================================
# SHARED INSTANCE
# =========================================================

analysis_engine = AnalysisEngine()


# =========================================================
# EXPORTS
# =========================================================

__all__ = [
    "AnalysisPoint",
    "AnalysisEngine",
    "analysis_engine",
]
