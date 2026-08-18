from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RiskProfile:
    """
    RR Trader account-risk configuration.

    Risk is deliberately kept separate from market
    direction and signal confidence.
    """

    risk_per_trade_percent: float = 1.0

    max_portfolio_exposure_percent: float = 10.0

    max_open_positions: int = 5

    max_daily_loss_percent: float = 3.0

    max_position_size_percent: float = 25.0

    max_leverage: float = 5.0

    allow_new_trades: bool = True

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def to_dict(
        self,
    ) -> dict[str, Any]:

        return {
            "risk_per_trade_percent": (
                self.risk_per_trade_percent
            ),
            "max_portfolio_exposure_percent": (
                self.max_portfolio_exposure_percent
            ),
            "max_open_positions": (
                self.max_open_positions
            ),
            "max_daily_loss_percent": (
                self.max_daily_loss_percent
            ),
            "max_position_size_percent": (
                self.max_position_size_percent
            ),
            "max_leverage": (
                self.max_leverage
            ),
            "allow_new_trades": (
                self.allow_new_trades
            ),
            "metadata": dict(
                self.metadata
            ),
        }


@dataclass
class RiskCheck:
    """
    Result of one individual risk gate.
    """

    name: str

    passed: bool

    value: Any = None

    limit: Any = None

    reason: str = ""

    critical: bool = True

    def to_dict(
        self,
    ) -> dict[str, Any]:

        return {
            "name": self.name,
            "passed": self.passed,
            "value": self.value,
            "limit": self.limit,
            "reason": self.reason,
            "critical": self.critical,
        }


@dataclass
class RiskAssessment:
    """
    Complete risk-engine result.

    A failed critical check can veto an otherwise
    strong market setup.
    """

    allowed: bool = False

    position_size: float = 0.0

    risk_amount: float = 0.0

    risk_percent: float = 0.0

    portfolio_exposure_percent: float = 0.0

    checks: list[RiskCheck] = field(
        default_factory=list
    )

    failures: list[str] = field(
        default_factory=list
    )

    warnings: list[str] = field(
        default_factory=list
    )

    reason: str = ""

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def to_dict(
        self,
    ) -> dict[str, Any]:

        return {
            "allowed": self.allowed,
            "position_size": (
                self.position_size
            ),
            "risk_amount": (
                self.risk_amount
            ),
            "risk_percent": (
                self.risk_percent
            ),
            "portfolio_exposure_percent": (
                self.portfolio_exposure_percent
            ),
            "checks": [
                check.to_dict()
                for check in self.checks
            ],
            "failures": list(
                self.failures
            ),
            "warnings": list(
                self.warnings
            ),
            "reason": self.reason,
            "metadata": dict(
                self.metadata
            ),
        }


__all__ = [
    "RiskProfile",
    "RiskCheck",
    "RiskAssessment",
]
