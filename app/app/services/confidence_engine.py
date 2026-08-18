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
            (self.confirmations / self.total_factors) * 100.0,
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
    Explainable RR Trader confidence engine.

    The score represents the amount of agreement among the
    configured market factors. It is NOT a guarantee of profit,
    prediction accuracy, or future price movement.
    """

    FACTOR_WEIGHTS: Dict[str, float] = {
        "trend": 18.0,
        "momentum": 12.0,
        "volume": 10.0,
        "market_structure": 14.0,
        "support_resistance": 10.0,
        "order_book": 10.0,
        "open_interest": 8.0,
        "funding": 4.0,
        "positioning": 5.0,
        "liquidations": 4.0,
        "risk_reward": 5.0,
    }

    MIN_CONFIDENCE = 50.0

    def __init__(self, min_confidence: float = MIN_CONFIDENCE) -> None:
        self.min_confidence = float(min_confidence)

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _direction_score(value: Any) -> float:
        if value is None:
            return 0.0

        if isinstance(value, str):
            normalized = (
                value.lower()
                .strip()
                .replace("_", " ")
                .replace("-", " ")
            )

            if normalized in {
                "bullish", "long", "buy", "positive", "up",
                "strong bullish",
            }:
                return 1.0

            if normalized in {
                "bearish", "short", "sell", "negative", "down",
                "strong bearish",
            }:
                return -1.0

            if normalized in {"neutral", "none", "flat"}:
                return 0.0

        numeric = ConfidenceEngine._safe_float(value, 0.0)

        if numeric > 0:
            return 1.0
        if numeric < 0:
            return -1.0
        return 0.0

    def _factor_direction(
        self,
        factor_name: str,
        data: Dict[str, Any],
    ) -> float:
        keys = {
            "trend": ["direction", "trend", "signal"],
            "momentum": ["direction", "momentum", "signal"],
            "volume": ["direction", "volume_direction", "signal"],
            "market_structure": ["direction", "structure", "market_structure", "signal"],
            "support_resistance": ["direction", "signal"],
            "order_book": ["direction", "imbalance_direction", "signal"],
            "open_interest": ["direction", "signal"],
            "funding": ["direction", "signal"],
            "positioning": ["direction", "signal"],
            "liquidations": ["direction", "signal"],
            "risk_reward": ["direction", "signal"],
        }

        for key in keys.get(factor_name, ["direction"]):
            if key not in data:
                continue
            direction = self._direction_score(data.get(key))
            if direction != 0:
                return direction

        return 0.0

    def calculate(
        self,
        factors: Dict[str, Dict[str, Any]],
    ) -> ConfidenceResult:
        long_score = 0.0
        short_score = 0.0
        reasons: List[str] = []
        normalized: Dict[str, Any] = {}

        max_score = sum(self.FACTOR_WEIGHTS.values())

        for factor_name, weight in self.FACTOR_WEIGHTS.items():
            data = factors.get(factor_name, {})
            if not isinstance(data, dict):
                data = {}

            direction = self._factor_direction(
                factor_name,
                data,
            )

            strength = self._safe_float(
                data.get("strength", 1.0),
                1.0,
            )
            strength = max(0.0, min(abs(strength), 1.0))

            weighted = direction * strength * weight

            if weighted > 0:
                long_score += weighted
            elif weighted < 0:
                short_score += abs(weighted)

            reason = data.get("reason")
            if reason:
                reasons.append(str(reason))

            normalized[factor_name] = {
                "direction": (
                    "bullish"
                    if direction > 0
                    else "bearish"
                    if direction < 0
                    else "neutral"
                ),
                "strength": round(strength, 4),
                "weight": weight,
                "weighted_score": round(weighted, 4),
            }

        if long_score > short_score:
            direction = "LONG"
            score = long_score
        elif short_score > long_score:
            direction = "SHORT"
            score = short_score
        else:
            direction = "NEUTRAL"
            score = 0.0

        confidence = (
            (score / max_score) * 100.0
            if max_score > 0 and direction != "NEUTRAL"
            else 0.0
        )
        confidence = max(0.0, min(confidence, 100.0))

        confirmations = 0
        for factor_name in self.FACTOR_WEIGHTS:
            data = factors.get(factor_name, {})
            if not isinstance(data, dict):
                continue

            factor_direction = self._factor_direction(
                factor_name,
                data,
            )
            strength = self._safe_float(
                data.get("strength", 0),
                0,
            )

            aligned = (
                direction == "LONG" and factor_direction > 0
            ) or (
                direction == "SHORT" and factor_direction < 0
            )

            if aligned and strength > 0:
                confirmations += 1

        return ConfidenceResult(
            direction=direction,
            confidence=confidence,
            score=score,
            max_score=max_score,
            confirmations=confirmations,
            total_factors=len(self.FACTOR_WEIGHTS),
            reasons=list(dict.fromkeys(reasons)),
            factors=normalized,
        )


__all__ = [
    "ConfidenceEngine",
    "ConfidenceResult",
]
