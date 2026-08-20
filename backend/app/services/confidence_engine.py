from __future__ import annotations

from typing import Any


class ConfidenceEngine:
    """
    RR Trader Confidence Engine v3.

    Confidence is evidence-driven and is a FINAL qualification gate.

    A high 24h mover is NOT automatically a trade.
    A setup must have:
      - valid LONG/SHORT direction
      - strict 15m/1h/4h MTF confirmation
      - meaningful entry location
      - repeated support/resistance reaction when available
      - structure + momentum confirmation
      - acceptable risk/reward
      - no critical contradiction

    Missing evidence is neutral, but required gates fail closed.
    The engine never invents evidence.
    """

    DEFAULT_WEIGHTS = {
        "trend": 0.08,
        "structure": 0.12,
        "momentum": 0.08,
        "volume": 0.06,
        "support_resistance": 0.14,
        "multi_timeframe": 0.16,
        "liquidity": 0.07,
        "derivatives": 0.07,
        "risk_reward": 0.10,
        "market_regime": 0.12,
    }

    REQUIRED_MTF = ("15m", "1h", "4h")

    def __init__(
        self,
        minimum_confidence: float = 85.0,
        weights: dict[str, float] | None = None,
    ) -> None:
        self.minimum_confidence = float(minimum_confidence)
        self.weights = (
            weights.copy()
            if isinstance(weights, dict)
            else self.DEFAULT_WEIGHTS.copy()
        )
        self._normalize_weights()

    @staticmethod
    def _clamp(value: Any, low: float = 0.0, high: float = 100.0) -> float:
        try:
            value = float(value)
        except (TypeError, ValueError):
            return low
        return max(low, min(high, value))

    @staticmethod
    def _direction(value: Any) -> str:
        value = str(value or "NEUTRAL").upper().strip()
        return value if value in {"LONG", "SHORT", "NEUTRAL"} else "NEUTRAL"

    @staticmethod
    def _text(value: Any) -> str:
        return str(value or "").upper().strip()

    @staticmethod
    def _bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).lower().strip() in {"1", "true", "yes", "y", "on"}

    def _normalize_weights(self) -> None:
        cleaned: dict[str, float] = {}
        for key, value in self.weights.items():
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                numeric = 0.0
            cleaned[key] = max(0.0, numeric)

        # Keep the canonical factor set even when a partial custom
        # weight dictionary is supplied.
        for key, value in self.DEFAULT_WEIGHTS.items():
            cleaned.setdefault(key, value)

        total = sum(cleaned.values())
        if total <= 0:
            cleaned = self.DEFAULT_WEIGHTS.copy()
            total = sum(cleaned.values())

        self.weights = {key: value / total for key, value in cleaned.items()}

    def _directional_score(
        self, direction: str, evidence_direction: Any, score: Any
    ) -> float:
        if direction == "NEUTRAL":
            return 0.0
        evidence = self._direction(evidence_direction)
        score = self._clamp(score)
        if evidence == direction:
            return score
        if evidence == "NEUTRAL":
            return score * 0.35
        return 0.0

    def _timeframes(self, analysis: dict[str, Any]) -> dict[str, Any]:
        tf = analysis.get("timeframes", {})
        return tf if isinstance(tf, dict) else {}

    def _trend_score(self, direction: str, analysis: dict[str, Any]) -> float:
        item = self._timeframes(analysis).get("1h", {})
        if not isinstance(item, dict):
            return 0.0
        return self._directional_score(direction, item.get("direction"), item.get("confidence", 0))

    def _structure_score(self, direction: str, analysis: dict[str, Any]) -> float:
        values = []
        for timeframe in self.REQUIRED_MTF:
            item = self._timeframes(analysis).get(timeframe, {})
            if not isinstance(item, dict):
                continue
            structure = item.get("structure", {})
            if not isinstance(structure, dict):
                continue
            details = structure.get("structure_details", {})
            if not isinstance(details, dict):
                details = structure

            positive = int(self._bool(details.get("higher_high"))) + int(self._bool(details.get("higher_low")))
            negative = int(self._bool(details.get("lower_high"))) + int(self._bool(details.get("lower_low")))
            strength = min(100.0, max(positive, negative) * 50.0)

            # BOS is stronger than a plain swing classification.
            bos = structure.get("break_of_structure", {})
            if isinstance(bos, dict) and self._bool(bos.get("break")):
                bos_direction = self._direction(bos.get("direction"))
                if bos_direction == direction:
                    strength = min(100.0, strength + 25.0)

            values.append(self._directional_score(
                direction, structure.get("direction", "NEUTRAL"), strength
            ))

        return sum(values) / len(values) if values else 0.0

    def _momentum_score(self, direction: str, analysis: dict[str, Any]) -> float:
        item = self._timeframes(analysis).get("15m", {})
        indicators = item.get("indicators", {}) if isinstance(item, dict) else {}
        if not isinstance(indicators, dict):
            return 0.0
        try:
            momentum = float(indicators.get("momentum", 0))
        except (TypeError, ValueError):
            return 0.0
        if direction == "LONG":
            return self._clamp(50.0 + momentum * 10.0)
        if direction == "SHORT":
            return self._clamp(50.0 - momentum * 10.0)
        return 0.0

    def _volume_score(self, direction: str, analysis: dict[str, Any]) -> float:
        del direction
        values = []
        for timeframe in self.REQUIRED_MTF:
            item = self._timeframes(analysis).get(timeframe, {})
            indicators = item.get("indicators", {}) if isinstance(item, dict) else {}
            if not isinstance(indicators, dict):
                continue
            try:
                ratio = float(indicators.get("volume_ratio", 0))
            except (TypeError, ValueError):
                continue
            if ratio > 0:
                values.append(self._clamp(ratio * 50.0))
        return sum(values) / len(values) if values else 0.0

    def _support_resistance_score(self, direction: str, analysis: dict[str, Any]) -> float:
        """
        Entry-location score.

        Preferred evidence:
          LONG  -> repeated support + near support / bullish reaction
          SHORT -> repeated resistance + near resistance / bearish reaction

        The scanner/signal engine may expose:
          support_resistance.retests / touches / reactions
          entry_location
          support_retest / resistance_retest
        """
        item = self._timeframes(analysis).get("15m", {})
        structure = item.get("structure", {}) if isinstance(item, dict) else {}
        sr = structure.get("support_resistance", {}) if isinstance(structure, dict) else {}
        if not isinstance(sr, dict):
            sr = {}

        location = self._text(sr.get("location"))
        if direction == "LONG":
            base = {"NEAR_SUPPORT": 82.0, "MID_RANGE": 42.0, "NEAR_RESISTANCE": 8.0}.get(location, 0.0)
        elif direction == "SHORT":
            base = {"NEAR_RESISTANCE": 82.0, "MID_RANGE": 42.0, "NEAR_SUPPORT": 8.0}.get(location, 0.0)
        else:
            return 0.0

        evidence = analysis.get("entry_location", {})
        if not isinstance(evidence, dict):
            evidence = {}

        if direction == "LONG":
            repeated = evidence.get("support_retests", evidence.get("support_touches", sr.get("support_retests", sr.get("touches", 0))))
            reaction = evidence.get("support_reaction", sr.get("support_reaction", 0))
        else:
            repeated = evidence.get("resistance_retests", evidence.get("resistance_touches", sr.get("resistance_retests", sr.get("touches", 0))))
            reaction = evidence.get("resistance_reaction", sr.get("resistance_reaction", 0))

        try:
            repeated_n = float(repeated or 0)
        except (TypeError, ValueError):
            repeated_n = 0.0
        try:
            reaction_n = float(reaction or 0)
        except (TypeError, ValueError):
            reaction_n = 0.0

        # 2 touches = useful, 3+ = strong confirmation.
        if repeated_n >= 3:
            base += 15.0
        elif repeated_n >= 2:
            base += 10.0

        base += self._clamp(reaction_n, 0, 1) * 8.0
        return self._clamp(base)

    def _mtf_score(self, direction: str, analysis: dict[str, Any]) -> float:
        mtf = analysis.get("multi_timeframe", {})
        if not isinstance(mtf, dict):
            return 0.0

        mtf_direction = self._direction(mtf.get("direction"))
        weighted = self._clamp(mtf.get("weighted_confidence", 0))
        agreement = self._clamp(mtf.get("agreement_ratio", 0), 0, 1)
        aligned = self._bool(mtf.get("aligned"))
        strict = self._bool(mtf.get("publishable_mtf"))

        score = weighted * agreement
        if aligned:
            score += 20.0
        if strict:
            score += 10.0

        return self._directional_score(direction, mtf_direction, self._clamp(score))

    def _liquidity_score(self, direction: str, analysis: dict[str, Any]) -> float:
        data = analysis.get("order_book", {})
        if not isinstance(data, dict) or self._text(data.get("status")) != "AVAILABLE":
            return 0.0
        return self._directional_score(direction, data.get("direction"), data.get("score", 0))

    def _derivatives_score(self, direction: str, analysis: dict[str, Any]) -> float:
        data = analysis.get("derivatives", {})
        if not isinstance(data, dict) or self._text(data.get("status")) != "AVAILABLE":
            return 0.0
        return self._directional_score(direction, data.get("direction"), data.get("score", 0))

    def _risk_reward_score(self, direction: str, analysis: dict[str, Any]) -> float:
        del direction
        try:
            rr = float(analysis.get("risk_reward", 0))
        except (TypeError, ValueError):
            return 0.0
        if rr <= 0:
            return 0.0
        if rr < 1.0:
            return 10.0
        if rr < 1.5:
            return 35.0
        if rr < 2.0:
            return 60.0
        if rr < 2.5:
            return 78.0
        if rr < 3.0:
            return 90.0
        return 100.0

    def _regime_score(self, direction: str, analysis: dict[str, Any]) -> float:
        item = self._timeframes(analysis).get("4h", {})
        if not isinstance(item, dict):
            return 0.0
        return self._directional_score(direction, item.get("direction"), item.get("confidence", 0))

    def _strict_gate_reasons(self, direction: str, analysis: dict[str, Any]) -> list[str]:
        reasons: list[str] = []
        if direction not in {"LONG", "SHORT"}:
            reasons.append("NO_DIRECTION")
            return reasons

        tf = self._timeframes(analysis)
        missing = [x for x in self.REQUIRED_MTF if not isinstance(tf.get(x), dict) or not tf.get(x)]
        if missing:
            reasons.append("MISSING_MTF:" + ",".join(missing))
            return reasons

        mtf = analysis.get("multi_timeframe", {})
        if not isinstance(mtf, dict):
            reasons.append("MTF_EVIDENCE_MISSING")
        else:
            if self._direction(mtf.get("direction")) != direction:
                reasons.append("MTF_DIRECTION_CONFLICT")
            if not self._bool(mtf.get("aligned")):
                reasons.append("MTF_NOT_FULLY_ALIGNED")
            if not self._bool(mtf.get("publishable_mtf")):
                reasons.append("MTF_STRICT_GATE_FAILED")

        # Explicit entry-location gate: avoid buying the middle of a range
        # or shorting directly into support.
        sr_score = self._support_resistance_score(direction, analysis)
        if sr_score < 55:
            reasons.append("ENTRY_LOCATION_NOT_STRONG")

        rr = self._risk_reward_score(direction, analysis)
        if rr < 60:
            reasons.append("RISK_REWARD_TOO_LOW")

        # If signal_engine exposes the repeated-level gate, honor it.
        location = analysis.get("entry_location", {})
        if isinstance(location, dict):
            gate = location.get("qualified")
            if gate is False:
                reasons.append("ENTRY_LOCATION_GATE_FAILED")
            required = location.get("required_retests")
            actual = location.get("retests")
            if required is not None and actual is not None:
                try:
                    if float(actual) < float(required):
                        reasons.append("INSUFFICIENT_LEVEL_RETESTS")
                except (TypeError, ValueError):
                    pass

        return list(dict.fromkeys(reasons))

    def calculate(
        self,
        analysis: dict[str, Any],
        *,
        direction: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(analysis, dict):
            return {
                "success": False,
                "confidence": 0.0,
                "decision": "NO_TRADE",
                "passed": False,
                "reason": "INVALID_ANALYSIS",
            }

        signal_direction = self._direction(
            direction or analysis.get("direction", "NEUTRAL")
        )

        if signal_direction == "NEUTRAL":
            return {
                "success": True,
                "confidence": 0.0,
                "decision": "NO_TRADE",
                "passed": False,
                "direction": "NEUTRAL",
                "factors": {},
                "gate_failures": ["NO_DIRECTION"],
            }

        factors = {
            "trend": self._trend_score(signal_direction, analysis),
            "structure": self._structure_score(signal_direction, analysis),
            "momentum": self._momentum_score(signal_direction, analysis),
            "volume": self._volume_score(signal_direction, analysis),
            "support_resistance": self._support_resistance_score(signal_direction, analysis),
            "multi_timeframe": self._mtf_score(signal_direction, analysis),
            "liquidity": self._liquidity_score(signal_direction, analysis),
            "derivatives": self._derivatives_score(signal_direction, analysis),
            "risk_reward": self._risk_reward_score(signal_direction, analysis),
            "market_regime": self._regime_score(signal_direction, analysis),
        }

        weighted = sum(
            self._clamp(score) * self.weights.get(factor, 0.0)
            for factor, score in factors.items()
        )

        mtf = analysis.get("multi_timeframe", {})
        if isinstance(mtf, dict):
            if (
                self._bool(mtf.get("aligned"))
                and self._direction(mtf.get("direction")) == signal_direction
            ):
                weighted += 5.0

        tf = self._timeframes(analysis)
        directions = [
            self._direction(tf.get(x, {}).get("direction"))
            for x in self.REQUIRED_MTF
            if isinstance(tf.get(x), dict)
        ]
        opposing = sum(1 for x in directions if x in {"LONG", "SHORT"} and x != signal_direction)
        conflict_penalty = opposing * 10.0

        # Explicitly penalize an unresolved support/resistance contradiction.
        sr_score = factors["support_resistance"]
        if sr_score <= 10:
            conflict_penalty += 8.0

        weighted = self._clamp(weighted - conflict_penalty)

        gate_failures = self._strict_gate_reasons(signal_direction, analysis)
        passed = weighted >= self.minimum_confidence and not gate_failures

        return {
            "success": True,
            "direction": signal_direction,
            "confidence": round(weighted, 2),
            "minimum_confidence": self.minimum_confidence,
            "passed": passed,
            "decision": "QUALIFIED" if passed else "REJECTED",
            "strict_gate": not bool(gate_failures),
            "gate_failures": gate_failures,
            "conflict_penalty": round(conflict_penalty, 2),
            "factors": {key: round(value, 2) for key, value in factors.items()},
            "weights": self.weights.copy(),
        }

    def evaluate(self, analysis: dict[str, Any]) -> dict[str, Any]:
        direction = self._direction(analysis.get("direction", "NEUTRAL"))
        return self.calculate(analysis, direction=direction)

    def breakdown(self, analysis: dict[str, Any]) -> dict[str, Any]:
        result = self.evaluate(analysis)
        return {
            "success": result.get("success", False),
            "direction": result.get("direction", "NEUTRAL"),
            "confidence": result.get("confidence", 0),
            "passed": result.get("passed", False),
            "decision": result.get("decision", "NO_TRADE"),
            "strict_gate": result.get("strict_gate", False),
            "gate_failures": result.get("gate_failures", []),
            "conflict_penalty": result.get("conflict_penalty", 0),
            "factors": result.get("factors", {}),
            "weights": result.get("weights", self.weights.copy()),
        }

    def status(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "version": "3.0.0",
            "minimum_confidence": self.minimum_confidence,
            "strict_mtf_required": True,
            "strict_entry_location_required": True,
            "minimum_retests_when_available": 2,
            "weights": self.weights.copy(),
        }


confidence_engine = ConfidenceEngine()

__all__ = ["ConfidenceEngine", "confidence_engine"]
