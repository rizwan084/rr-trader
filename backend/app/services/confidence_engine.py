from __future__ import annotations

from typing import Any


class ConfidenceEngine:
    """
    RR Trader Confidence Engine v2.

    Scores the actual evidence available from:
    - trend
    - structure
    - momentum
    - volume
    - support/resistance
    - multi-timeframe alignment
    - liquidity/order book
    - derivatives
    - risk/reward
    - market regime

    The engine does NOT force a trade.
    Missing evidence stays neutral.
    Conflicting evidence reduces confidence.
    """

    DEFAULT_WEIGHTS = {
        "trend": 0.12,
        "structure": 0.10,
        "momentum": 0.08,
        "volume": 0.08,
        "support_resistance": 0.08,
        "multi_timeframe": 0.16,
        "liquidity": 0.08,
        "derivatives": 0.10,
        "risk_reward": 0.10,
        "market_regime": 0.10,
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
    # HELPERS
    # =====================================================

    @staticmethod
    def _clamp(
        value: Any,
        low: float = 0.0,
        high: float = 100.0,
    ) -> float:

        try:
            value = float(value)
        except (
            TypeError,
            ValueError,
        ):
            return low

        return max(
            low,
            min(
                high,
                value,
            ),
        )

    @staticmethod
    def _direction(
        value: Any,
    ) -> str:

        direction = str(
            value or "NEUTRAL"
        ).upper().strip()

        if direction not in {
            "LONG",
            "SHORT",
            "NEUTRAL",
        }:
            return "NEUTRAL"

        return direction

    @staticmethod
    def _normalize_text(
        value: Any,
    ) -> str:

        return str(
            value or ""
        ).upper().strip()

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
            for key, value in cleaned.items()
        }

    # =====================================================
    # FACTOR SCORING
    # =====================================================

    def _directional_score(
        self,
        direction: str,
        evidence_direction: str,
        score: float,
    ) -> float:

        if direction == "NEUTRAL":
            return 0.0

        evidence_direction = (
            self._direction(
                evidence_direction
            )
        )

        score = self._clamp(
            score
        )

        if evidence_direction == direction:
            return score

        if evidence_direction == "NEUTRAL":
            return score * 0.35

        return 0.0

    def _trend_score(
        self,
        direction: str,
        analysis: dict[str, Any],
    ) -> float:

        tf = analysis.get(
            "timeframes",
            {},
        )

        if not isinstance(
            tf,
            dict,
        ):
            return 0.0

        one_hour = tf.get(
            "1h",
            {},
        )

        if not isinstance(
            one_hour,
            dict,
        ):
            return 0.0

        return self._directional_score(
            direction,
            one_hour.get(
                "direction"
            ),
            one_hour.get(
                "confidence",
                0,
            ),
        )

    def _structure_score(
        self,
        direction: str,
        analysis: dict[str, Any],
    ) -> float:

        tf = analysis.get(
            "timeframes",
            {},
        )

        if not isinstance(
            tf,
            dict,
        ):
            return 0.0

        structure_values = []

        for timeframe in (
            "15m",
            "1h",
            "4h",
        ):

            item = tf.get(
                timeframe,
                {},
            )

            if not isinstance(
                item,
                dict,
            ):
                continue

            structure = item.get(
                "structure",
                {},
            )

            if not isinstance(
                structure,
                dict,
            ):
                continue

            structure_direction = (
                structure.get(
                    "direction",
                    "NEUTRAL",
                )
            )

            strength = 0.0

            details = structure.get(
                "structure_details",
                {},
            )

            if isinstance(
                details,
                dict,
            ):

                positive = (
                    int(
                        bool(
                            details.get(
                                "higher_high",
                                False,
                            )
                        )
                    )
                    + int(
                        bool(
                            details.get(
                                "higher_low",
                                False,
                            )
                        )
                    )
                )

                negative = (
                    int(
                        bool(
                            details.get(
                                "lower_high",
                                False,
                            )
                        )
                    )
                    + int(
                        bool(
                            details.get(
                                "lower_low",
                                False,
                            )
                        )
                    )
                )

                strength = min(
                    100.0,
                    max(
                        positive,
                        negative,
                    )
                    * 25.0,
                )

            directional = (
                self._directional_score(
                    direction,
                    structure_direction,
                    strength,
                )
            )

            structure_values.append(
                directional
            )

        if not structure_values:
            return 0.0

        return sum(
            structure_values
        ) / len(
            structure_values
        )

    def _momentum_score(
        self,
        direction: str,
        analysis: dict[str, Any],
    ) -> float:

        tf = analysis.get(
            "timeframes",
            {},
        )

        if not isinstance(
            tf,
            dict,
        ):
            return 0.0

        item = tf.get(
            "15m",
            {},
        )

        if not isinstance(
            item,
            dict,
        ):
            return 0.0

        indicators = item.get(
            "indicators",
            {},
        )

        if not isinstance(
            indicators,
            dict,
        ):
            return 0.0

        momentum = indicators.get(
            "momentum",
            0,
        )

        try:
            momentum = float(
                momentum
            )
        except (
            TypeError,
            ValueError,
        ):
            return 0.0

        if direction == "LONG":
            return self._clamp(
                50.0 + (
                    momentum * 10.0
                )
            )

        if direction == "SHORT":
            return self._clamp(
                50.0 - (
                    momentum * 10.0
                )
            )

        return 0.0

    def _volume_score(
        self,
        direction: str,
        analysis: dict[str, Any],
    ) -> float:

        del direction

        tf = analysis.get(
            "timeframes",
            {},
        )

        if not isinstance(
            tf,
            dict,
        ):
            return 0.0

        values = []

        for timeframe in (
            "15m",
            "1h",
            "4h",
        ):

            item = tf.get(
                timeframe,
                {},
            )

            if not isinstance(
                item,
                dict,
            ):
                continue

            indicators = item.get(
                "indicators",
                {},
            )

            if not isinstance(
                indicators,
                dict,
            ):
                continue

            ratio = indicators.get(
                "volume_ratio",
                0,
            )

            try:
                ratio = float(
                    ratio
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

            if ratio <= 0:
                continue

            # 1.0x = normal
            # 2.0x+ = strong
            score = self._clamp(
                ratio * 50.0
            )

            values.append(
                score
            )

        if not values:
            return 0.0

        return sum(
            values
        ) / len(
            values
        )

    def _support_resistance_score(
        self,
        direction: str,
        analysis: dict[str, Any],
    ) -> float:

        tf = analysis.get(
            "timeframes",
            {},
        )

        if not isinstance(
            tf,
            dict,
        ):
            return 0.0

        item = tf.get(
            "15m",
            {},
        )

        if not isinstance(
            item,
            dict,
        ):
            return 0.0

        structure = item.get(
            "structure",
            {},
        )

        if not isinstance(
            structure,
            dict,
        ):
            return 0.0

        sr = structure.get(
            "support_resistance",
            {},
        )

        if not isinstance(
            sr,
            dict,
        ):
            return 0.0

        location = self._normalize_text(
            sr.get(
                "location"
            )
        )

        if direction == "LONG":

            if location == "NEAR_SUPPORT":
                return 95.0

            if location == "MID_RANGE":
                return 55.0

            if location == "NEAR_RESISTANCE":
                return 20.0

        elif direction == "SHORT":

            if location == "NEAR_RESISTANCE":
                return 95.0

            if location == "MID_RANGE":
                return 55.0

            if location == "NEAR_SUPPORT":
                return 20.0

        return 0.0

    def _mtf_score(
        self,
        direction: str,
        analysis: dict[str, Any],
    ) -> float:

        mtf = analysis.get(
            "multi_timeframe",
            {},
        )

        if not isinstance(
            mtf,
            dict,
        ):
            return 0.0

        mtf_direction = (
            self._direction(
                mtf.get(
                    "direction"
                )
            )
        )

        weighted = self._clamp(
            mtf.get(
                "weighted_confidence",
                0,
            )
        )

        agreement = self._clamp(
            mtf.get(
                "agreement_ratio",
                0,
            ),
            0,
            1,
        )

        aligned = bool(
            mtf.get(
                "aligned",
                False,
            )
        )

        base = (
            weighted
            * agreement
        )

        if aligned:
            base += 20.0

        return self._directional_score(
            direction,
            mtf_direction,
            self._clamp(
                base
            ),
        )

    def _liquidity_score(
        self,
        direction: str,
        analysis: dict[str, Any],
    ) -> float:

        order_book = analysis.get(
            "order_book",
            {},
        )

        if not isinstance(
            order_book,
            dict,
        ):
            return 0.0

        status = self._normalize_text(
            order_book.get(
                "status"
            )
        )

        if status != "AVAILABLE":
            return 0.0

        score = self._clamp(
            order_book.get(
                "score",
                0,
            )
        )

        evidence_direction = (
            order_book.get(
                "direction",
                "NEUTRAL",
            )
        )

        return self._directional_score(
            direction,
            evidence_direction,
            score,
        )

    def _derivatives_score(
        self,
        direction: str,
        analysis: dict[str, Any],
    ) -> float:

        derivatives = analysis.get(
            "derivatives",
            {},
        )

        if not isinstance(
            derivatives,
            dict,
        ):
            return 0.0

        if (
            self._normalize_text(
                derivatives.get(
                    "status"
                )
            )
            != "AVAILABLE"
        ):
            return 0.0

        return self._directional_score(
            direction,
            derivatives.get(
                "direction",
                "NEUTRAL",
            ),
            derivatives.get(
                "score",
                0,
            ),
        )

    def _risk_reward_score(
        self,
        direction: str,
        analysis: dict[str, Any],
    ) -> float:

        del direction

        rr = analysis.get(
            "risk_reward",
            0,
        )

        try:
            rr = float(
                rr
            )
        except (
            TypeError,
            ValueError,
        ):
            return 0.0

        if rr <= 0:
            return 0.0

        if rr < 1.0:
            return 20.0

        if rr < 1.5:
            return 40.0

        if rr < 2.0:
            return 60.0

        if rr < 2.5:
            return 75.0

        if rr < 3.0:
            return 90.0

        return 100.0

    def _regime_score(
        self,
        direction: str,
        analysis: dict[str, Any],
    ) -> float:

        tf = analysis.get(
            "timeframes",
            {},
        )

        if not isinstance(
            tf,
            dict,
        ):
            return 0.0

        four_hour = tf.get(
            "4h",
            {},
        )

        if not isinstance(
            four_hour,
            dict,
        ):
            return 0.0

        regime_direction = (
            four_hour.get(
                "direction",
                "NEUTRAL",
            )
        )

        confidence = self._clamp(
            four_hour.get(
                "confidence",
                0,
            )
        )

        return self._directional_score(
            direction,
            regime_direction,
            confidence,
        )

    # =====================================================
    # MAIN CALCULATION
    # =====================================================

    def calculate(
        self,
        analysis: dict[str, Any],
        *,
        direction: str | None = None,
    ) -> dict[str, Any]:

        if not isinstance(
            analysis,
            dict,
        ):

            return {
                "success": False,
                "confidence": 0.0,
                "decision": "NO_TRADE",
            }

        signal_direction = (
            self._direction(
                direction
                or analysis.get(
                    "direction",
                    "NEUTRAL",
                )
            )
        )

        if signal_direction == "NEUTRAL":

            return {
                "success": True,
                "confidence": 0.0,
                "decision": "NO_TRADE",
                "direction": "NEUTRAL",
                "factors": {},
            }

        factors = {

            "trend":
                self._trend_score(
                    signal_direction,
                    analysis,
                ),

            "structure":
                self._structure_score(
                    signal_direction,
                    analysis,
                ),

            "momentum":
                self._momentum_score(
                    signal_direction,
                    analysis,
                ),

            "volume":
                self._volume_score(
                    signal_direction,
                    analysis,
                ),

            "support_resistance":
                self._support_resistance_score(
                    signal_direction,
                    analysis,
                ),

            "multi_timeframe":
                self._mtf_score(
                    signal_direction,
                    analysis,
                ),

            "liquidity":
                self._liquidity_score(
                    signal_direction,
                    analysis,
                ),

            "derivatives":
                self._derivatives_score(
                    signal_direction,
                    analysis,
                ),

            "risk_reward":
                self._risk_reward_score(
                    signal_direction,
                    analysis,
                ),

            "market_regime":
                self._regime_score(
                    signal_direction,
                    analysis,
                ),
        }

        weighted = 0.0

        for factor, score in (
            factors.items()
        ):

            weighted += (
                self._clamp(
                    score
                )
                * self.weights.get(
                    factor,
                    0.0,
                )
            )

        # -------------------------------------------------
        # Alignment bonus
        # -------------------------------------------------

        mtf = analysis.get(
            "multi_timeframe",
            {},
        )

        if isinstance(
            mtf,
            dict,
        ):

            aligned = bool(
                mtf.get(
                    "aligned",
                    False,
                )
            )

            mtf_direction = (
                self._direction(
                    mtf.get(
                        "direction"
                    )
                )
            )

            if (
                aligned
                and mtf_direction
                == signal_direction
            ):

                weighted += 5.0

        # -------------------------------------------------
        # Conflict penalty
        # -------------------------------------------------

        conflict_penalty = 0.0

        directions = []

        tf = analysis.get(
            "timeframes",
            {},
        )

        if isinstance(
            tf,
            dict,
        ):

            for timeframe in (
                "15m",
                "1h",
                "4h",
            ):

                item = tf.get(
                    timeframe,
                    {},
                )

                if not isinstance(
                    item,
                    dict,
                ):
                    continue

                tf_direction = (
                    self._direction(
                        item.get(
                            "direction"
                        )
                    )
                )

                if tf_direction in {
                    "LONG",
                    "SHORT",
                }:

                    directions.append(
                        tf_direction
                    )

        opposing = sum(
            1
            for item in directions
            if item != signal_direction
        )

        conflict_penalty += (
            opposing * 7.5
        )

        weighted -= conflict_penalty

        confidence = self._clamp(
            weighted
        )

        passed = (
            confidence
            >= self.minimum_confidence
        )

        return {
            "success": True,
            "direction":
                signal_direction,
            "confidence":
                round(
                    confidence,
                    2,
                ),
            "minimum_confidence":
                self.minimum_confidence,
            "passed":
                passed,
            "decision":
                "QUALIFIED"
                if passed
                else "REJECTED",
            "conflict_penalty":
                round(
                    conflict_penalty,
                    2,
                ),
            "factors": {
                key: round(
                    value,
                    2,
                )
                for key, value
                in factors.items()
            },
            "weights":
                self.weights.copy(),
        }

    # =====================================================
    # EVALUATE
    # =====================================================

    def evaluate(
        self,
        analysis: dict[str, Any],
    ) -> dict[str, Any]:

        direction = self._direction(
            analysis.get(
                "direction",
                "NEUTRAL",
            )
        )

        return self.calculate(
            analysis,
            direction=direction,
        )

    # =====================================================
    # BREAKDOWN
    # =====================================================

    def breakdown(
        self,
        analysis: dict[str, Any],
    ) -> dict[str, Any]:

        result = self.evaluate(
            analysis
        )

        return {
            "success":
                result.get(
                    "success",
                    False,
                ),
            "direction":
                result.get(
                    "direction",
                    "NEUTRAL",
                ),
            "confidence":
                result.get(
                    "confidence",
                    0,
                ),
            "factors":
                result.get(
                    "factors",
                    {},
                ),
            "weights":
                result.get(
                    "weights",
                    self.weights.copy(),
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
            "version": "2.0.0",
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
