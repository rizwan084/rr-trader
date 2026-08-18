from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional


# =========================================================
# TRADE ENGINE
# =========================================================
#
# IMPORTANT:
# This version is PAPER-TRADING ONLY.
#
# It does NOT place real Binance orders.
# It only decides whether a signal is strong enough
# to open a simulated position and manages that position.
#
# Later we can connect the same engine to Binance Testnet
# and, after testing, build a separately controlled live
# execution layer.
#


@dataclass
class TradeConfig:
    """
    Safe default trading configuration.
    """

    enabled: bool = True

    mode: str = "paper"

    min_confidence: float = 90.0

    risk_per_trade_percent: float = 0.5

    max_open_positions: int = 2

    max_daily_loss_percent: float = 2.0

    minimum_risk_reward: float = 1.5

    allow_long: bool = True

    allow_short: bool = True

    require_entry: bool = True

    require_stop_loss: bool = True

    require_take_profit: bool = True


@dataclass
class PaperPosition:
    """
    Represents one simulated open position.
    """

    id: str

    symbol: str

    market: str

    direction: str

    entry_price: float

    quantity: float

    stop_loss: float

    tp1: float

    tp2: float

    tp3: float

    confidence: float

    risk_amount: float

    opened_at: str

    status: str = "OPEN"

    realized_pnl: float = 0.0

    tp1_hit: bool = False

    tp2_hit: bool = False

    tp3_hit: bool = False


