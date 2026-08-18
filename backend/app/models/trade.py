from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Trade:
    """
    RR Trader paper-trade model.

    A Trade represents an execution created by the
    Trade Engine after the analysis and risk gates
    have been evaluated.
    """

    symbol: str
    market: str

    direction: str = "NEUTRAL"

    status: str = "OPEN"

    entry: float | None = None
    exit_price: float | None = None

    stop_loss: float | None = None

    tp1: float | None = None
    tp2: float | None = None
    tp3: float | None = None

    quantity: float = 0.0

    risk_amount: float = 0.0
    risk_reward: float = 0.0

    pnl: float = 0.0
    pnl_percent: float = 0.0

    confidence: float = 0.0

    open_time: str | None = None
    close_time: str | None = None

    close_reason: str | None = None

    reasons: list[str] = field(
        default_factory=list
    )

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
            "status": self.status.upper(),
            "entry": self.entry,
            "exit_price": self.exit_price,
            "stop_loss": self.stop_loss,
            "tp1": self.tp1,
            "tp2": self.tp2,
            "tp3": self.tp3,
            "quantity": self.quantity,
            "risk_amount": self.risk_amount,
            "risk_reward": self.risk_reward,
            "pnl": self.pnl,
            "pnl_percent": self.pnl_percent,
            "confidence": self.confidence,
            "open_time": self.open_time,
            "close_time": self.close_time,
            "close_reason": self.close_reason,
            "reasons": list(
                self.reasons
            ),
            "metadata": dict(
                self.metadata
            ),
        }


__all__ = [
    "Trade",
]
