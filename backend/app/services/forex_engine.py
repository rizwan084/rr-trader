from __future__ import annotations

from typing import Any
import math

import httpx

from app.core.config import settings


class ForexEngine:
    """MT5-bridge backed Forex/Gold market intelligence.

    The bridge is intentionally external so the FastAPI service can run on
    Linux/Render while MetaTrader 5 remains on a Windows/VPS terminal.
    """

    DEFAULT_SYMBOLS = (
        "XAUUSD",
        "EURUSD",
        "GBPUSD",
        "USDJPY",
        "AUDUSD",
        "USDCAD",
        "USDCHF",
        "NZDUSD",
    )
    DEFAULT_TIMEFRAMES = ("1m", "3m", "5m", "15m")

    def __init__(self) -> None:
        self.bridge_url = str(getattr(settings, "mt5_bridge_url", "") or "").strip().rstrip("/")
        self.bridge_token = str(getattr(settings, "mt5_bridge_token", "") or "").strip()
        self.primary_symbol = str(getattr(settings, "forex_primary_symbol", "XAUUSD") or "XAUUSD").upper()
        raw = str(getattr(settings, "forex_timeframes", "1m,3m,5m,15m") or "1m,3m,5m,15m")
        self.timeframes = tuple(x.strip() for x in raw.split(",") if x.strip()) or self.DEFAULT_TIMEFRAMES
        self.symbols = self.DEFAULT_SYMBOLS
        self.timeout = max(5.0, float(getattr(settings, "request_timeout", 30) or 30))
        self.min_rr = max(1.1, float(getattr(settings, "min_risk_reward", 1.1) or 1.1))

    def status(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.bridge_url),
            "configured": bool(self.bridge_url and self.bridge_token),
            "bridge": "MT5" if self.bridge_url else None,
            "primary_symbol": self.primary_symbol,
            "symbols": list(self.symbols),
            "timeframes": list(self.timeframes),
            "minimum_rr": self.min_rr,
            "mode": "LIVE" if self.bridge_url else "NOT_CONFIGURED",
        }

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.bridge_token:
            headers["Authorization"] = f"Bearer {self.bridge_token}"
            headers["X-MT5-Bridge-Token"] = self.bridge_token
        return headers

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if not self.bridge_url:
            raise RuntimeError("MT5 bridge is not configured. Set MT5_BRIDGE_URL and MT5_BRIDGE_TOKEN.")
        url = f"{self.bridge_url}/{path.lstrip('/')}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, headers=self._headers(), params=params or {})
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _rows(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [x for x in payload if isinstance(x, dict)]
        if isinstance(payload, dict):
            for key in ("candles", "bars", "rates", "data", "items"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [x for x in value if isinstance(x, dict)]
        return []

    @staticmethod
    def _number(row: dict[str, Any], *keys: str) -> float | None:
        for key in keys:
            value = row.get(key)
            try:
                number = float(value)
                if math.isfinite(number):
                    return number
            except (TypeError, ValueError):
                continue
        return None

    def _analyze_rows(self, symbol: str, timeframe: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        if len(rows) < 20:
            return {"symbol": symbol, "timeframe": timeframe, "direction": "NO TRADE", "confidence": 0, "reason": "Insufficient MT5 candles."}
        closes = [self._number(r, "close", "c") for r in rows]
        highs = [self._number(r, "high", "h") for r in rows]
        lows = [self._number(r, "low", "l") for r in rows]
        closes = [x for x in closes if x is not None]
        highs = [x for x in highs if x is not None]
        lows = [x for x in lows if x is not None]
        if len(closes) < 20 or len(highs) < 20 or len(lows) < 20:
            return {"symbol": symbol, "timeframe": timeframe, "direction": "NO TRADE", "confidence": 0, "reason": "Invalid MT5 candle data."}
        price = closes[-1]
        fast = sum(closes[-9:]) / 9
        slow = sum(closes[-20:]) / 20
        recent_high = max(highs[-20:])
        recent_low = min(lows[-20:])
        span = max(recent_high - recent_low, price * 0.00001)
        momentum = (price - closes[-6]) / max(abs(closes[-6]), 1e-12)
        bullish = price > fast > slow and momentum > 0
        bearish = price < fast < slow and momentum < 0
        direction = "LONG" if bullish else "SHORT" if bearish else "NO TRADE"
        score = 50
        if direction != "NO TRADE":
            score += 15
            score += 10 if abs(momentum) > 0.0005 else 0
            score += 10 if abs(price - fast) / price < 0.003 else 0
        else:
            score = 35
        score = min(95, max(0, score))
        risk = span * 0.18
        if direction == "LONG":
            entry = price
            sl = max(recent_low, entry - risk)
            risk_distance = max(entry - sl, price * 0.0001)
            tp1 = entry + risk_distance * self.min_rr
            tp2 = entry + risk_distance * 1.8
            tp3 = entry + risk_distance * 2.5
        elif direction == "SHORT":
            entry = price
            sl = min(recent_high, entry + risk)
            risk_distance = max(sl - entry, price * 0.0001)
            tp1 = entry - risk_distance * self.min_rr
            tp2 = entry - risk_distance * 1.8
            tp3 = entry - risk_distance * 2.5
        else:
            entry = sl = tp1 = tp2 = tp3 = price
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "price": price,
            "direction": direction,
            "confidence": score,
            "entry": entry,
            "stop_loss": sl,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "risk_reward": self.min_rr if direction != "NO TRADE" else 0,
            "trend": "BULLISH" if bullish else "BEARISH" if bearish else "MIXED",
            "support": recent_low,
            "resistance": recent_high,
            "confirmation": ["EMA-style trend alignment", "short-term momentum", "20-candle structure"] if direction != "NO TRADE" else ["No aligned trend"],
        }

    async def analyze(self, symbol: str | None = None, timeframe: str | None = None, limit: int = 200) -> dict[str, Any]:
        symbol = (symbol or self.primary_symbol).upper()
        timeframe = timeframe or self.timeframes[-1]
        payload = await self._get("candles", {"symbol": symbol, "timeframe": timeframe, "limit": max(50, min(limit, 500))})
        rows = self._rows(payload)
        result = self._analyze_rows(symbol, timeframe, rows)
        result["market"] = "FOREX"
        result["source"] = "MT5"
        return result

    async def multi_timeframe(self, symbol: str | None = None, limit: int = 200) -> dict[str, Any]:
        symbol = (symbol or self.primary_symbol).upper()
        analyses = []
        for timeframe in self.timeframes:
            try:
                analyses.append(await self.analyze(symbol, timeframe, limit))
            except Exception as exc:
                analyses.append({"symbol": symbol, "timeframe": timeframe, "direction": "NO DATA", "confidence": 0, "error": str(exc)})
        valid = [x for x in analyses if x.get("direction") in {"LONG", "SHORT"}]
        long_votes = sum(1 for x in valid if x.get("direction") == "LONG")
        short_votes = sum(1 for x in valid if x.get("direction") == "SHORT")
        direction = "LONG" if long_votes > short_votes and long_votes >= 2 else "SHORT" if short_votes > long_votes and short_votes >= 2 else "NO TRADE"
        confidence = round(sum(float(x.get("confidence", 0)) for x in valid) / len(valid)) if valid else 0
        return {
            "success": True,
            "market": "FOREX",
            "symbol": symbol,
            "primary": symbol == self.primary_symbol,
            "direction": direction,
            "confidence": confidence,
            "timeframes": analyses,
            "source": "MT5",
            "minimum_rr": self.min_rr,
        }

    async def watchlist(self) -> dict[str, Any]:
        results = []
        for symbol in self.symbols:
            try:
                results.append(await self.multi_timeframe(symbol, 120))
            except Exception as exc:
                results.append({"symbol": symbol, "direction": "NO DATA", "confidence": 0, "error": str(exc)})
        return {"success": True, "market": "FOREX", "primary_symbol": self.primary_symbol, "results": results}


forex_engine = ForexEngine()
