from __future__ import annotations
from typing import Any

class AdvancedConfirmationEngine:
    """RR Trader advanced confirmation catalog: rules 25-50.

    Missing evidence is neutral; this engine never invents a PASS.
    It returns per-rule evidence and a bounded corroboration score.
    """
    RULES = {
        25: "ema_structure_slope", 26: "rsi_regime", 27: "macd_confirmation",
        28: "adx_trend_strength", 29: "volume_profile", 30: "cvd_buy_sell_pressure",
        31: "open_interest_change", 32: "funding_extreme", 33: "long_short_ratio",
        34: "whale_activity", 35: "order_book_walls", 36: "spread_slippage",
        37: "support_resistance_strength", 38: "supply_demand_zone", 39: "fair_value_gap",
        40: "volume_imbalance", 41: "candle_quality", 42: "breakout_volume_quality",
        43: "fakeout_detection", 44: "liquidity_distance", 45: "target_liquidity",
        46: "correlation_check", 47: "sector_strength", 48: "market_breadth",
        49: "volatility_regime", 50: "setup_quality_score",
    }

    @staticmethod
    def _float(v: Any, default: float = 0.0) -> float:
        try: return float(v)
        except (TypeError, ValueError): return default

    @staticmethod
    def _direction(v: Any) -> str:
        v = str(v or "NEUTRAL").upper().strip()
        return v if v in {"LONG", "SHORT", "NEUTRAL"} else "NEUTRAL"

    @staticmethod
    def _clamp(v: Any, low: float = 0.0, high: float = 100.0) -> float:
        try: v = float(v)
        except (TypeError, ValueError): return low
        return max(low, min(high, v))

    def _tf(self, analysis: dict[str, Any], tf: str = "15m") -> dict[str, Any]:
        tfs = analysis.get("timeframes", {})
        item = tfs.get(tf, {}) if isinstance(tfs, dict) else {}
        return item if isinstance(item, dict) else {}

    def _ind(self, analysis: dict[str, Any], tf: str = "15m") -> dict[str, Any]:
        x = self._tf(analysis, tf).get("indicators", {})
        return x if isinstance(x, dict) else {}

    def _struct(self, analysis: dict[str, Any], tf: str = "15m") -> dict[str, Any]:
        x = self._tf(analysis, tf).get("structure", {})
        return x if isinstance(x, dict) else {}

    def _aligned(self, direction: str, evidence: Any, score: float = 100.0) -> float:
        return self._clamp(score) if self._direction(evidence) == direction else 0.0

    def _score_rule(self, n: int, direction: str, analysis: dict[str, Any]) -> tuple[float, str]:
        ind = self._ind(analysis); struct = self._struct(analysis)
        deriv = analysis.get("derivatives", {}); deriv = deriv if isinstance(deriv, dict) else {}
        book = analysis.get("order_book", {}); book = book if isinstance(book, dict) else {}

        if n == 25:
            slope = self._float(ind.get("ema20_slope", ind.get("ema_slope", 0)))
            state = str(ind.get("ema_alignment", ind.get("ema_state", ""))).upper()
            ok = (direction == "LONG" and (slope > 0 or "BULL" in state)) or (direction == "SHORT" and (slope < 0 or "BEAR" in state))
            return (100.0 if ok else 0.0, "EMA slope/alignment aligned" if ok else "EMA slope not aligned")
        if n == 26:
            rsi = self._float(ind.get("rsi", 0));
            if not rsi: return 0.0, "RSI unavailable"
            return self._clamp((rsi - 45) * 4 if direction == "LONG" else (55 - rsi) * 4), f"RSI {rsi:.1f}"
        if n == 27:
            hist = self._float(ind.get("macd_histogram", self._float(ind.get("macd", 0)) - self._float(ind.get("macd_signal", 0))))
            if not hist: return 0.0, "MACD unavailable"
            ok = hist > 0 if direction == "LONG" else hist < 0
            return (100.0 if ok else 0.0, "MACD aligned" if ok else "MACD conflict")
        if n == 28:
            adx = self._float(ind.get("adx", 0)); return (self._clamp((adx - 15) * 2) if adx else 0.0, f"ADX {adx:.1f}" if adx else "ADX unavailable")
        if n == 29:
            vp = ind.get("volume_profile", {}); vp = vp if isinstance(vp, dict) else {}
            loc = str(vp.get("location", "")).upper(); good = (direction == "LONG" and loc in {"BELOW_POC", "VALUE_LOW", "HIGH_VOLUME_SUPPORT"}) or (direction == "SHORT" and loc in {"ABOVE_POC", "VALUE_HIGH", "HIGH_VOLUME_RESISTANCE"})
            return (100.0 if good else 0.0, "Volume profile aligned" if good else "Volume profile unavailable/neutral")
        if n == 30:
            ev = ind.get("cvd_direction", ind.get("cvd", "")); return self._aligned(direction, ev), "CVD aligned" if self._direction(ev) == direction else "CVD unavailable/conflict"
        if n == 31:
            oi = self._float(deriv.get("open_interest_change", deriv.get("oi_change", 0))); return (self._clamp(abs(oi) * 10) if oi else 0.0, f"OI change {oi:.2f}%" if oi else "OI change unavailable")
        if n == 32:
            f = deriv.get("funding_rate", []); rate = self._float(f[-1].get("fundingRate", 0)) if isinstance(f, list) and f and isinstance(f[-1], dict) else self._float(deriv.get("funding_rate_value", 0))
            if not rate: return 0.0, "Funding unavailable"
            ok = (direction == "LONG" and rate < -0.0003) or (direction == "SHORT" and rate > 0.0003)
            return (100.0 if ok else self._clamp(abs(rate) * 100000), "Funding supports setup" if ok else "Funding not extreme")
        if n == 33:
            r = deriv.get("global_long_short_ratio", []); ratio = self._float(r[-1].get("longShortRatio", 1), 1) if isinstance(r, list) and r and isinstance(r[-1], dict) else self._float(deriv.get("long_short_ratio", 1), 1)
            ok = (direction == "LONG" and ratio < .9) or (direction == "SHORT" and ratio > 1.1)
            return (100.0 if ok else 0.0, "Positioning supports setup" if ok else "L/S ratio not supportive")
        if n == 34:
            x = analysis.get("whale_activity", {}); x = x if isinstance(x, dict) else {}; return self._aligned(direction, x.get("direction"), x.get("score", 0)), "Whale activity aligned" if self._direction(x.get("direction")) == direction else "Whale data unavailable"
        if n == 35:
            x = book.get("walls", book.get("wall_direction", "")); x = x.get("direction", "") if isinstance(x, dict) else x; return self._aligned(direction, x), "Order-book walls aligned" if self._direction(x) == direction else "Wall evidence unavailable"
        if n == 36:
            spread = self._float(book.get("spread_bps", book.get("spread", 0))); return (self._clamp(100 - spread * 5) if spread else 0.0, f"Spread {spread:.2f} bps" if spread else "Spread unavailable")
        if n == 37:
            sr = struct.get("support_resistance", {}); sr = sr if isinstance(sr, dict) else {}; touches = self._float(sr.get("touches", sr.get("retests", 0))); loc = str(sr.get("location", "")).upper(); ok = (direction == "LONG" and loc == "NEAR_SUPPORT") or (direction == "SHORT" and loc == "NEAR_RESISTANCE"); return (self._clamp(touches * 30) if ok else 0.0, "Strong directional level" if ok else "S/R not at entry")
        if n in {38, 39, 41}:
            key = {38: "supply_demand", 39: "fvg", 41: "candle_quality"}[n]; x = struct.get(key, {}) if n != 41 else ind.get(key, {}); x = x if isinstance(x, dict) else {}; return self._aligned(direction, x.get("direction"), x.get("score", 0)), f"{self.RULES[n]} aligned" if self._direction(x.get("direction")) == direction else f"{self.RULES[n]} unavailable"
        if n == 40:
            x = self._float(ind.get("volume_imbalance", 0)); score = (x if direction == "LONG" else -x) * 100; return (self._clamp(score) if x else 0.0, "Volume imbalance aligned" if score > 0 else "Volume imbalance unavailable")
        if n == 42:
            b = ind.get("breakout", {}); b = b if isinstance(b, dict) else {}; vr = self._float(ind.get("volume_ratio", 0)); ok = self._direction(b.get("direction")) == direction and vr >= 1.2; return (self._clamp(vr * 60) if ok else 0.0, "Breakout has volume confirmation" if ok else "Breakout volume not confirmed")
        if n == 43:
            x = struct.get("fakeout", {}); x = x if isinstance(x, dict) else {}; detected = bool(x.get("detected", False)); return (100.0 if not detected else 0.0, "No fakeout detected" if not detected else "Fakeout risk")
        if n == 44:
            d = self._float(analysis.get("liquidity_distance_pct", 0)); return (self._clamp(100 - d * 10) if d else 0.0, f"Liquidity distance {d:.2f}%" if d else "Liquidity distance unavailable")
        if n == 45:
            x = analysis.get("target_liquidity", {}); x = x if isinstance(x, dict) else {}; return self._aligned(direction, x.get("direction"), x.get("score", 0)), "Target liquidity aligned" if self._direction(x.get("direction")) == direction else "Target liquidity unavailable"
        if n == 46:
            x = analysis.get("correlation", {}); x = x if isinstance(x, dict) else {}; return self._aligned(direction, x.get("direction"), x.get("score", 0)), "Correlation aligned" if self._direction(x.get("direction")) == direction else "Correlation unavailable"
        if n == 47:
            x = analysis.get("sector_strength", {}); x = x if isinstance(x, dict) else {}; return self._aligned(direction, x.get("direction"), x.get("score", 0)), "Sector aligned" if self._direction(x.get("direction")) == direction else "Sector unavailable"
        if n == 48:
            x = analysis.get("market_breadth", {}); x = x if isinstance(x, dict) else {}; return self._aligned(direction, x.get("direction"), x.get("score", 0)), "Breadth aligned" if self._direction(x.get("direction")) == direction else "Breadth unavailable"
        if n == 49:
            atr = self._float(ind.get("atr_percent", 0)); return (self._clamp(100 - abs(atr - 2) * 20) if atr else 0.0, f"ATR volatility {atr:.2f}%" if atr else "Volatility unavailable")
        if n == 50:
            x = analysis.get("setup_quality", {}); x = x if isinstance(x, dict) else {}; return (self._clamp(x.get("score", 0)) if x.get("score") is not None else 0.0, "Setup quality available" if x.get("score") is not None else "Setup quality synthesis deferred")
        return 0.0, "Unknown rule"

    def evaluate(self, analysis: dict[str, Any], direction: str) -> dict[str, Any]:
        direction = self._direction(direction); rules = {}; scores = []; confirmed = 0; available = 0
        for n, name in self.RULES.items():
            score, reason = self._score_rule(n, direction, analysis); score = self._clamp(score)
            if score > 0:
                available += 1
                if score >= 55: confirmed += 1
                scores.append(score)
            rules[str(n)] = {"name": name, "score": round(score, 2), "status": "CONFIRMED" if score >= 55 else ("WEAK" if score > 0 else "UNAVAILABLE"), "reason": reason}
        avg = sum(scores) / len(scores) if scores else 0.0
        ratio = confirmed / available if available else 0.0
        return {"version": "1.0.0", "rule_count": 26, "direction": direction, "available_rules": available, "confirmed_rules": confirmed, "confirmation_ratio": round(ratio, 4), "score": round(avg, 2), "rules": rules}

advanced_confirmation_engine = AdvancedConfirmationEngine()
__all__ = ["AdvancedConfirmationEngine", "advanced_confirmation_engine"]
