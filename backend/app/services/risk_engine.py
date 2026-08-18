from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RiskDecision:
    """
    Result of the RR Trader risk engine.

    The risk engine is separate from market-direction
    analysis. It can veto a trade even when the market
    score is high.
    """

    allowed: bool
    reason: str
    risk_per_trade_percent: float
    position_size: float
    portfolio_exposure_percent: float
    failures: list[str]


class RiskEngine:
    """
    RR Trader risk-control engine foundation.

    Responsibilities:
    - Position sizing
    - Account-risk control
    - Portfolio exposure
    - Maximum open positions
    - Stop-based risk calculation

    Live execution is disabled during development.
    """

    def __init__(
        self,
        risk_per_trade_percent: float = 1.0,
        max_portfolio_exposure_percent: float = 10.0,
        max_open_positions: int = 5,
    ) -> None:

        self.risk_per_trade_percent = float(
            risk_per_trade_percent
        )

        self.max_portfolio_exposure_percent = float(
            max_portfolio_exposure_percent
        )

        self.max_open_positions = int(
            max_open_positions
        )

    # =====================================================
    # SAFE FLOAT
    # =====================================================

    @staticmethod
    def _float(
        value: Any,
        default: float = 0.0,
    ) -> float:

        try:
            return float(value)

        except (
            TypeError,
            ValueError,
        ):
            return default

    # =====================================================
    # POSITION SIZE
    # =====================================================

    def calculate_position_size(
        self,
        *,
        account_balance: float,
        entry: float,
        stop_loss: float,
        risk_percent: float | None = None,
    ) -> float:

        balance = self._float(
            account_balance
        )

        entry_price = self._float(
            entry
        )

        stop_price = self._float(
            stop_loss
        )

        risk_pct = (
            self.risk_per_trade_percent
            if risk_percent is None
            else self._float(
                risk_percent
            )
        )

        if balance <= 0:
            return 0.0

        if entry_price <= 0:
            return 0.0

        if stop_price <= 0:
            return 0.0

        stop_distance = abs(
            entry_price - stop_price
        )

        if stop_distance <= 0:
            return 0.0

        risk_amount = (
            balance
            * risk_pct
            / 100.0
        )

        position_size = (
            risk_amount
            / stop_distance
        )

        return round(
            max(
                0.0,
                position_size,
            ),
            8,
        )

    # =====================================================
    # PORTFOLIO CHECK
    # =====================================================

    def evaluate(
        self,
        *,
        account_balance: float,
        entry: float,
        stop_loss: float,
        current_open_positions: int = 0,
        portfolio_exposure_percent: float = 0.0,
        risk_percent: float | None = None,
    ) -> RiskDecision:

        failures: list[str] = []

        balance = self._float(
            account_balance
        )

        entry_price = self._float(
            entry
        )

        stop_price = self._float(
            stop_loss
        )

        exposure = self._float(
            portfolio_exposure_percent
        )

        open_positions = int(
            max(
                0,
                current_open_positions,
            )
        )

        risk_pct = (
            self.risk_per_trade_percent
            if risk_percent is None
            else self._float(
                risk_percent
            )
        )

        # -------------------------------------------------
        # Account balance
        # -------------------------------------------------

        if balance <= 0:
            failures.append(
                "INVALID_ACCOUNT_BALANCE"
            )

        # -------------------------------------------------
        # Entry / stop
        # -------------------------------------------------

        if entry_price <= 0:
            failures.append(
                "INVALID_ENTRY"
            )

        if stop_price <= 0:
            failures.append(
                "INVALID_STOP"
            )

        if (
            entry_price > 0
            and stop_price > 0
            and entry_price == stop_price
        ):
            failures.append(
                "ZERO_STOP_DISTANCE"
            )

        # -------------------------------------------------
        # Risk percentage
        # -------------------------------------------------

        if risk_pct <= 0:
            failures.append(
                "INVALID_RISK_PERCENT"
            )

        if risk_pct > 5.0:
            failures.append(
                "EXCESSIVE_PER_TRADE_RISK"
            )

        # -------------------------------------------------
        # Portfolio exposure
        # -------------------------------------------------

        if (
            exposure
            >= self.max_portfolio_exposure_percent
        ):
            failures.append(
                "PORTFOLIO_EXPOSURE_LIMIT"
            )

        # -------------------------------------------------
        # Open position count
        # -------------------------------------------------

        if (
            open_positions
            >= self.max_open_positions
        ):
            failures.append(
                "MAX_OPEN_POSITIONS"
            )

        # -------------------------------------------------
        # Position size
        # -------------------------------------------------

        position_size = (
            self.calculate_position_size(
                account_balance=balance,
                entry=entry_price,
                stop_loss=stop_price,
                risk_percent=risk_pct,
            )
        )

        if position_size <= 0:
            failures.append(
                "POSITION_SIZE_ZERO"
            )

        allowed = (
            len(failures) == 0
        )

        if allowed:
            reason = (
                "Risk gates passed."
            )
        else:
            reason = (
                "Risk gates failed."
            )

        return RiskDecision(
            allowed=allowed,
            reason=reason,
            risk_per_trade_percent=risk_pct,
            position_size=position_size,
            portfolio_exposure_percent=exposure,
            failures=failures,
        )

    # =====================================================
    # STATUS
    # =====================================================

    def status(
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
            "live_trading": False,
            "status": "risk_engine_ready",
        }


risk_engine = RiskEngine()


__all__ = [
    "RiskDecision",
    "RiskEngine",
    "risk_engine",
]
