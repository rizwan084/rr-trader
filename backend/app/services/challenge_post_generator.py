from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.config import settings


class ChallengePostGenerator:
    """Build transparent, challenge-only community posts from validated signals."""

    @staticmethod
    def _f(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _price(value: Any) -> str:
        n = ChallengePostGenerator._f(value)
        if n <= 0:
            return "-"
        if n >= 1000:
            return f"{n:,.2f}"
        if n >= 1:
            return f"{n:,.4f}"
        if n >= 0.01:
            return f"{n:.6f}"
        return f"{n:.8f}"

    @staticmethod
    def _coin(symbol: str) -> str:
        value = str(symbol or "").upper().strip()
        return value[:-4] if value.endswith("USDT") else value

    @staticmethod
    def _point_summary(analysis: dict[str, Any]) -> list[str]:
        result = analysis.get("24_point_analysis") or {}
        points = result.get("points") if isinstance(result, dict) else {}
        if not isinstance(points, dict):
            return []
        output: list[str] = []
        for number in sorted(points, key=lambda x: int(x) if str(x).isdigit() else 999):
            point = points.get(number)
            if not isinstance(point, dict):
                continue
            name = str(point.get("name") or "Point " + str(number))
            status = str(point.get("status") or "UNKNOWN")
            direction = str(point.get("direction") or "NEUTRAL")
            output.append(f"{number}. {name}: {status} ({direction})")
        return output

    def build(self, analysis: dict[str, Any], *, balance: float | None = None) -> dict[str, Any]:
        if not isinstance(analysis, dict):
            raise ValueError("analysis must be a dictionary")
        direction = str(analysis.get("direction") or "NEUTRAL").upper()
        if direction not in {"LONG", "SHORT"}:
            raise ValueError("Challenge post requires a LONG or SHORT signal")
        if not bool(analysis.get("publishable")):
            raise ValueError("Challenge post requires a publishable RR Trader signal")

        symbol = str(analysis.get("symbol") or "").upper()
        coin = self._coin(symbol)
        confidence = self._f(analysis.get("confidence"))
        rr = self._f(analysis.get("risk_reward"))
        reasons = [str(x) for x in (analysis.get("reasons") or []) if str(x).strip()]
        failures = [str(x) for x in (analysis.get("critical_failures") or []) if str(x).strip()]
        news = analysis.get("news") or analysis.get("news_context") or {}
        if not isinstance(news, dict):
            news = {"status": "UNKNOWN", "summary": str(news)}
        news_status = str(news.get("status") or "UNKNOWN").upper()
        news_summary = str(news.get("summary") or news.get("headline") or "News provider not connected.")

        body_lines = [
            f"Challenge Update: ${coin} {direction}",
            "",
            f"RR Trader selected this setup after the challenge risk gates passed. Confidence is {confidence:.0f}% and the planned R:R is {rr:.2f}.",
            f"Entry: {self._price(analysis.get('entry'))}",
            f"TP1: {self._price(analysis.get('tp1'))} | TP2: {self._price(analysis.get('tp2'))} | TP3: {self._price(analysis.get('tp3'))}",
            f"SL: {self._price(analysis.get('stop_loss'))}",
            f"Risk: {settings.pro_risk_per_trade_percent:.2f}% of challenge equity",
            f"Max leverage: {settings.max_leverage}x",
            "",
            "Why this signal passed:",
        ]
        body_lines.extend(f"- {reason}" for reason in reasons[:8])
        body_lines.extend([
            "",
            f"News/Event check: {news_status} — {news_summary}",
            f"Challenge balance: {self._price(balance) if balance is not None else 'current dashboard balance'}",
            "",
            "This is the challenge trade only. Risk is controlled first; no setup is posted when the required gates fail.",
        ])

        return {
            "success": True,
            "mode": "challenge",
            "publishable": True,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "symbol": symbol,
            "coin": coin,
            "direction": direction,
            "confidence": round(confidence, 2),
            "risk_reward": round(rr, 4),
            "entry": analysis.get("entry"),
            "stop_loss": analysis.get("stop_loss"),
            "tp1": analysis.get("tp1"),
            "tp2": analysis.get("tp2"),
            "tp3": analysis.get("tp3"),
            "risk_percent": settings.pro_risk_per_trade_percent,
            "max_leverage": settings.max_leverage,
            "reasons": reasons,
            "critical_failures": failures,
            "news": news,
            "point_summary": self._point_summary(analysis),
            "post": "\n".join(body_lines),
        }


challenge_post_generator = ChallengePostGenerator()

__all__ = ["ChallengePostGenerator", "challenge_post_generator"]
