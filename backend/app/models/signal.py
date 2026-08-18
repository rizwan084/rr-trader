from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Signal:
    """
    RR Trader trading signal model.

    A signal is produced by the analysis/confidence
    pipeline. It does not execute a trade by itself.
    """

    symbol: str
    market: str

    direction: str = "NEUTRAL"

    confidence: float = 0.0

    confirmation_percent: float = 0.0

    entry: float | None = None

    stop_loss: float | None = None

    tp1: float | None = None
    tp2: float | None = None
    tp3: float | None = None

    risk_reward: float = 0.0

    publishable: bool = False

    status: str = "NEW"

    reasons: list[str] = field(
        default_factory=list
    )

    critical_failures: list[str] = field(
        default_factory=list
    )

    multi_timeframe: dict[str, Any] = field(
        default_factory=dict
    )

    analysis_points: dict[str, Any] = field(
        default_factory=dict
    )

    timestamp: str | None = None

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def to_dict(
        self,
    ) -> dict[str, Any]:

        return {
            "success": True,
            "symbol": self.symbol.upper(),
            "market": self.market.lower(),
            "direction": self.direction.upper(),
            "confidence": round(
                float(self.confidence),
                2,
            ),
            "confirmation_percent": round(
                float(
                    self.confirmation_percent
                ),
                2,
            ),
            "entry": self.entry,
            "stop_loss": self.stop_loss,
            "tp1": self.tp1,
            "tp2": self.tp2,
            "tp3": self.tp3,
            "risk_reward": round(
                float(self.risk_reward),
                4,
            ),
            "publishable": self.publishable,
            "status": self.status,
            "reasons": list(
                self.reasons
            ),
            "critical_failures": list(
                self.critical_failures
            ),
            "multi_timeframe": dict(
                self.multi_timeframe
            ),
            "analysis_points": dict(
                self.analysis_points
            ),
            "timestamp": self.timestamp,
            "metadata": dict(
                self.metadata
            ),
        }


__all__ = [
    "Signal",
]
