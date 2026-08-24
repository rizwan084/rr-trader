from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class TradePlan:
    symbol: str
    side: str
    entry: float
    stop_loss: float
    take_profits: tuple[float, ...]
    confidence: float = 0.0
    risk_reward: float = 0.0
    risk_percent: float = 1.0
    leverage: int = 1
    setup: str = ""
    signal_id: str = ""

    @property
    def direction_side(self) -> str:
        return "BUY" if self.side.upper() == "LONG" else "SELL"

    @property
    def close_side(self) -> str:
        return "SELL" if self.direction_side == "BUY" else "BUY"


@dataclass
class ExecutionResult:
    success: bool
    mode: str
    symbol: str
    side: str
    status: str
    message: str = ""
    entry_order: dict[str, Any] = field(default_factory=dict)
    protective_orders: list[dict[str, Any]] = field(default_factory=list)
    risk: dict[str, Any] = field(default_factory=dict)
    signal_id: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ChallengeState:
    starting_balance: float = 50.0
    target_balance: float = 1000.0
    current_balance: float = 50.0
    peak_balance: float = 50.0
    daily_start_balance: float = 50.0
    daily_pnl: float = 0.0
    consecutive_losses: int = 0
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    net_r: float = 0.0

    @property
    def progress_percent(self) -> float:
        if self.target_balance <= self.starting_balance:
            return 0.0
        return max(0.0, min(100.0, (self.current_balance - self.starting_balance) / (self.target_balance - self.starting_balance) * 100.0))

    @property
    def drawdown_percent(self) -> float:
        if self.peak_balance <= 0:
            return 0.0
        return max(0.0, (self.peak_balance - self.current_balance) / self.peak_balance * 100.0)

    def snapshot(self) -> dict[str, Any]:
        return {
            "starting_balance": self.starting_balance,
            "target_balance": self.target_balance,
            "current_balance": self.current_balance,
            "progress_percent": round(self.progress_percent, 2),
            "peak_balance": self.peak_balance,
            "drawdown_percent": round(self.drawdown_percent, 2),
            "daily_start_balance": self.daily_start_balance,
            "daily_pnl": round(self.daily_pnl, 8),
            "consecutive_losses": self.consecutive_losses,
            "total_trades": self.total_trades,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": round(self.wins / (self.wins + self.losses) * 100.0, 2) if self.wins + self.losses else 0.0,
            "net_r": round(self.net_r, 4),
        }
