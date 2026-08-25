from __future__ import annotations

from typing import Any

from app.services.advanced_confirmations import advanced_confirmation_engine


class ConfidenceEngine:
    """RR Trader calibrated confidence engine.

    Confidence measures directional evidence, not simply the number of
    available indicators. Missing optional data is neutral. Strong aligned
    trend/structure/momentum/volume/MTF evidence is rewarded, while real
    conflicts still reduce the score.
    """

    DEFAULT_WEIGHTS = {
        "trend": 0.10,
        "structure": 0.15,
        "momentum": 0.14,
        "volume": 0.10,
        "support_resistance": 0.08,
        "multi_timeframe": 0.18,
        "liquidity": 0.06,
        "derivatives": 0.06,
        "risk_reward": 0.07,
        "market_regime": 0.06,
    }
    REQUIRED_MTF = ("15m", "1h", "4h")

    def __init__(self, minimum_confidence: float = 85.0, weights: dict[str, float] | None = None) -> None:
        self.minimum_confidence = float(minimum_confidence)
        self.weights = weights.copy() if isinstance(weights, dict) else self.DEFAULT_WEIGHTS.copy()
        self._normalize_weights()

    @staticmethod
    def _clamp(v: Any, low: float = 0.0, high: float = 100.0) -> float:
        try: v = float(v)
        except (TypeError, ValueError): return low
        return max(low, min(high, v))

    @staticmethod
    def _direction(v: Any) -> str:
        v = str(v or "NEUTRAL").upper().strip()
        return v if v in {"LONG", "SHORT", "NEUTRAL"} else "NEUTRAL"

    @staticmethod
    def _bool(v: Any) -> bool:
        if isinstance(v, bool): return v
        return str(v).lower().strip() in {"1", "true", "yes", "y", "on"}

    def _normalize_weights(self) -> None:
        clean = {k: max(0.0, float(v)) for k, v in self.weights.items() if self._is_number(v)}
        for k, v in self.DEFAULT_WEIGHTS.items(): clean.setdefault(k, v)
        total = sum(clean.values()) or 1.0
        self.weights = {k: v / total for k, v in clean.items()}

    @staticmethod
    def _is_number(v: Any) -> bool:
        try: float(v); return True
        except (TypeError, ValueError): return False

    @staticmethod
    def _tf(analysis: dict[str, Any]) -> dict[str, Any]:
        x = analysis.get("timeframes", {})
        return x if isinstance(x, dict) else {}

    def _directional(self, direction: str, evidence: Any, score: Any, neutral_factor: float = 0.55) -> float:
        s = self._clamp(score); e = self._direction(evidence)
        if e == direction: return s
        if e == "NEUTRAL": return s * neutral_factor
        return 0.0

    def _trend(self, d: str, a: dict[str, Any]) -> float:
        x = self._tf(a).get("1h", {}); return self._directional(d, x.get("direction") if isinstance(x, dict) else None, x.get("confidence", 0) if isinstance(x, dict) else 0)

    def _structure(self, d: str, a: dict[str, Any]) -> float:
        vals = []
        for tf in self.REQUIRED_MTF:
            x = self._tf(a).get(tf, {})
            if not isinstance(x, dict): continue
            s = x.get("structure", {}); s = s if isinstance(s, dict) else {}
            det = s.get("structure_details", {}); det = det if isinstance(det, dict) else s
            bull = int(self._bool(det.get("higher_high"))) + int(self._bool(det.get("higher_low")))
            bear = int(self._bool(det.get("lower_high"))) + int(self._bool(det.get("lower_low")))
            raw = max(bull, bear) * 50.0
            bos = s.get("break_of_structure", {})
            if isinstance(bos, dict) and self._bool(bos.get("break")) and self._direction(bos.get("direction")) == d: raw += 25.0
            vals.append(self._directional(d, s.get("direction"), min(100.0, raw)))
        return sum(vals) / len(vals) if vals else 0.0

    def _momentum(self, d: str, a: dict[str, Any]) -> float:
        x = self._tf(a).get("15m", {}); ind = x.get("indicators", {}) if isinstance(x, dict) else {}
        if not isinstance(ind, dict): return 0.0
        m = float(ind.get("momentum", 0) or 0)
        # Momentum is signed. Strong directional momentum gets a nonlinear boost.
        aligned = m if d == "LONG" else -m
        return self._clamp(50.0 + aligned * 14.0)

    def _volume(self, d: str, a: dict[str, Any]) -> float:
        del d; vals = []
        for tf in self.REQUIRED_MTF:
            x = self._tf(a).get(tf, {}); ind = x.get("indicators", {}) if isinstance(x, dict) else {}
            if not isinstance(ind, dict): continue
            ratio = float(ind.get("volume_ratio", 0) or 0)
            if ratio > 0: vals.append(self._clamp(35.0 + ratio * 32.5))
        return sum(vals) / len(vals) if vals else 0.0

    def _sr(self, d: str, a: dict[str, Any]) -> float:
        x = self._tf(a).get("15m", {}); s = x.get("structure", {}) if isinstance(x, dict) else {}
        s = s if isinstance(s, dict) else {}; sr = s.get("support_resistance", {}); sr = sr if isinstance(sr, dict) else {}
        loc = str(sr.get("location", "")).upper()
        if d == "LONG": return {"NEAR_SUPPORT": 90.0, "MID_RANGE": 55.0, "NEAR_RESISTANCE": 15.0}.get(loc, 50.0)
        return {"NEAR_RESISTANCE": 90.0, "MID_RANGE": 55.0, "NEAR_SUPPORT": 15.0}.get(loc, 50.0)

    def _mtf(self, d: str, a: dict[str, Any]) -> float:
        m = a.get("multi_timeframe", {}); m = m if isinstance(m, dict) else {}
        wd = self._clamp(m.get("weighted_confidence", 0)); ar = self._clamp(m.get("agreement_ratio", 0), 0, 1)
        score = wd * (0.65 + 0.35 * ar)
        if self._bool(m.get("aligned")): score += 12.0
        if self._bool(m.get("publishable_mtf")): score += 8.0
        return self._directional(d, m.get("direction"), self._clamp(score))

    def _liquidity(self, d: str, a: dict[str, Any]) -> float:
        x = a.get("order_book", {}); x = x if isinstance(x, dict) else {}
        if str(x.get("status", "")).upper() != "AVAILABLE": return 0.0
        return self._directional(d, x.get("direction"), x.get("score", 0), 0.45)

    def _derivatives(self, d: str, a: dict[str, Any]) -> float:
        x = a.get("derivatives", {}); x = x if isinstance(x, dict) else {}
        if str(x.get("status", "")).upper() != "AVAILABLE": return 0.0
        return self._directional(d, x.get("direction"), x.get("score", 0), 0.45)

    def _rr(self, a: dict[str, Any]) -> float:
        rr = float(a.get("risk_reward", 0) or 0)
        if rr <= 0: return 0.0
        if rr < 1: return 20.0
        if rr < 1.5: return 45.0
        if rr < 2: return 65.0
        if rr < 2.5: return 80.0
        if rr < 3: return 92.0
        return 100.0

    def _regime(self, d: str, a: dict[str, Any]) -> float:
        x = self._tf(a).get("4h", {}); return self._directional(d, x.get("direction") if isinstance(x, dict) else None, x.get("confidence", 0) if isinstance(x, dict) else 0)

    def _market_expansion_bonus(self, d: str, a: dict[str, Any], f: dict[str, float]) -> tuple[float, dict[str, Any]]:
        x = self._tf(a).get("15m", {}); ind = x.get("indicators", {}) if isinstance(x, dict) else {}; ind = ind if isinstance(ind, dict) else {}
        breakout = ind.get("breakout", {}); breakout = breakout if isinstance(breakout, dict) else {}
        breakout_ok = self._direction(breakout.get("direction")) == d and self._bool(breakout.get("breakout"))
        strong = sum(1 for k in ("trend", "structure", "momentum", "volume", "multi_timeframe", "market_regime") if f.get(k, 0) >= 75)
        bonus = 0.0
        if strong >= 3: bonus += 4.0
        if strong >= 5: bonus += 4.0
        if strong >= 6: bonus += 3.0
        if breakout_ok and f.get("volume", 0) >= 70: bonus += 4.0
        if f.get("momentum", 0) >= 80 and f.get("structure", 0) >= 75: bonus += 3.0
        return min(18.0, bonus), {"strong_core_factors": strong, "breakout_confirmed": breakout_ok}

    def _strict_gates(self, d: str, a: dict[str, Any], f: dict[str, float]) -> list[str]:
        fail = []
        if d not in {"LONG", "SHORT"}: return ["NO_DIRECTION"]
        tf = self._tf(a); missing = [x for x in self.REQUIRED_MTF if not isinstance(tf.get(x), dict) or not tf.get(x)]
        if missing: fail.append("MISSING_MTF:" + ",".join(missing))
        m = a.get("multi_timeframe", {}); m = m if isinstance(m, dict) else {}
        if self._direction(m.get("direction")) != d: fail.append("MTF_DIRECTION_CONFLICT")
        if not self._bool(m.get("aligned")): fail.append("MTF_NOT_FULLY_ALIGNED")
        if not self._bool(m.get("publishable_mtf")): fail.append("MTF_STRICT_GATE_FAILED")
        if f.get("risk_reward", 0) < 65: fail.append("RISK_REWARD_TOO_LOW")
        return list(dict.fromkeys(fail))

    def calculate(self, analysis: dict[str, Any], *, direction: str | None = None) -> dict[str, Any]:
        if not isinstance(analysis, dict): return {"success": False, "confidence": 0.0, "decision": "NO_TRADE", "passed": False}
        d = self._direction(direction or analysis.get("direction"))
        if d == "NEUTRAL": return {"success": True, "confidence": 0.0, "decision": "NO_TRADE", "passed": False, "direction": d, "factors": {}}
        f = {
            "trend": self._trend(d, analysis), "structure": self._structure(d, analysis), "momentum": self._momentum(d, analysis),
            "volume": self._volume(d, analysis), "support_resistance": self._sr(d, analysis), "multi_timeframe": self._mtf(d, analysis),
            "liquidity": self._liquidity(d, analysis), "derivatives": self._derivatives(d, analysis), "risk_reward": self._rr(analysis), "market_regime": self._regime(d, analysis),
        }
        # Normalize over evidence that is actually present; optional missing feeds do not drag a good setup down.
        available = []
        for k, v in f.items():
            if k in {"liquidity", "derivatives"} and v == 0:
                continue
            if k == "risk_reward" and v == 0:
                continue
            available.append(k)
        weight_total = sum(self.weights[k] for k in available) or 1.0
        base = sum(f[k] * self.weights[k] for k in available) / weight_total
        expansion_bonus, expansion = self._market_expansion_bonus(d, analysis, f)

        # Corroboration from rules 25-50, capped so it cannot manufacture a signal.
        advanced = advanced_confirmation_engine.evaluate(analysis, d)
        adv_score = self._clamp(advanced.get("score", 0)); adv_ratio = self._clamp(advanced.get("confirmation_ratio", 0), 0, 1)
        adv_available = int(advanced.get("available_rules", 0) or 0)
        advanced_bonus = min(15.0, self._clamp((adv_score - 45.0) / 55.0 * 15.0) * adv_ratio) if adv_available >= 3 else 0.0

        # Real conflicts are penalized; neutral optional feeds are not.
        tf_dirs = [self._direction(self._tf(analysis).get(x, {}).get("direction")) for x in self.REQUIRED_MTF if isinstance(self._tf(analysis).get(x), dict)]
        conflicts = sum(1 for x in tf_dirs if x in {"LONG", "SHORT"} and x != d)
        conflict_penalty = min(20.0, conflicts * 8.0)
        if f["support_resistance"] <= 15: conflict_penalty += 7.0

        confidence = self._clamp(base + expansion_bonus + advanced_bonus - conflict_penalty)
        gates = self._strict_gates(d, analysis, f)
        passed = confidence >= self.minimum_confidence and not gates
        return {
            "success": True, "version": "5.0.0", "direction": d, "confidence": round(confidence, 2),
            "minimum_confidence": self.minimum_confidence, "passed": passed, "decision": "QUALIFIED" if passed else "REJECTED",
            "strict_gate": not bool(gates), "gate_failures": gates, "available_factor_count": len(available),
            "base_confidence": round(base, 2), "market_expansion_bonus": round(expansion_bonus, 2),
            "advanced_bonus": round(advanced_bonus, 2), "conflict_penalty": round(conflict_penalty, 2),
            "advanced_confirmations": advanced, "expansion_context": expansion,
            "factors": {k: round(v, 2) for k, v in f.items()}, "weights": self.weights.copy(),
        }

    def evaluate(self, analysis: dict[str, Any]) -> dict[str, Any]:
        return self.calculate(analysis, direction=self._direction(analysis.get("direction")))

    def breakdown(self, analysis: dict[str, Any]) -> dict[str, Any]:
        return self.evaluate(analysis)

    def status(self) -> dict[str, Any]:
        return {"enabled": True, "version": "5.0.0", "minimum_confidence": self.minimum_confidence, "advanced_rules": "25-50", "market_expansion_bonus_max": 18.0, "advanced_bonus_max": 15.0, "optional_feed_neutral": True, "weights": self.weights.copy()}


confidence_engine = ConfidenceEngine()
__all__ = ["ConfidenceEngine", "confidence_engine"]
