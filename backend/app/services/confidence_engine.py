from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConfidenceResult:
    """
    Final confidence result produced by the RR Trader
    confidence engine.

    The confidence value represents agreement among
    configured factors. It is not a guarantee of profit.
    """

    direction: str
    confidence: float
    score: float
    max_score: float
    confirmations: int
    total_factors: int
    reasons: list[str] = field(
        default_factory=list
    )
    factors: dict[str, Any] = field(
        default_factory=dict
    )

    @property
    def confirmation_percent(self) -> float:
        if self.total_factors <= 0:
            return 0.0

        return round(
            (
                self.confirmations
                / self.total_factors
            )
            * 100.0,
            2,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction,
            "confidence": round(
                self.confidence,
                2,
            ),
            "score": round(
                self.score,
                2,
            ),
            "max_score": round(
                self.max_score,
                2,
            ),
            "confirmations": (
                self.confirmations
            ),
            "total_factors": (
                self.total_factors
            ),
            "confirmation_percent": (
                self.confirmation_percent
            ),
            "reasons": list(
                self.reasons
            ),
            "factors": dict(
                self.factors
            ),
        }


class ConfidenceEngine:
    """
    RR Trader confidence engine foundation.

    The weights intentionally separate market-direction
    confirmations from later risk/execution vetoes.

    The engine will eventually consume the 20 market
    confirmations from the Analysis Engine.

    Risk gates 21-24 are NOT counted as directional
    market confirmations.
    """

    FACTOR_WEIGHTS: dict[str, float] = {
        "market_regime": 10.0,
        "market_structure": 10.0,
        "multi_timeframe": 12.0,
        "entry_location": 8.0,
        "liquidity_sweep": 5.0,
        "vwap": 4.0,
        "atr_volatility": 4.0,
        "momentum": 8.0,
        "divergence": 4.0,
        "breakout": 5.0,
        "retest": 5.0,
        "derivatives": 7.0,
        "liquidations": 4.0,
        "order_book": 4.0,
        "tradeability": 3.0,
        "news_event": 2.0,
        "btc_context": 2.0,
        "relative_strength": 2.0,
        "risk_reward": 5.0,
        "stop_quality": 5.0,
    }

    def __init__(
        self,
        min_confidence: float = 85.0,
    ) -> None:

        self.min_confidence = float(
            min_confidence
        )

    # =====================================================
    # SAFE CONVERSION
    # =====================================================

    @staticmethod
    def _safe_float(
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
    # DIRECTION NORMALIZATION
    # =====================================================

    @staticmethod
    def _direction_score(
        value: Any,
    ) -> float:

        if value is None:
            return 0.0

        if isinstance(
            value,
            str,
        ):

            normalized = (
                value.lower()
                .strip()
                .replace(
                    "_",
                    " ",
                )
                .replace(
                    "-",
                    " ",
                )
            )

            bullish = {
                "bullish",
                "long",
                "buy",
                "positive",
                "up",
                "strong bullish",
                "supporting",
            }

            bearish = {
                "bearish",
                "short",
                "sell",
                "negative",
                "down",
                "strong bearish",
                "contradicting",
            }

            neutral = {
                "neutral",
                "none",
                "flat",
                "unknown",
            }

            if normalized in bullish:
                return 1.0

            if normalized in bearish:
                return -1.0

            if normalized in neutral:
                return 0.0

        numeric = (
            ConfidenceEngine._safe_float(
                value,
                0.0,
            )
        )

        if numeric > 0:
            return 1.0

        if numeric < 0:
            return -1.0

        return 0.0

    # =====================================================
    # FACTOR DIRECTION
    # =====================================================

    def _factor_direction(
        self,
        factor_name: str,
        data: dict[str, Any],
    ) -> float:

        direction_keys = {
            "market_regime": [
                "direction",
                "regime",
                "trend",
            ],
            "market_structure": [
                "direction",
                "structure",
            ],
            "multi_timeframe": [
                "direction",
                "mtf_direction",
            ],
            "entry_location": [
                "direction",
            ],
            "liquidity_sweep": [
                "direction",
            ],
            "vwap": [
                "direction",
            ],
            "atr_volatility": [
                "direction",
            ],
            "momentum": [
                "direction",
                "momentum",
            ],
            "divergence": [
                "direction",
                "divergence",
            ],
            "breakout": [
                "direction",
            ],
            "retest": [
                "direction",
            ],
            "derivatives": [
                "direction",
                "bias",
            ],
            "liquidations": [
                "direction",
            ],
            "order_book": [
                "direction",
            ],
            "tradeability": [
                "direction",
            ],
            "news_event": [
                "direction",
            ],
            "btc_context": [
                "direction",
            ],
            "relative_strength": [
                "direction",
            ],
            "risk_reward": [
                "direction",
            ],
            "stop_quality": [
                "direction",
            ],
        }

        for key in direction_keys.get(
            factor_name,
            ["direction"],
        ):

            if key not in data:
                continue

            direction = (
                self._direction_score(
                    data.get(key)
                )
            )

            if direction != 0:
                return direction

        return 0.0

    # =====================================================
    # NORMALIZE FACTOR
    # =====================================================

    def _normalize_factor(
        self,
        factor_name: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:

        direction = (
            self._factor_direction(
                factor_name,
                data,
            )
        )

        strength = self._safe_float(
            data.get(
                "strength",
                1.0,
            ),
            1.0,
        )

        strength = max(
            0.0,
            min(
                abs(strength),
                1.0,
            ),
        )

        weight = self.FACTOR_WEIGHTS[
            factor_name
        ]

        weighted_score = (
            direction
            * strength
            * weight
        )

        return {
            "direction": (
                "bullish"
                if direction > 0
                else "bearish"
                if direction < 0
                else "neutral"
            ),
            "strength": round(
                strength,
                4,
            ),
            "weight": weight,
            "weighted_score": round(
                weighted_score,
                4,
            ),
            "reason": str(
                data.get(
                    "reason",
                    "",
                )
            ),
        }

    # =====================================================
    # CALCULATE
    # =====================================================

    def calculate(
        self,
        factors: dict[
            str,
            dict[str, Any],
        ],
    ) -> ConfidenceResult:

        long_score = 0.0
        short_score = 0.0

        reasons: list[str] = []
        normalized: dict[
            str,
            Any,
        ] = {}

        max_score = sum(
            self.FACTOR_WEIGHTS.values()
        )

        for factor_name, weight in (
            self.FACTOR_WEIGHTS.items()
        ):

            data = factors.get(
                factor_name,
                {},
            )

            if not isinstance(
                data,
                dict,
            ):
                data = {}

            item = self._normalize_factor(
                factor_name,
                data,
            )

            normalized[
                factor_name
            ] = item

            weighted_score = (
                self._safe_float(
                    item.get(
                        "weighted_score",
                        0,
                    )
                )
            )

            if weighted_score > 0:
                long_score += (
                    weighted_score
                )

            elif weighted_score < 0:
                short_score += abs(
                    weighted_score
                )

            reason = item.get(
                "reason"
            )

            if reason:
                reasons.append(
                    str(reason)
                )

        # =================================================
        # FINAL DIRECTION
        # =================================================

        if long_score > short_score:

            direction = "LONG"
            score = long_score

        elif short_score > long_score:

            direction = "SHORT"
            score = short_score

        else:

            direction = "NEUTRAL"
            score = 0.0

        # =================================================
        # CONFIDENCE
        # =================================================

        if (
            direction != "NEUTRAL"
            and max_score > 0
        ):

            confidence = (
                score
                / max_score
                * 100.0
            )

        else:

            confidence = 0.0

        confidence = max(
            0.0,
            min(
                confidence,
                100.0,
            ),
        )

        # =================================================
        # CONFIRMATIONS
        # =================================================

        confirmations = 0

        for factor_name in (
            self.FACTOR_WEIGHTS
        ):

            data = factors.get(
                factor_name,
                {},
            )

            if not isinstance(
                data,
                dict,
            ):
                continue

            factor_direction = (
                self._factor_direction(
                    factor_name,
                    data,
                )
            )

            strength = self._safe_float(
                data.get(
                    "strength",
                    0.0,
                ),
                0.0,
            )

            aligned = (
                direction == "LONG"
                and factor_direction > 0
            ) or (
                direction == "SHORT"
                and factor_direction < 0
            )

            if (
                aligned
                and strength > 0
            ):
                confirmations += 1

        return ConfidenceResult(
            direction=direction,
            confidence=confidence,
            score=score,
            max_score=max_score,
            confirmations=confirmations,
            total_factors=len(
                self.FACTOR_WEIGHTS
            ),
            reasons=list(
                dict.fromkeys(
                    reasons
                )
            ),
            factors=normalized,
        )


__all__ = [
    "ConfidenceEngine",
    "ConfidenceResult",
]
