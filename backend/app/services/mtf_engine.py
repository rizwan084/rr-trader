from __future__ import annotations

from typing import Any


class MTFEngine:
    """
    RR Trader Multi-Timeframe Confirmation Engine.

    Core timeframes:
        15m
        1h
        4h

    Rules:
    - 15m = entry / local confirmation
    - 1h  = primary trend
    - 4h  = higher-timeframe regime

    A fully aligned setup requires all three
    timeframes to point in the same direction.
    """

    CORE_TIMEFRAMES = (
        "15m",
        "1h",
        "4h",
    )

    WEIGHTS = {
        "15m": 0.30,
        "1h": 0.35,
        "4h": 0.35,
    }

    # =====================================================
    # HELPERS
    # =====================================================

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

    @staticmethod
    def _score(
        value: Any,
    ) -> float:

        try:
            score = float(
                value
                or 0
            )

        except (
            TypeError,
            ValueError,
        ):
            return 0.0

        return max(
            0.0,
            min(
                100.0,
                score,
            ),
        )

    # =====================================================
    # NORMALIZE TIMEFRAME RESULT
    # =====================================================

    def normalize_timeframe(
        self,
        timeframe: str,
        data: dict[str, Any] | None,
    ) -> dict[str, Any]:

        data = (
            data
            if isinstance(
                data,
                dict,
            )
            else {}
        )

        direction = self._direction(
            data.get(
                "direction",
                data.get(
                    "signal",
                    "NEUTRAL",
                ),
            )
        )

        confidence = self._score(
            data.get(
                "confidence",
                data.get(
                    "score",
                    0,
                ),
            )
        )

        return {
            "timeframe": timeframe,
            "direction": direction,
            "confidence": confidence,
            "available": bool(
                data
            ),
        }

    # =====================================================
    # ANALYZE MTF
    # =====================================================

    def analyze(
        self,
        timeframes: dict[
            str,
            dict[str, Any],
        ],
    ) -> dict[str, Any]:

        normalized = {}

        for timeframe in (
            self.CORE_TIMEFRAMES
        ):

            normalized[
                timeframe
            ] = self.normalize_timeframe(
                timeframe,
                timeframes.get(
                    timeframe,
                    {},
                ),
            )

        directions = {
            timeframe:
                item["direction"]
            for timeframe, item
            in normalized.items()
        }

        bullish_count = sum(
            1
            for direction
            in directions.values()
            if direction == "LONG"
        )

        bearish_count = sum(
            1
            for direction
            in directions.values()
            if direction == "SHORT"
        )

        neutral_count = sum(
            1
            for direction
            in directions.values()
            if direction == "NEUTRAL"
        )

        # -------------------------------------------------
        # Strict alignment
        # -------------------------------------------------

        all_long = (
            bullish_count == 3
        )

        all_short = (
            bearish_count == 3
        )

        aligned = (
            all_long
            or all_short
        )

        if all_long:

            direction = "LONG"

        elif all_short:

            direction = "SHORT"

        elif bullish_count > bearish_count:

            direction = "LONG"

        elif bearish_count > bullish_count:

            direction = "SHORT"

        else:

            direction = "NEUTRAL"

        # -------------------------------------------------
        # Agreement ratio
        # -------------------------------------------------

        strongest_count = max(
            bullish_count,
            bearish_count,
        )

        agreement_ratio = (
            strongest_count
            / 3.0
        )

        # -------------------------------------------------
        # Weighted confidence
        # -------------------------------------------------

        weighted_score = 0.0

        for timeframe, weight in (
            self.WEIGHTS.items()
        ):

            item = normalized[
                timeframe
            ]

            if (
                direction
                == item["direction"]
            ):

                weighted_score += (
                    item["confidence"]
                    * weight
                )

        # -------------------------------------------------
        # Conflict rules
        # -------------------------------------------------

        conflict = (
            neutral_count > 0
            or (
                bullish_count > 0
                and bearish_count > 0
            )
        )

        # 4H is the regime anchor.
        four_hour_direction = (
            normalized[
                "4h"
            ]["direction"]
        )

        four_hour_confirms = (
            four_hour_direction
            == direction
            and direction
            in {
                "LONG",
                "SHORT",
            }
        )

        # -------------------------------------------------
        # Status
        # -------------------------------------------------

        if aligned:

            status = "ALIGNED"

        elif conflict:

            status = "CONFLICT"

        else:

            status = "PARTIAL"

        # -------------------------------------------------
        # Strict publish gate
        # -------------------------------------------------

        publishable_mtf = (
            aligned
            and four_hour_confirms
        )

        return {
            "core_timeframes": list(
                self.CORE_TIMEFRAMES
            ),
            "15m":
                normalized["15m"],
            "1h":
                normalized["1h"],
            "4h":
                normalized["4h"],
            "direction":
                direction,
            "aligned":
                aligned,
            "status":
                status,
            "agreement_ratio":
                round(
                    agreement_ratio,
                    4,
                ),
            "weighted_confidence":
                round(
                    weighted_score,
                    2,
                ),
            "bullish_count":
                bullish_count,
            "bearish_count":
                bearish_count,
            "neutral_count":
                neutral_count,
            "4h_confirms":
                four_hour_confirms,
            "publishable_mtf":
                publishable_mtf,
        }

    # =====================================================
    # HARD GATE
    # =====================================================

    def passes_strict_gate(
        self,
        mtf_result: dict[str, Any],
    ) -> bool:

        if not isinstance(
            mtf_result,
            dict,
        ):
            return False

        return bool(
            mtf_result.get(
                "publishable_mtf",
                False,
            )
        )


mtf_engine = MTFEngine()


__all__ = [
    "MTFEngine",
    "mtf_engine",
]
