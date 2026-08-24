from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.config import settings


@dataclass(frozen=True)
class ProRiskDecision:
    allowed: bool
    score: float
    reason: str
    failures: list[str]
    warnings: list[str]
    risk_percent: float
    position_size: float
    risk_amount: float
    rr: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "score": round(self.score, 2),
            "reason": self.reason,
            "failures": self.failures,
            "warnings": self.warnings,
            "risk_percent": self.risk_percent,
            "position_size": self.position_size,
            "risk_amount": self.risk_amount,
            "risk_reward": self.rr,
        }


class ProRiskEngine:
    """Final quality gate used before a signal can become a trade."""

    def __init__(
        self,
        *,
        min_confidence: float = 90.0,
        min_rr: float = 2.0,
        max_risk_percent: float = 1.0,
        max_open_positions: int = 3,
        max_daily_loss_percent: float = 2.0,
        max_consecutive_losses: int = 3,
    ) -> None:
        self.min_confidence = min_confidence
        self.min_rr = min_rr
        self.max_risk_percent = max_risk_percent
        self.max_open_positions = max_open_positions
        self.max_daily_loss_percent = max_daily_loss_percent
        self.max_consecutive_losses = max_consecutive_losses

    @staticmethod
    def _f(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _s(value: Any) -> str:
        return str(value or "").upper().strip()

    def evaluate(
        self,
        signal: dict[str, Any],
        *,
        account_balance: float,
        open_positions: int = 0,
        daily_pnl_percent: float = 0.0,
        consecutive_losses: int = 0,
        risk_percent: float | None = None,
    ) -> ProRiskDecision:
        failures: list[str] = []
        warnings: list[str] = []

        side = self._s(signal.get("direction") or signal.get("decision") or signal.get("side"))
        entry = self._f(signal.get("entry") or signal.get("entry_price"))
        stop = self._f(signal.get("stop_loss") or signal.get("sl"))
        confidence = self._f(signal.get("confidence"))
        rr = self._f(signal.get("risk_reward") or signal.get("rr"))
        risk_pct = self.max_risk_percent if risk_percent is None else self._f(risk_percent)

        if side not in {"LONG", "SHORT"}:
            failures.append("INVALID_DIRECTION")
        if entry <= 0 or stop <= 0:
            failures.append("INVALID_ENTRY_OR_STOP")
        elif side == "LONG" and stop >= entry:
            failures.append("LONG_STOP_NOT_BELOW_ENTRY")
        elif side == "SHORT" and stop <= entry:
            failures.append("SHORT_STOP_NOT_ABOVE_ENTRY")

        if confidence < self.min_confidence:
            failures.append("CONFIDENCE_BELOW_PRO_THRESHOLD")
        if rr < self.min_rr:
            failures.append("RISK_REWARD_BELOW_PRO_THRESHOLD")
        if risk_pct <= 0 or risk_pct > self.max_risk_percent:
            failures.append("RISK_PER_TRADE_LIMIT")
        if open_positions >= self.max_open_positions:
            failures.append("MAX_OPEN_POSITIONS")
        if daily_pnl_percent <= -self.max_daily_loss_percent:
            failures.append("DAILY_LOSS_LIMIT")
        if consecutive_losses >= self.max_consecutive_losses:
            failures.append("LOSS_STREAK_COOLDOWN")

        setup_obj = signal.get("setup")
        if isinstance(setup_obj, dict):
            setup = self._s(setup_obj.get("setup"))
        else:
            setup = self._s(setup_obj or signal.get("setup_type"))

        structure = signal.get("structure")
        if not isinstance(structure, dict):
            structure = {}
        sr = structure.get("support_resistance")
        if not isinstance(sr, dict):
            sr = {}

        location = self._s(signal.get("structure_location") or signal.get("location") or sr.get("location"))

        mtf_obj = signal.get("multi_timeframe") or signal.get("mtf")
        if isinstance(mtf_obj, dict):
            mtf_confirmed = bool(mtf_obj.get("publishable_mtf", False))
        else:
            mtf_confirmed = signal.get("mtf_confirmation", signal.get("mtf_confirmed"))

        indicators = signal.get("indicators")
        if not isinstance(indicators, dict):
            indicators = {}
        volume_ratio = self._f(signal.get("volume_ratio"), self._f(indicators.get("volume_ratio"), 1.0))
        momentum = self._f(signal.get("momentum_score"), self._f(indicators.get("momentum"), 50.0))

        if setup in {"NONE", "RANGE_COMPRESSION", "MID_RANGE", ""}:
            failures.append("BAD_TRADE_LOCATION")
        if location in {"MID_RANGE", "UNKNOWN", ""}:
            warnings.append("STRUCTURE_LOCATION_NOT_EXPLICITLY_CONFIRMED")
        if mtf_confirmed is False:
            failures.append("MTF_CONFLICT")
        if volume_ratio < 0.8:
            failures.append("WEAK_VOLUME")
        if momentum < 45:
            warnings.append("WEAK_MOMENTUM")

        score = 0.0
        score += min(confidence, 100.0) * 0.45
        score += min(max(rr / max(self.min_rr, 0.01), 0.0), 1.5) * 20.0
        score += min(max(volume_ratio, 0.0), 1.5) / 1.5 * 15.0
        score += min(max(momentum, 0.0), 100.0) * 0.20
        score = min(score, 100.0)

        risk_amount = max(account_balance, 0.0) * risk_pct / 100.0
        position_size = risk_amount / abs(entry - stop) if entry > 0 and stop > 0 and abs(entry - stop) > 0 else 0.0

        allowed = not failures
        return ProRiskDecision(
            allowed=allowed,
            score=score,
            reason="PRO_TRADE_APPROVED" if allowed else "PRO_TRADE_REJECTED",
            failures=failures,
            warnings=warnings,
            risk_percent=risk_pct,
            position_size=round(position_size, 12),
            risk_amount=round(risk_amount, 8),
            rr=rr,
        )

    def status(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "min_confidence": self.min_confidence,
            "min_risk_reward": self.min_rr,
            "max_risk_per_trade_percent": self.max_risk_percent,
            "max_open_positions": self.max_open_positions,
            "max_daily_loss_percent": self.max_daily_loss_percent,
            "max_consecutive_losses": self.max_consecutive_losses,
        }


pro_risk_engine = ProRiskEngine(
    min_confidence=settings.pro_min_confidence,
    min_rr=settings.pro_min_risk_reward,
    max_risk_percent=settings.pro_risk_per_trade_percent,
    max_open_positions=settings.pro_max_open_positions,
    max_daily_loss_percent=settings.pro_max_daily_loss_percent,
    max_consecutive_losses=settings.pro_max_consecutive_losses,
)
