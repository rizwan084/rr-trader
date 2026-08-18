from __future__ import annotations

from typing import Any


class ConfidenceEngine:
    """
    RR Trader Confidence Engine.

    Converts analysis factors into one normalized
    0-100 confidence score.

    This engine does not independently create a LONG
    or SHORT signal. It evaluates the evidence supplied
    by the analysis layer.
    """

    DEFAULT_WEIGHTS = {
        "trend": 0.15,
        "structure": 0.10,
        "momentum": 0.10,
        "volume": 0.10,
        "support_resistance": 0.10,
        "multi_timeframe": 0.15,
        "liquidity": 0.05,
        "derivatives": 0.10,
        "risk_reward": 0.10,
        "market_regime": 0.05,
    }

    def __init__(
        self,
        minimum_confidence: float = 85.0,
        weights: dict[str, float] | None = None,
    ) -> None:

        self.minimum_confidence = float(
            minimum_confidence
        )

        self.weights = (
            weights.copy()
            if isinstance(weights, dict)
            else self.DEFAULT_WEIGHTS.copy()
        )

        self._normalize_weights()

    # =====================================================
    # SAFE SCORE
    # =====================================================

    @staticmethod
    def _score(
        value: Any,
    ) -> float:

        try:
            score = float(
                value
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
    # NORMALIZE WEIGHTS
    # =====================================================

    def _normalize_weights(
        self,
    ) -> None:

        cleaned: dict[
            str,
            float,
        ] = {}

        for key, value in (
            self.weights.items()
        ):

            try:
                numeric = float(
                    value
                )
            except (
                TypeError,
                ValueError,
            ):
                numeric = 0.0

            cleaned[key] = max(
                0.0,
                numeric,
            )

        total = sum(
            cleaned.values()
        )

        if total <= 0:

            cleaned = (
                self.DEFAULT_WEIGHTS.copy()
            )

            total = sum(
                cleaned.values()
            )

        self.weights = {
            key: value / total
            for key, value
            in cleaned.items()
        }

    # =====================================================
    # CALCULATE
    # =====================================================

    def calculate(
        self,
        analysis: dict[str, Any],
    ) -> float:

        if not isinstance(
            analysis,
            dict,
        ):
            return 0.0

        weighted_score = 0.0

        for factor, weight in (
            self.weights.items()
        ):

            score = self._score(
                analysis.get(
                    factor,
                    0.0,
                )
            )

            weighted_score += (
                score * weight
            )

        return round(
            max(
                0.0,
                min(
                    100.0,
                    weighted_score,
                ),
            ),
            2,
        )

    # =====================================================
    # EVALUATE
    # =====================================================

    def evaluate(
        self,
        analysis: dict[str, Any],
    ) -> dict[str, Any]:

        confidence = self.calculate(
            analysis
        )

        passed = (
            confidence
            >= self.minimum_confidence
        )

        return {
            "success": True,
            "confidence": confidence,
            "minimum_confidence":
                self.minimum_confidence,
            "passed": passed,
            "decision": (
                "QUALIFIED"
                if passed
                else "REJECTED"
            ),
            "weights": self.weights.copy(),
        }

    # =====================================================
    # FACTOR BREAKDOWN
    # =====================================================

    def breakdown(
        self,
        analysis: dict[str, Any],
    ) -> dict[str, Any]:

        if not isinstance(
            analysis,
            dict,
        ):

            return {
                "success": False,
                "factors": {},
            }

        factors: dict[
            str,
            dict[str, float],
        ] = {}

        for factor, weight in (
            self.weights.items()
        ):

            raw_score = self._score(
                analysis.get(
                    factor,
                    0.0,
                )
            )

            contribution = (
                raw_score
                * weight
            )

            factors[factor] = {
                "score": round(
                    raw_score,
                    2,
                ),
                "weight": round(
                    weight,
                    6,
                ),
                "contribution": round(
                    contribution,
                    2,
                ),
            }

        return {
            "success": True,
            "factors": factors,
            "total_confidence":
                self.calculate(
                    analysis
                ),
        }

    # =====================================================
    # STATUS
    # =====================================================

    def status(
        self,
    ) -> dict[str, Any]:

        return {
            "enabled": True,
            "minimum_confidence":
                self.minimum_confidence,
            "weights":
                self.weights.copy(),
        }


# =========================================================
# SHARED INSTANCE
# =========================================================

confidence_engine = ConfidenceEngine()


__all__ = [
    "ConfidenceEngine",
    "confidence_engine",
]