class TradeEngine:
    """
    RR Trader paper-trading decision and position engine.

    Responsibilities:

    - Validate signals
    - Apply confidence filters
    - Apply risk rules
    - Calculate paper position size
    - Open simulated trades
    - Monitor simulated trades
    - Detect SL / TP hits
    - Close simulated positions
    - Track paper balance
    - Track daily PnL

    This class DOES NOT send orders to Binance.
    """

    def __init__(
        self,
        starting_balance: float = 1000.0,
        config: Optional[TradeConfig] = None,
    ) -> None:

        self.config = (
            config
            or TradeConfig()
        )

        self.starting_balance = float(
            starting_balance
        )

        self.balance = float(
            starting_balance
        )

        self.positions: Dict[
            str,
            PaperPosition,
        ] = {}

        self.closed_trades: list[
            Dict[str, Any]
        ] = []

        self.daily_realized_pnl = 0.0

        self.last_signal: Optional[
            Dict[str, Any]
        ] = None

    # =====================================================
    # HELPERS
    # =====================================================

    @staticmethod
    def _safe_float(
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
    def _now() -> str:

        return datetime.now(
            timezone.utc
        ).isoformat()

    @staticmethod
    def _normalize_symbol(
        symbol: str,
    ) -> str:

        cleaned = (
            str(symbol)
            .upper()
            .replace("/", "")
            .replace("-", "")
            .strip()
        )

        if not cleaned.endswith(
            "USDT"
        ):

            cleaned = (
                f"{cleaned}USDT"
            )

        return cleaned

    # =====================================================
    # CONFIG
    # =====================================================

    def update_config(
        self,
        **kwargs: Any,
    ) -> Dict[str, Any]:

        for key, value in kwargs.items():

            if hasattr(
                self.config,
                key,
            ):

                setattr(
                    self.config,
                    key,
                    value,
                )

        return asdict(
            self.config
        )

    def get_config(
        self,
    ) -> Dict[str, Any]:

        return asdict(
            self.config
        )

    # =====================================================
    # CURRENT STATE
    # =====================================================

    def get_balance(
        self,
    ) -> float:

        return round(
            self.balance,
            8,
        )

    def get_open_positions(
        self,
    ) -> list[Dict[str, Any]]:

        return [
            asdict(position)
            for position in self.positions.values()
        ]

    def get_closed_trades(
        self,
    ) -> list[Dict[str, Any]]:

        return list(
            self.closed_trades
        )

    def get_status(
        self,
    ) -> Dict[str, Any]:

        return {
            "enabled": self.config.enabled,
            "mode": self.config.mode,
            "balance": self.get_balance(),
            "starting_balance": (
                self.starting_balance
            ),
            "daily_realized_pnl": round(
                self.daily_realized_pnl,
                8,
            ),
            "daily_loss_percent": round(
                self._daily_loss_percent(),
                4,
            ),
            "open_positions": len(
                self.positions
            ),
            "max_open_positions": (
                self.config.max_open_positions
            ),
            "last_signal": self.last_signal,
        }

    # =====================================================
    # RISK
    # =====================================================

    def _daily_loss_percent(
        self,
    ) -> float:

        if self.starting_balance <= 0:
            return 0.0

        loss = min(
            0.0,
            self.daily_realized_pnl,
        )

        return abs(
            loss
        ) / self.starting_balance * 100.0

    def _daily_loss_limit_reached(
        self,
    ) -> bool:

        return (
            self._daily_loss_percent()
            >= self.config.max_daily_loss_percent
        )

    def _risk_amount(
        self,
    ) -> float:

        return (
            self.balance
            * (
                self.config.risk_per_trade_percent
                / 100.0
            )
        )

    # =====================================================
    # SIGNAL VALIDATION
    # =====================================================

    def validate_signal(
        self,
        signal: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Decide whether a scanner signal is allowed
        to become a paper trade.
        """

        if not self.config.enabled:

            return {
                "allowed": False,
                "reason": "Trade engine is disabled.",
            }

        if not isinstance(
            signal,
            dict,
        ):

            return {
                "allowed": False,
                "reason": "Invalid signal payload.",
            }

        symbol = self._normalize_symbol(
            signal.get(
                "symbol",
                "",
            )
        )

        direction = str(
            signal.get(
                "direction",
                "NEUTRAL",
            )
        ).upper().strip()

        confidence = self._safe_float(
            signal.get(
                "confidence",
                0,
            )
        )

        entry = self._safe_float(
            signal.get(
                "entry",
                0,
            )
        )

        stop_loss = self._safe_float(
            signal.get(
                "stop_loss",
                0,
            )
        )

        tp1 = self._safe_float(
            signal.get(
                "tp1",
                0,
            )
        )

        tp2 = self._safe_float(
            signal.get(
                "tp2",
                0,
            )
        )

        tp3 = self._safe_float(
            signal.get(
                "tp3",
                0,
            )
        )

        risk_reward = self._safe_float(
            signal.get(
                "risk_reward",
                0,
            )
        )

        # -------------------------------------------------
        # BASIC
        # -------------------------------------------------

        if not symbol:

            return {
                "allowed": False,
                "reason": "Missing symbol.",
            }

        if direction not in {
            "LONG",
            "SHORT",
        }:

            return {
                "allowed": False,
                "reason": (
                    "Direction must be LONG or SHORT."
                ),
            }

        # -------------------------------------------------
        # DIRECTION
        # -------------------------------------------------

        if (
            direction == "LONG"
            and not self.config.allow_long
        ):

            return {
                "allowed": False,
                "reason": "LONG trading is disabled.",
            }

        if (
            direction == "SHORT"
            and not self.config.allow_short
        ):

            return {
                "allowed": False,
                "reason": "SHORT trading is disabled.",
            }

        # -------------------------------------------------
        # CONFIDENCE
        # -------------------------------------------------

        if (
            confidence
            < self.config.min_confidence
        ):

            return {
                "allowed": False,
                "reason": (
                    f"Confidence {confidence:.2f}% "
                    f"is below required "
                    f"{self.config.min_confidence:.2f}%."
                ),
            }

        # -------------------------------------------------
        # RISK LIMIT
        # -------------------------------------------------

        if self._daily_loss_limit_reached():

            return {
                "allowed": False,
                "reason": (
                    "Maximum daily loss limit "
                    "has been reached."
                ),
            }

        # -------------------------------------------------
        # MAX OPEN POSITIONS
        # -------------------------------------------------

        if (
            len(self.positions)
            >= self.config.max_open_positions
        ):

            return {
                "allowed": False,
                "reason": (
                    "Maximum open positions reached."
                ),
            }

        # -------------------------------------------------
        # DUPLICATE SYMBOL
        # -------------------------------------------------

        for position in self.positions.values():

            if (
                position.symbol
                == symbol
            ):

                return {
                    "allowed": False,
                    "reason": (
                        f"{symbol} already has "
                        "an open position."
                    ),
                }

        # -------------------------------------------------
        # REQUIRED LEVELS
        # -------------------------------------------------

        if (
            self.config.require_entry
            and entry <= 0
        ):

            return {
                "allowed": False,
                "reason": "Entry price is missing.",
            }

        if (
            self.config.require_stop_loss
            and stop_loss <= 0
        ):

            return {
                "allowed": False,
                "reason": "Stop loss is missing.",
            }

        if (
            self.config.require_take_profit
            and (
                tp1 <= 0
                or tp2 <= 0
                or tp3 <= 0
            )
        ):

            return {
                "allowed": False,
                "reason": (
                    "One or more take-profit "
                    "levels are missing."
                ),
            }

        # -------------------------------------------------
        # LEVEL DIRECTION VALIDATION
        # -------------------------------------------------

        if direction == "LONG":

            if not (
                stop_loss < entry
            ):

                return {
                    "allowed": False,
                    "reason": (
                        "For LONG, stop loss "
                        "must be below entry."
                    ),
                }

            if not (
                tp1 > entry
                and tp2 > entry
                and tp3 > entry
            ):

                return {
                    "allowed": False,
                    "reason": (
                        "For LONG, all take-profit "
                        "levels must be above entry."
                    ),
                }

        else:

            if not (
                stop_loss > entry
            ):

                return {
                    "allowed": False,
                    "reason": (
                        "For SHORT, stop loss "
                        "must be above entry."
                    ),
                }

            if not (
                tp1 < entry
                and tp2 < entry
                and tp3 < entry
            ):

                return {
                    "allowed": False,
                    "reason": (
                        "For SHORT, all take-profit "
                        "levels must be below entry."
                    ),
                }

        # -------------------------------------------------
        # RISK / REWARD
        # -------------------------------------------------

        if (
            risk_reward > 0
            and risk_reward
            < self.config.minimum_risk_reward
        ):

            return {
                "allowed": False,
                "reason": (
                    f"R:R {risk_reward:.2f} "
                    f"is below required "
                    f"{self.config.minimum_risk_reward:.2f}."
                ),
            }

        return {
            "allowed": True,
            "reason": "Signal passed all trade rules.",
            "symbol": symbol,
            "direction": direction,
            "confidence": confidence,
            "entry": entry,
            "stop_loss": stop_loss,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "risk_reward": risk_reward,
        }

    # =====================================================
    # POSITION SIZE
    # =====================================================

    def calculate_quantity(
        self,
        entry_price: float,
        stop_loss: float,
    ) -> Dict[str, float]:
        """
        Position sizing based on configured percentage risk.

        Example:

        Balance = $1000
        Risk = 0.5%
        Risk amount = $5

        If entry-to-SL distance is $2,
        quantity = 2.5 units.
        """

        entry_price = self._safe_float(
            entry_price
        )

        stop_loss = self._safe_float(
            stop_loss
        )

        if (
            entry_price <= 0
            or stop_loss <= 0
        ):

            return {
                "risk_amount": 0.0,
                "stop_distance": 0.0,
                "stop_distance_percent": 0.0,
                "quantity": 0.0,
                "notional": 0.0,
            }

        risk_amount = self._risk_amount()

        stop_distance = abs(
            entry_price
            - stop_loss
        )

        if stop_distance <= 0:

            return {
                "risk_amount": 0.0,
                "stop_distance": 0.0,
                "stop_distance_percent": 0.0,
                "quantity": 0.0,
                "notional": 0.0,
            }

        quantity = (
            risk_amount
            / stop_distance
        )

        notional = (
            quantity
            * entry_price
        )

        stop_distance_percent = (
            stop_distance
            / entry_price
            * 100.0
        )

        return {
            "risk_amount": round(
                risk_amount,
                8,
            ),
            "stop_distance": round(
                stop_distance,
                8,
            ),
            "stop_distance_percent": round(
                stop_distance_percent,
                6,
            ),
            "quantity": round(
                quantity,
                8,
            ),
            "notional": round(
                notional,
                8,
            ),
        }

    # =====================================================
    # OPEN PAPER POSITION
    # =====================================================

    def open_paper_trade(
        self,
        signal: Dict[str, Any],
    ) -> Dict[str, Any]:

        validation = (
            self.validate_signal(
                signal
            )
        )

        if not validation.get(
            "allowed",
            False,
        ):

            return {
                "success": False,
                "opened": False,
                "reason": validation[
                    "reason"
                ],
            }

        symbol = validation[
            "symbol"
        ]

        direction = validation[
            "direction"
        ]

        confidence = validation[
            "confidence"
        ]

        entry = validation[
            "entry"
        ]

        stop_loss = validation[
            "stop_loss"
        ]

        tp1 = validation[
            "tp1"
        ]

        tp2 = validation[
            "tp2"
        ]

        tp3 = validation[
            "tp3"
        ]

        sizing = (
            self.calculate_quantity(
                entry_price=entry,
                stop_loss=stop_loss,
            )
        )

        quantity = sizing[
            "quantity"
        ]

        if quantity <= 0:

            return {
                "success": False,
                "opened": False,
                "reason": (
                    "Calculated position size "
                    "is zero."
                ),
            }

        position_id = (
            f"{symbol}-"
            f"{direction}-"
            f"{int(datetime.now().timestamp() * 1000)}"
        )

        position = PaperPosition(
            id=position_id,
            symbol=symbol,
            market=str(
                signal.get(
                    "market",
                    "futures",
                )
            ),
            direction=direction,
            entry_price=entry,
            quantity=quantity,
            stop_loss=stop_loss,
            tp1=tp1,
            tp2=tp2,
            tp3=tp3,
            confidence=confidence,
            risk_amount=sizing[
                "risk_amount"
            ],
            opened_at=self._now(),
        )

        self.positions[
            position_id
        ] = position

        self.last_signal = dict(
            signal
        )

        return {
            "success": True,
            "opened": True,
            "mode": "paper",
            "position": asdict(
                position
            ),
            "sizing": sizing,
        }

    # =====================================================
    # POSITION UPDATE
    # =====================================================

    def update_position(
        self,
        position_id: str,
        current_price: float,
    ) -> Dict[str, Any]:

        position = self.positions.get(
            position_id
        )

        if position is None:

            return {
                "success": False,
                "reason": "Position not found.",
            }

        current_price = self._safe_float(
            current_price
        )

        if current_price <= 0:

            return {
                "success": False,
                "reason": "Invalid current price.",
            }

        # -------------------------------------------------
        # LONG POSITION
        # -------------------------------------------------

        if position.direction == "LONG":

            if (
                not position.tp1_hit
                and current_price
                >= position.tp1
            ):

                position.tp1_hit = True

            if (
                not position.tp2_hit
                and current_price
                >= position.tp2
            ):

                position.tp2_hit = True

            if (
                not position.tp3_hit
                and current_price
                >= position.tp3
            ):

                position.tp3_hit = True

                return self.close_position(
                    position_id=position_id,
                    exit_price=current_price,
                    reason="TP3",
                )

            if (
                current_price
                <= position.stop_loss
            ):

                return self.close_position(
                    position_id=position_id,
                    exit_price=current_price,
                    reason="STOP_LOSS",
                )

        # -------------------------------------------------
        # SHORT POSITION
        # -------------------------------------------------

        else:

            if (
                not position.tp1_hit
                and current_price
                <= position.tp1
            ):

                position.tp1_hit = True

            if (
                not position.tp2_hit
                and current_price
                <= position.tp2
            ):

                position.tp2_hit = True

            if (
                not position.tp3_hit
                and current_price
                <= position.tp3
            ):

                position.tp3_hit = True

                return self.close_position(
                    position_id=position_id,
                    exit_price=current_price,
                    reason="TP3",
                )

            if (
                current_price
                >= position.stop_loss
            ):

                return self.close_position(
                    position_id=position_id,
                    exit_price=current_price,
                    reason="STOP_LOSS",
                )

        return {
            "success": True,
            "closed": False,
            "position": asdict(
                position
            ),
        }

    # =====================================================
    # CLOSE POSITION
    # =====================================================

    def close_position(
        self,
        position_id: str,
        exit_price: float,
        reason: str = "MANUAL",
    ) -> Dict[str, Any]:

        position = self.positions.get(
            position_id
        )

        if position is None:

            return {
                "success": False,
                "reason": "Position not found.",
            }

        exit_price = self._safe_float(
            exit_price
        )

        if exit_price <= 0:

            return {
                "success": False,
                "reason": "Invalid exit price.",
            }

        # -------------------------------------------------
        # PNL
        # -------------------------------------------------

        if position.direction == "LONG":

            pnl = (
                exit_price
                - position.entry_price
            ) * position.quantity

        else:

            pnl = (
                position.entry_price
                - exit_price
            ) * position.quantity

        pnl = round(
            pnl,
            8,
        )

        position.realized_pnl = pnl
        position.status = "CLOSED"

        self.balance = round(
            self.balance + pnl,
            8,
        )

        self.daily_realized_pnl = round(
            self.daily_realized_pnl + pnl,
            8,
        )

        closed = asdict(
            position
        )

        closed[
            "exit_price"
        ] = exit_price

        closed[
            "close_reason"
        ] = reason

        closed[
            "closed_at"
        ] = self._now()

        self.closed_trades.append(
            closed
        )

        del self.positions[
            position_id
        ]

        return {
            "success": True,
            "closed": True,
            "pnl": pnl,
            "balance": self.get_balance(),
            "trade": closed,
        }

    # =====================================================
    # RESET DAILY STATS
    # =====================================================

    def reset_daily_stats(
        self,
    ) -> Dict[str, Any]:

        self.daily_realized_pnl = 0.0

        return {
            "success": True,
            "daily_realized_pnl": 0.0,
            "daily_loss_percent": 0.0,
        }


# =========================================================
# DEFAULT ENGINE
# =========================================================

default_trade_engine = TradeEngine(
    starting_balance=1000.0,
    config=TradeConfig(
        enabled=True,
        mode="paper",
        min_confidence=90.0,
        risk_per_trade_percent=0.5,
        max_open_positions=2,
        max_daily_loss_percent=2.0,
        minimum_risk_reward=1.5,
        allow_long=True,
        allow_short=True,
    ),
)


__all__ = [
    "TradeConfig",
    "PaperPosition",
    "TradeEngine",
    "default_trade_engine",
]
