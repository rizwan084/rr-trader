from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ConfidenceResult:
    direction: str
    confidence: float
    score: float
    max_score: float
    confirmations: int
    total_factors: int
    reasons: List[str] = field(default_factory=list)
    factors: Dict[str, Any] = field(default_factory=dict)

    @property
    def confirmation_percent(self) -> float:
        if self.total_factors <= 0:
            return 0.0

        return round(
            (self.confirmations / self.total_factors) * 100,
            2,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "direction": self.direction,
            "confidence": round(self.confidence, 2),
            "score": round(self.score, 2),
            "max_score": round(self.max_score, 2),
            "confirmations": self.confirmations,
            "total_factors": self.total_factors,
            "confirmation_percent": self.confirmation_percent,
            "reasons": self.reasons,
            "factors": self.factors,
        }


class ConfidenceEngine:
    """
    RR Trader confidence engine.

    This engine combines independent market confirmations
    into an explainable LONG / SHORT confidence score.

    Important:
    This is a confidence model, not a guarantee of profit
    or prediction accuracy.
    """

    FACTOR_WEIGHTS = {
        "trend": 20.0,
        "momentum": 12.0,
        "volume": 12.0,
        "market_structure": 14.0,
        "support_resistance": 10.0,
        "order_book": 10.0,
        "open_interest": 8.0,
        "funding": 4.0,
        "liquidations": 5.0,
        "risk_reward": 5.0,
    }

    MIN_CONFIDENCE = 50.0

    def __init__(
        self,
        min_confidence: float = MIN_CONFIDENCE,
    ) -> None:
        self.min_confidence = float(
            min_confidence
        )

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

    @staticmethod
    def _direction_score(
        value: Any,
    ) -> float:
        """
        Convert common directional values into:

        +1.0 = bullish
         0.0 = neutral
        -1.0 = bearish
        """

        if value is None:
            return 0.0

        if isinstance(value, str):

            normalized = (
                value
                .lower()
                .strip()
                .replace("_", " ")
                .replace("-", " ")
            )

            if normalized in {
                "bullish",
                "long",
                "buy",
                "positive",
                "up",
                "strong bullish",
            }:
                return 1.0

            if normalized in {
                "bearish",
                "short",
                "sell",
                "negative",
                "down",
                "strong bearish",
            }:
                return -1.0

            if normalized in {
                "neutral",
                "none",
                "flat",
            }:
                return 0.0

        numeric = ConfidenceEngine._safe_float(
            value,
            0.0,
        )

        if numeric > 0:
            return 1.0

        if numeric < 0:
            return -1.0

        return 0.0

    @staticmethod
    def _extract_direction(
        data: Dict[str, Any],
        keys: List[str],
    ) -> float:
        for key in keys:

            if key not in data:
                continue

            value = data.get(key)

            direction = (
                ConfidenceEngine
                ._direction_score(value)
            )

            if direction != 0:
                return direction

        return 0.0

    def _factor_direction(
        self,
        factor_name: str,
        data: Dict[str, Any],
    ) -> float:

        key_map = {
            "trend": [
                "direction",
                "trend",
                "signal",
            ],
            "momentum": [
                "direction",
                "momentum",
                "signal",
            ],
            "volume": [
                "direction",
                "volume_direction",
                "signal",
            ],
            "market_structure": [
                "direction",
                "structure",
                "market_structure",
                "signal",
            ],
            "support_resistance": [
                "direction",
                "signal",
            ],
            "order_book": [
                "direction",
                "imbalance_direction",
                "signal",
            ],
            "open_interest": [
                "direction",
                "signal",
            ],
            "funding": [
                "direction",
                "signal",
            ],
            "liquidations": [
                "direction",
                "signal",
            ],
            "risk_reward": [
                "direction",
                "signal",
            ],
        }

        return self._extract_direction(
            data,
            key_map.get(
                factor_name,
                ["direction"],
            ),
        )

    def calculate(
        self,
        factors: Dict[str, Dict[str, Any]],
    ) -> ConfidenceResult:

        long_score = 0.0
        short_score = 0.0

        reasons: List[str] = []
        normalized_factors: Dict[str, Any] = {}

        confirmations = 0
        total_factors = 0

        max_score = sum(
            self.FACTOR_WEIGHTS.values()
        )

        for factor_name, weight in (
            self.FACTOR_WEIGHTS.items()
        ):

            factor_data = factors.get(
                factor_name,
                {},
            )

            if not isinstance(
                factor_data,
                dict,
            ):
                factor_data = {}

            direction = self._factor_direction(
                factor_name,
                factor_data,
            )

            strength = self._safe_float(
                factor_data.get(
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

            weighted_score = (
                direction
                * strength
                * weight
            )

            if weighted_score > 0:
                long_score += weighted_score

            elif weighted_score < 0:
                short_score += abs(
                    weighted_score
                )

            if direction != 0:
                total_factors += 1
                confirmations += 1

            reason = factor_data.get(
                "reason"
            )

            if reason:
                reasons.append(
                    str(reason)
                )

            normalized_factors[
                factor_name
            ] = {
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
            }

        if long_score > short_score:
            direction = "LONG"
            raw_score = long_score

        elif short_score > long_score:
            direction = "SHORT"
            raw_score = short_score

        else:
            direction = "NEUTRAL"
            raw_score = 0.0

        confidence = (
            raw_score / max_score
        ) * 100 if max_score > 0 else 0.0

        confidence = max(
            0.0,
            min(
                confidence,
                100.0,
            ),
        )

        if direction == "NEUTRAL":
            confidence = 0.0

        return ConfidenceResult(
            direction=direction,
            confidence=confidence,
            score=raw_score,
            max_score=max_score,
            confirmations=confirmations,
            total_factors=total_factors,
            reasons=reasons,
            factors=normalized_factors,
        )


__all__ = [
    "ConfidenceEngine",
    "ConfidenceResult",
]
