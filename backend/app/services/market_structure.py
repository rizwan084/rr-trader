from __future__ import annotations

from typing import Any


class MarketStructureEngine:
    """
    RR Trader market-structure engine.

    Detects:
    - Higher High
    - Higher Low
    - Lower High
    - Lower Low
    - Bullish / Bearish / Neutral structure
    - Break of structure proxy
    - Local support / resistance

    This engine is deterministic.
    It does not use AI to decide structure.
    """

    # =====================================================
    # SAFE FLOAT
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

    # =====================================================
    # SWING POINTS
    # =====================================================

    @classmethod
    def swing_points(
        cls,
        highs: list[float],
        lows: list[float],
        window: int = 2,
    ) -> dict[str, list[float]]:

        if len(highs) < (
            window * 2 + 1
        ):
            return {
                "swing_highs": [],
                "swing_lows": [],
            }

        swing_highs: list[
            float
        ] = []

        swing_lows: list[
            float
        ] = []

        for index in range(
            window,
            len(highs) - window,
        ):

            current_high = (
                highs[index]
            )

            current_low = (
                lows[index]
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
                    left_highs
                    + right_highs
                )
            ):
                swing_highs.append(
                    current_high
                )

            if (
                current_low
                <= min(
                    left_lows
                    + right_lows
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
    # STRUCTURE DIRECTION
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
            swing_highs[-2]
        )

        current_high = (
            swing_highs[-1]
        )

        previous_low = (
            swing_lows[-2]
        )

        current_low = (
            swing_lows[-1]
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
            }

        current_close = (
            closes[-1]
        )

        latest_high = (
            swing_highs[-1]
            if swing_highs
            else 0.0
        )

        latest_low = (
            swing_lows[-1]
            if swing_lows
            else 0.0
        )

        if (
            latest_high > 0
            and current_close
            > latest_high
        ):

            return {
                "direction": "LONG",
                "break": True,
                "level": latest_high,
                "type": "BOS_UP",
            }

        if (
            latest_low > 0
            and current_close
            < latest_low
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
    # SUPPORT / RESISTANCE
    # =====================================================

    @classmethod
    def support_resistance(
        cls,
        highs: list[float],
        lows: list[float],
        current_price: float,
    ) -> dict[str, Any]:

        if not highs or not lows:

            return {
                "support": 0.0,
                "resistance": 0.0,
                "position_percent": 50.0,
                "location": "UNKNOWN",
            }

        support = min(
            lows[-20:]
        )

        resistance = max(
            highs[-20:]
        )

        if resistance <= support:

            return {
                "support": support,
                "resistance": resistance,
                "position_percent": 50.0,
                "location": "RANGE",
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
        }

    # =====================================================
    # COMPLETE STRUCTURE
    # =====================================================

    @classmethod
    def analyze(
        cls,
        highs: list[float],
        lows: list[float],
        closes: list[float],
        window: int = 2,
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

        swings = cls.swing_points(
            highs=highs,
            lows=lows,
            window=window,
        )

        structure = cls.classify_structure(
            swing_highs=(
                swings[
                    "swing_highs"
                ]
            ),
            swing_lows=(
                swings[
                    "swing_lows"
                ]
            ),
        )

        bos = cls.break_of_structure(
            closes=closes,
            swing_highs=(
                swings[
                    "swing_highs"
                ]
            ),
            swing_lows=(
                swings[
                    "swing_lows"
                ]
            ),
        )

        current_price = (
            cls._float(
                closes[-1]
            )
        )

        sr = cls.support_resistance(
            highs=highs,
            lows=lows,
            current_price=current_price,
        )

        return {
            "success": True,
            "direction": structure[
                "direction"
            ],
            "structure": structure[
                "structure"
            ],
            "swing_points": swings,
            "structure_details": structure,
            "break_of_structure": bos,
            "support_resistance": sr,
        }


market_structure_engine = (
    MarketStructureEngine()
)


__all__ = [
    "MarketStructureEngine",
    "market_structure_engine",
]
