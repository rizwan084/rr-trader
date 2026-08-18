from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RiskDecision:
    allowed: bool
    reason: str
    risk_per_trade_percent: float
    position_size: float
    risk_amount: float
    portfolio_exposure_percent: float
    failures: list[str]


class RiskEngine:
    """
    RR Trader Risk Engine.

    Responsibilities:
    - Position sizing
    - Stop validation
    - Risk / reward validation
    - Portfolio exposure
    - Open-position limits
    - Daily risk controls

    Live trading remains disabled.
    """

    def __init__(
        self,
        risk_per_trade_percent: float = 1.0,
        max_portfolio_exposure_percent: float = 10.0,
        max_open_positions: int = 5,
        max_daily_loss_percent: float = 3.0,
    ) -> None:

        self.risk_per_trade_percent = max(
            0.0,
            float(risk_per_trade_percent),
        )

        self.max_portfolio_exposure_percent = max(
            0.0,
            float(max_portfolio_exposure_percent),
        )

        self.max_open_positions = max(
            1,
            int(max_open_positions),
        )

        self.max_daily_loss_percent = max(
            0.0,
            float(max_daily_loss_percent),
        )

        self.daily_pnl_percent = 0.0

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
    # RISK AMOUNT
    # =====================================================

    def risk_amount(
        self,
        account_balance: float,
        risk_percent: float | None = None,
    ) -> float:

        balance = max(
            0.0,
            self._float(
                account_balance
            ),
        )

        risk_pct = (
            self.risk_per_trade_percent
            if risk_percent is None
            else self._float(
                risk_percent
            )
        )

        if balance <= 0 or risk_pct <= 0:
            return 0.0

        return round(
            balance
            * risk_pct
            / 100.0,
            8,
        )

    # =====================================================
    # POSITION SIZE
    # =====================================================

    def position_size(
        self,
        account_balance: float,
        entry: float,
        stop_loss: float,
        risk_percent: float | None = None,
    ) -> float:

        entry_price = self._float(
            entry
        )

        stop_price = self._float(
            stop_loss
        )

        if (
            account_balance <= 0
            or entry_price <= 0
            or stop_price <= 0
        ):
            return 0.0

        stop_distance = abs(
            entry_price
            - stop_price
        )

        if stop_distance <= 0:
            return 0.0

        risk_cash = self.risk_amount(
            account_balance,
            risk_percent,
        )

        return round(
            risk_cash
            / stop_distance,
            8,
        )

    # =====================================================
    # STOP VALIDATION
    # =====================================================

    def validate_stop_loss(
        self,
        direction: str,
        entry: float,
        stop_loss: float,
    ) -> dict[str, Any]:

        direction = str(
            direction
            or ""
        ).upper()

        entry_price = self._float(
            entry
        )

        stop_price = self._float(
            stop_loss
        )

        if (
            entry_price <= 0
            or stop_price <= 0
        ):

            return {
                "valid": False,
                "reason": "Invalid entry or stop loss.",
            }

        if direction == "LONG":

            valid = stop_price < entry_price

        elif direction == "SHORT":

            valid = stop_price > entry_price

        else:

            return {
                "valid": False,
                "reason": "Direction must be LONG or SHORT.",
            }

        return {
            "valid": valid,
            "reason": (
                "Stop loss is valid."
                if valid
                else "Stop loss is on the wrong side of entry."
            ),
        }

    # =====================================================
    # RISK / REWARD
    # =====================================================

    def calculate_risk_reward(
        self,
        entry: float,
        stop_loss: float,
        take_profit: float,
    ) -> float:

        entry_price = self._float(
            entry
        )

        stop_price = self._float(
            stop_loss
        )

        target_price = self._float(
            take_profit
        )

        if (
            entry_price <= 0
            or stop_price <= 0
            or target_price <= 0
        ):
            return 0.0

        risk = abs(
            entry_price
            - stop_price
        )

        reward = abs(
            target_price
            - entry_price
        )

        if risk <= 0:
            return 0.0

        return round(
            reward / risk,
            4,
        )

    # =====================================================
    # PORTFOLIO EXPOSURE
    # =====================================================

    def validate_exposure(
        self,
        account_balance: float,
        current_exposure_percent: float,
        new_exposure_percent: float,
    ) -> dict[str, Any]:

        _ = account_balance

        current = max(
            0.0,
            self._float(
                current_exposure_percent
            ),
        )

        new = max(
            0.0,
            self._float(
                new_exposure_percent
            ),
        )

        total = (
            current
            + new
        )

        valid = (
            total
            <= self.max_portfolio_exposure_percent
        )

        return {
            "valid": valid,
            "current_exposure_percent": current,
            "new_exposure_percent": new,
            "total_exposure_percent": total,
            "maximum_exposure_percent": (
                self.max_portfolio_exposure_percent
            ),
            "reason": (
                "Portfolio exposure is within limits."
                if valid
                else "Maximum portfolio exposure exceeded."
            ),
        }

    # =====================================================
    # OPEN POSITION LIMIT
    # =====================================================

    def validate_position_count(
        self,
        open_positions: int,
    ) -> dict[str, Any]:

        count = max(
            0,
            int(
                self._float(
                    open_positions
                )
            ),
        )

        valid = (
            count
            < self.max_open_positions
        )

        return {
            "valid": valid,
            "open_positions": count,
            "maximum_open_positions": (
                self.max_open_positions
            ),
            "reason": (
                "Position limit available."
                if valid
                else "Maximum open position limit reached."
            ),
        }

    # =====================================================
    # DAILY LOSS
    # =====================================================

    def validate_daily_loss(
        self,
    ) -> dict[str, Any]:

        valid = (
            self.daily_pnl_percent
            > -self.max_daily_loss_percent
        )

        return {
            "valid": valid,
            "daily_pnl_percent": (
                self.daily_pnl_percent
            ),
            "maximum_daily_loss_percent": (
                self.max_daily_loss_percent
            ),
            "reason": (
                "Daily loss limit is not breached."
                if valid
                else "Daily loss limit has been breached."
            ),
        }

    # =====================================================
    # MASTER EVALUATION
    # =====================================================

    def evaluate(
        self,
        *,
        account_balance: float,
        entry: float,
        stop_loss: float,
        current_open_positions: int = 0,
        portfolio_exposure_percent: float = 0.0,
        new_exposure_percent: float = 0.0,
        risk_percent: float | None = None,
        direction: str = "LONG",
        take_profit: float | None = None,
        minimum_risk_reward: float = 1.5,
    ) -> RiskDecision:

        failures: list[str] = []

        risk_pct = (
            self.risk_per_trade_percent
            if risk_percent is None
            else self._float(
                risk_percent
            )
        )

        balance = self._float(
            account_balance
        )

        entry_price = self._float(
            entry
        )

        stop_price = self._float(
            stop_loss
        )

        # -------------------------------------------------
        # Basic account
        # -------------------------------------------------

        if balance <= 0:
            failures.append(
                "INVALID_ACCOUNT_BALANCE"
            )

        if risk_pct <= 0:
            failures.append(
                "INVALID_RISK_PERCENT"
            )

        if risk_pct > 5.0:
            failures.append(
                "EXCESSIVE_PER_TRADE_RISK"
            )

        # -------------------------------------------------
        # Stop
        # -------------------------------------------------

        stop_result = (
            self.validate_stop_loss(
                direction=direction,
                entry=entry_price,
                stop_loss=stop_price,
            )
        )

        if not stop_result["valid"]:
            failures.append(
                "INVALID_STOP"
            )

        # -------------------------------------------------
        # Position count
        # -------------------------------------------------

        position_result = (
            self.validate_position_count(
                current_open_positions
            )
        )

        if not position_result["valid"]:
            failures.append(
                "MAX_OPEN_POSITIONS"
            )

        # -------------------------------------------------
        # Portfolio exposure
        # -------------------------------------------------

        exposure_result = (
            self.validate_exposure(
                account_balance=balance,
                current_exposure_percent=(
                    portfolio_exposure_percent
                ),
                new_exposure_percent=(
                    new_exposure_percent
                ),
            )
        )

        if not exposure_result["valid"]:
            failures.append(
                "PORTFOLIO_EXPOSURE_LIMIT"
            )

        # -------------------------------------------------
        # Daily loss
        # -------------------------------------------------

        daily_result = (
            self.validate_daily_loss()
        )

        if not daily_result["valid"]:
            failures.append(
                "DAILY_LOSS_LIMIT"
            )

        # -------------------------------------------------
        # Position size
        # -------------------------------------------------

        size = self.position_size(
            account_balance=balance,
            entry=entry_price,
            stop_loss=stop_price,
            risk_percent=risk_pct,
        )

        if size <= 0:
            failures.append(
                "POSITION_SIZE_ZERO"
            )

        risk_cash = self.risk_amount(
            balance,
            risk_pct,
        )

        # -------------------------------------------------
        # R:R
        # -------------------------------------------------

        rr = None

        if take_profit is not None:

            rr = self.calculate_risk_reward(
                entry=entry_price,
                stop_loss=stop_price,
                take_profit=take_profit,
            )

            if rr < minimum_risk_reward:
                failures.append(
                    "INSUFFICIENT_RISK_REWARD"
                )

        allowed = (
            len(failures) == 0
        )

        return RiskDecision(
            allowed=allowed,
            reason=(
                "All risk gates passed."
                if allowed
                else "One or more risk gates failed."
            ),
            risk_per_trade_percent=risk_pct,
            position_size=size,
            risk_amount=risk_cash,
            portfolio_exposure_percent=(
                exposure_result[
                    "total_exposure_percent"
                ]
            ),
            failures=failures,
        )

    # =====================================================
    # DAILY RESET
    # =====================================================

    def reset_daily_stats(
        self,
    ) -> dict[str, Any]:

        self.daily_pnl_percent = 0.0

        return {
            "success": True,
            "daily_pnl_percent": 0.0,
            "status": "daily_risk_reset",
        }

    # =====================================================
    # STATUS
    # =====================================================

    def status(
        self,
    ) -> dict[str, Any]:

        return {
            "enabled": True,
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
            "daily_pnl_percent": (
                self.daily_pnl_percent
            ),
            "live_trading": False,
        }


risk_engine = RiskEngine()


__all__ = [
    "RiskDecision",
    "RiskEngine",
    "risk_engine",
]
