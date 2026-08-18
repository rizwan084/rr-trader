from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TradeDecision:
    """
    Final trade-gate decision.

    The TradeEngine does not invent market direction.
    It evaluates a completed analysis and applies
    hard safety/risk gates.
    """

    decision: str
    direction: str
    trade_score: float
    reason: str
    critical_failures: list[str]


class TradeEngine:
    """
    RR Trader trade engine foundation.

    Execution mode:
        PAPER ONLY

    Live trading is intentionally disabled during
    development.

    The engine is designed around:

        Market Analysis
             ↓
        Confidence
             ↓
        Risk Gates
             ↓
        Trade Decision
    """

    PAPER_MODE = "paper"

    def __init__(
        self,
        min_confidence: float = 85.0,
        min_risk_reward: float = 2.0,
        max_spread_percent: float = 0.10,
    ) -> None:

        self.min_confidence = float(
            min_confidence
        )

        self.min_risk_reward = float(
            min_risk_reward
        )

        self.max_spread_percent = float(
            max_spread_percent
        )

        self.open_positions: list[
            dict[str, Any]
        ] = []

        self.closed_trades: list[
            dict[str, Any]
        ] = []

    # =====================================================
    # STATUS
    # =====================================================

    def get_status(
        self,
    ) -> dict[str, Any]:

        return {
            "mode": self.PAPER_MODE,
            "live_trading": False,
            "open_positions": len(
                self.open_positions
            ),
            "closed_trades": len(
                self.closed_trades
            ),
            "status": "paper_ready",
        }

    # =====================================================
    # CONFIG
    # =====================================================

    def get_config(
        self,
    ) -> dict[str, Any]:

        return {
            "mode": self.PAPER_MODE,
            "live_trading": False,
            "min_confidence": (
                self.min_confidence
            ),
            "min_risk_reward": (
                self.min_risk_reward
            ),
            "max_spread_percent": (
                self.max_spread_percent
            ),
        }

    # =====================================================
    # HELPERS
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

    @staticmethod
    def _direction(
        value: Any,
    ) -> str:

        direction = (
            str(
                value
                or "NEUTRAL"
            )
            .upper()
            .strip()
        )

        if direction not in {
            "LONG",
            "SHORT",
            "NEUTRAL",
        }:
            return "NEUTRAL"

        return direction

    # =====================================================
    # CRITICAL GATES
    # =====================================================

    def _critical_failures(
        self,
        signal: dict[str, Any],
    ) -> list[str]:

        failures: list[str] = []

        direction = self._direction(
            signal.get(
                "direction"
            )
        )

        confidence = self._float(
            signal.get(
                "confidence",
                0,
            )
        )

        risk_reward = self._float(
            signal.get(
                "risk_reward",
                0,
            )
        )

        spread = self._float(
            signal.get(
                "spread_percent",
                0,
            )
        )

        mtf_aligned = signal.get(
            "mtf_aligned",
            True,
        )

        stale = bool(
            signal.get(
                "stale",
                False,
            )
        )

        stop_valid = signal.get(
            "stop_valid",
            None,
        )

        if direction not in {
            "LONG",
            "SHORT",
        }:
            failures.append(
                "INVALID_DIRECTION"
            )

        if confidence < (
            self.min_confidence
        ):
            failures.append(
                "LOW_CONFIDENCE"
            )

        if risk_reward < (
            self.min_risk_reward
        ):
            failures.append(
                "INSUFFICIENT_RISK_REWARD"
            )

        if spread > (
            self.max_spread_percent
        ):
            failures.append(
                "EXCESSIVE_SPREAD"
            )

        if mtf_aligned is False:
            failures.append(
                "MTF_CONFLICT"
            )

        if stale:
            failures.append(
                "STALE_SIGNAL"
            )

        if stop_valid is False:
            failures.append(
                "INVALID_STOP"
            )

        if bool(
            signal.get(
                "portfolio_risk_blocked",
                False,
            )
        ):
            failures.append(
                "PORTFOLIO_RISK_BLOCKED"
            )

        if bool(
            signal.get(
                "execution_blocked",
                False,
            )
        ):
            failures.append(
                "EXECUTION_BLOCKED"
            )

        if str(
            signal.get(
                "news_risk",
                "",
            )
        ).upper() == "HIGH":
            failures.append(
                "HIGH_NEWS_RISK"
            )

        return failures

    # =====================================================
    # TRADE EVALUATION
    # =====================================================

    def evaluate_trade(
        self,
        signal: dict[str, Any],
    ) -> dict[str, Any]:

        direction = self._direction(
            signal.get(
                "direction"
            )
        )

        confidence = self._float(
            signal.get(
                "confidence",
                0,
            )
        )

        failures = (
            self._critical_failures(
                signal
            )
        )

        # -------------------------------------------------
        # Trade quality score
        # -------------------------------------------------

        rr = self._float(
            signal.get(
                "risk_reward",
                0,
            )
        )

        spread = self._float(
            signal.get(
                "spread_percent",
                0,
            )
        )

        trade_score = min(
            100.0,
            max(
                0.0,
                (
                    confidence
                    * 0.70
                )
                + (
                    min(
                        rr / 3.0,
                        1.0,
                    )
                    * 20.0
                )
                + (
                    max(
                        0.0,
                        1.0
                        - min(
                            spread
                            / max(
                                self.max_spread_percent,
                                0.000001,
                            ),
                            1.0,
                        ),
                    )
                    * 10.0
                ),
            ),
        )

        trade_score = round(
            trade_score,
            2,
        )

        # -------------------------------------------------
        # Final decision
        # -------------------------------------------------

        if failures:

            decision = "NO_TRADE"

            reason = (
                "Critical trade gates failed."
            )

        elif trade_score >= 90.0:

            decision = (
                "EXECUTE_CANDIDATE"
            )

            reason = (
                "All critical gates passed "
                "in paper-trading mode."
            )

        else:

            decision = "WATCH"

            reason = (
                "Setup is valid but trade "
                "quality is below execution "
                "candidate threshold."
            )

        return {
            "success": True,
            "decision": decision,
            "direction": direction,
            "trade_score": trade_score,
            "scanner_confidence": (
                confidence
            ),
            "passed_confirmations": max(
                0,
                int(
                    signal.get(
                        "passed_confirmations",
                        0,
                    )
                ),
            ),
            "total_confirmations": max(
                0,
                int(
                    signal.get(
                        "total_confirmations",
                        24,
                    )
                ),
            ),
            "critical_failures": failures,
            "reason": reason,
            "mode": self.PAPER_MODE,
            "live_trading": False,
        }

    # =====================================================
    # PAPER OPEN
    # =====================================================

    def open_paper_trade(
        self,
        signal: dict[str, Any],
    ) -> dict[str, Any]:

        evaluation = self.evaluate_trade(
            signal
        )

        if evaluation["decision"] != (
            "EXECUTE_CANDIDATE"
        ):
            return {
                "success": False,
                "opened": False,
                "evaluation": evaluation,
            }

        position = {
            "symbol": str(
                signal.get(
                    "symbol",
                    "",
                )
            ).upper(),
            "direction": self._direction(
                signal.get(
                    "direction"
                )
            ),
            "entry": signal.get(
                "entry"
            ),
            "stop_loss": signal.get(
                "stop_loss"
            ),
            "tp1": signal.get(
                "tp1"
            ),
            "tp2": signal.get(
                "tp2"
            ),
            "tp3": signal.get(
                "tp3"
            ),
            "confidence": signal.get(
                "confidence",
                0,
            ),
            "status": "OPEN",
        }

        self.open_positions.append(
            position
        )

        return {
            "success": True,
            "opened": True,
            "mode": self.PAPER_MODE,
            "position": position,
            "evaluation": evaluation,
        }

    # =====================================================
    # OPEN POSITIONS
    # =====================================================

    def get_open_positions(
        self,
    ) -> list[dict[str, Any]]:

        return list(
            self.open_positions
        )

    # =====================================================
    # CLOSED TRADES
    # =====================================================

    def get_closed_trades(
        self,
    ) -> list[dict[str, Any]]:

        return list(
            self.closed_trades
        )

    # =====================================================
    # RESET
    # =====================================================

    def reset_daily_stats(
        self,
    ) -> dict[str, Any]:

        return {
            "success": True,
            "status": (
                "daily_stats_reset"
            ),
            "mode": self.PAPER_MODE,
        }


default_trade_engine = TradeEngine()


__all__ = [
    "TradeEngine",
    "TradeDecision",
    "default_trade_engine",
]
