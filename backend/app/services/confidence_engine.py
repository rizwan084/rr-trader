from __future__ import annotations

from typing import Any


class ConfidenceEngine:
    """RR Trader Core-7 confidence engine.

    ONLY these seven market confirmations affect signal confidence:
      1. EMA trend
      2. RSI
      3. Momentum
      4. Volume
      5. Market structure
      6. Multi-timeframe agreement (15m/1h/4h)
      7. Support / resistance location

    Risk, order-book, liquidation, derivatives, news, advanced rules and
    expansion bonuses are deliberately excluded from confidence.
    """

    DEFAULT_WEIGHTS = {
        "ema_trend": 15.0,
        "rsi": 10.0,
        "momentum": 15.0,
        "volume": 10.0,
        "market_structure": 15.0,
        "multi_timeframe": 20.0,
        "support_resistance": 15.0,
    }
    REQUIRED_MTF = ("15m", "1h", "4h")

    def __init__(self, minimum_confidence: float = 85.0, weights: dict[str, float] | None = None) -> None:
        self.minimum_confidence = float(minimum_confidence)
        self.weights = weights.copy() if isinstance(weights, dict) else self.DEFAULT_WEIGHTS.copy()
        self._normalize_weights()

    @staticmethod
    def _clamp(v: Any, low: float = 0.0, high: float = 100.0) -> float:
        try:
            return max(low, min(high, float(v)))
        except (TypeError, ValueError):
            return low

    @staticmethod
    def _direction(v: Any) -> str:
        v = str(v or "NEUTRAL").upper().strip()
        return v if v in {"LONG", "SHORT", "NEUTRAL"} else "NEUTRAL"

    @staticmethod
    def _tf(a: dict[str, Any]) -> dict[str, Any]:
        x = a.get("timeframes", {})
        return x if isinstance(x, dict) else {}

    def _normalize_weights(self) -> None:
        clean = {}
        for k, default in self.DEFAULT_WEIGHTS.items():
            try:
                clean[k] = max(0.0, float(self.weights.get(k, default)))
            except (TypeError, ValueError):
                clean[k] = default
        total = sum(clean.values()) or 1.0
        self.weights = {k: v / total for k, v in clean.items()}

    def _ema(self, d: str, x: dict[str, Any]) -> float:
        ind = x.get("indicators", {}) if isinstance(x, dict) else {}
        if not isinstance(ind, dict):
            return 0.0
        try:
            p = float(ind.get("price", 0))
            e20 = float(ind.get("ema20", 0))
            e50 = float(ind.get("ema50", 0))
        except (TypeError, ValueError):
            return 0.0
        if not all((p, e20, e50)):
            return 0.0
        return 100.0 if ((d == "LONG" and p > e20 > e50) or (d == "SHORT" and p < e20 < e50)) else 0.0

    def _rsi(self, d: str, x: dict[str, Any]) -> float:
        ind = x.get("indicators", {}) if isinstance(x, dict) else {}
        if not isinstance(ind, dict):
            return 0.0
        try: r = float(ind.get("rsi", 50.0))
        except (TypeError, ValueError): return 0.0
        # Directional but non-extreme RSI: the same practical behavior as the
        # earlier RR Trader signal logic.
        if d == "LONG":
            return 100.0 if 50.0 < r < 70.0 else 0.0
        return 100.0 if 30.0 < r < 50.0 else 0.0

    def _momentum(self, d: str, x: dict[str, Any]) -> float:
        ind = x.get("indicators", {}) if isinstance(x, dict) else {}
        if not isinstance(ind, dict):
            return 0.0
        try: m = float(ind.get("momentum", 0.0))
        except (TypeError, ValueError): return 0.0
        aligned = m if d == "LONG" else -m
        return self._clamp(50.0 + aligned * 10.0)

    def _volume(self, d: str, x: dict[str, Any]) -> float:
        ind = x.get("indicators", {}) if isinstance(x, dict) else {}
        if not isinstance(ind, dict):
            return 0.0
        try: ratio = float(ind.get("volume_ratio", 0.0))
        except (TypeError, ValueError): return 0.0
        candle = ind.get("candle_structure", {})
        cd = self._direction(candle.get("direction") if isinstance(candle, dict) else None)
        if ratio <= 0 or cd != d:
            return 0.0
        return self._clamp(ratio * 50.0)

    def _structure(self, d: str, a: dict[str, Any]) -> float:
        vals = []
        for tf in self.REQUIRED_MTF:
            x = self._tf(a).get(tf, {})
            if not isinstance(x, dict): continue
            s = x.get("structure", {})
            if not isinstance(s, dict): continue
            sd = self._direction(s.get("direction"))
            vals.append(100.0 if sd == d else 0.0)
        return sum(vals) / len(vals) if vals else 0.0

    def _mtf(self, d: str, a: dict[str, Any]) -> float:
        vals = []
        for tf in self.REQUIRED_MTF:
            x = self._tf(a).get(tf, {})
            if isinstance(x, dict):
                vals.append(100.0 if self._direction(x.get("direction")) == d else 0.0)
        return sum(vals) / len(vals) if vals else 0.0

    def _sr(self, d: str, a: dict[str, Any]) -> float:
        x = self._tf(a).get("15m", {})
        s = x.get("structure", {}) if isinstance(x, dict) else {}
        sr = s.get("support_resistance", {}) if isinstance(s, dict) else {}
        if not isinstance(sr, dict): return 0.0
        loc = str(sr.get("location", "")).upper()
        if d == "LONG":
            return {"NEAR_SUPPORT": 100.0, "MID_RANGE": 45.0, "NEAR_RESISTANCE": 0.0}.get(loc, 0.0)
        return {"NEAR_RESISTANCE": 100.0, "MID_RANGE": 45.0, "NEAR_SUPPORT": 0.0}.get(loc, 0.0)

    def calculate(self, analysis: dict[str, Any], *, direction: str | None = None) -> dict[str, Any]:
        if not isinstance(analysis, dict):
            return {"success": False, "confidence": 0.0, "decision": "NO_TRADE", "passed": False}
        d = self._direction(direction or analysis.get("direction"))
        if d == "NEUTRAL":
            return {"success": True, "confidence": 0.0, "decision": "NO_TRADE", "passed": False, "direction": d, "factors": {}}

        tf = self._tf(analysis)
        f = {
            "ema_trend": self._ema(d, tf.get("15m", {})),
            "rsi": self._rsi(d, tf.get("15m", {})),
            "momentum": self._momentum(d, tf.get("15m", {})),
            "volume": self._volume(d, tf.get("15m", {})),
            "market_structure": self._structure(d, analysis),
            "multi_timeframe": self._mtf(d, analysis),
            "support_resistance": self._sr(d, analysis),
        }
        available = [k for k,v in f.items() if v > 0]
        total_w = sum(self.weights[k] for k in available) or 1.0
        confidence = sum(f[k] * self.weights[k] for k in available) / total_w if available else 0.0
        aligned = sum(1 for tf_name in self.REQUIRED_MTF if self._direction(tf.get(tf_name, {}).get("direction")) == d if isinstance(tf.get(tf_name), dict))
        reasons = []
        if f["ema_trend"] >= 100: reasons.append("EMA20/EMA50 trend confirms direction.")
        if f["rsi"] >= 100: reasons.append("RSI confirms directional momentum.")
        if f["momentum"] >= 70: reasons.append("Momentum supports the direction.")
        if f["volume"] >= 50: reasons.append("Volume confirms the move.")
        if f["market_structure"] >= 66: reasons.append("Market structure confirms the direction.")
        if f["multi_timeframe"] >= 66: reasons.append(f"{aligned}/3 core timeframes agree.")
        if f["support_resistance"] >= 100: reasons.append("Price is at the correct support/resistance location.")
        passed = d in {"LONG","SHORT"} and confidence >= self.minimum_confidence
        return {
            "success": True, "version": "core-7", "direction": d,
            "confidence": round(confidence, 2), "minimum_confidence": self.minimum_confidence,
            "passed": passed, "decision": "QUALIFIED" if passed else "REJECTED",
            "available_factor_count": len(available), "factors": {k: round(v,2) for k,v in f.items()},
            "weights": self.weights.copy(), "reasons": list(dict.fromkeys(reasons)),
            "core_rules": ["EMA trend","RSI","Momentum","Volume","Market Structure","MTF 15m/1h/4h","Support/Resistance"],
        }

    def evaluate(self, analysis: dict[str, Any]) -> dict[str, Any]:
        return self.calculate(analysis, direction=self._direction(analysis.get("direction")))

    def breakdown(self, analysis: dict[str, Any]) -> dict[str, Any]:
        return self.evaluate(analysis)

    def status(self) -> dict[str, Any]:
        return {"enabled": True, "version": "core-7", "minimum_confidence": self.minimum_confidence, "rules": self.DEFAULT_WEIGHTS.copy()}


confidence_engine = ConfidenceEngine()
__all__ = ["ConfidenceEngine", "confidence_engine"]
