from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class SignalRecord:
    """
    Stored RR Trader signal record.

    Signal memory is kept separate from the scanner,
    confidence engine, and trade engine so historical
    signals can later be used for performance analysis,
    AI context, and validation.
    """

    symbol: str
    market: str
    direction: str
    confidence: float

    entry: float | None = None
    stop_loss: float | None = None
    tp1: float | None = None
    tp2: float | None = None
    tp3: float | None = None

    status: str = "OPEN"

    created_at: str = field(
        default_factory=lambda: (
            datetime.now(
                timezone.utc
            ).isoformat()
        )
    )

    closed_at: str | None = None

    result: str | None = None

    pnl_percent: float | None = None

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
            "symbol": self.symbol,
            "market": self.market,
            "direction": self.direction,
            "confidence": self.confidence,
            "entry": self.entry,
            "stop_loss": self.stop_loss,
            "tp1": self.tp1,
            "tp2": self.tp2,
            "tp3": self.tp3,
            "status": self.status,
            "created_at": self.created_at,
            "closed_at": self.closed_at,
            "result": self.result,
            "pnl_percent": self.pnl_percent,
            "reasons": list(
                self.reasons
            ),
            "metadata": dict(
                self.metadata
            ),
        }


class SignalMemory:
    """
    In-memory signal store for the foundation phase.

    Persistent database storage will be added later.
    """

    def __init__(
        self,
        max_records: int = 5000,
    ) -> None:

        self.max_records = max(
            100,
            int(
                max_records
            ),
        )

        self._signals: list[
            SignalRecord
        ] = []

    # =====================================================
    # ADD SIGNAL
    # =====================================================

    def add(
        self,
        signal: SignalRecord,
    ) -> SignalRecord:

        self._signals.append(
            signal
        )

        if len(
            self._signals
        ) > self.max_records:

            self._signals = (
                self._signals[
                    -self.max_records:
                ]
            )

        return signal

    # =====================================================
    # CREATE FROM DICT
    # =====================================================

    def add_dict(
        self,
        data: dict[str, Any],
    ) -> SignalRecord:

        record = SignalRecord(
            symbol=str(
                data.get(
                    "symbol",
                    "",
                )
            ).upper(),
            market=str(
                data.get(
                    "market",
                    "futures",
                )
            ).lower(),
            direction=str(
                data.get(
                    "direction",
                    "NEUTRAL",
                )
            ).upper(),
            confidence=float(
                data.get(
                    "confidence",
                    0,
                )
                or 0
            ),
            entry=data.get(
                "entry"
            ),
            stop_loss=data.get(
                "stop_loss"
            ),
            tp1=data.get(
                "tp1"
            ),
            tp2=data.get(
                "tp2"
            ),
            tp3=data.get(
                "tp3"
            ),
            status=str(
                data.get(
                    "status",
                    "OPEN",
                )
            ).upper(),
            reasons=list(
                data.get(
                    "reasons",
                    [],
                )
                or []
            ),
            metadata=dict(
                data.get(
                    "metadata",
                    {},
                )
                or {}
            ),
        )

        return self.add(
            record
        )

    # =====================================================
    # GET ALL
    # =====================================================

    def all(
        self,
    ) -> list[dict[str, Any]]:

        return [
            item.to_dict()
            for item in self._signals
        ]

    # =====================================================
    # RECENT
    # =====================================================

    def recent(
        self,
        limit: int = 50,
    ) -> list[dict[str, Any]]:

        safe_limit = max(
            1,
            min(
                int(limit),
                self.max_records,
            ),
        )

        return [
            item.to_dict()
            for item in (
                self._signals[
                    -safe_limit:
                ]
            )
        ]

    # =====================================================
    # FILTER BY SYMBOL
    # =====================================================

    def by_symbol(
        self,
        symbol: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:

        normalized = str(
            symbol
        ).upper()

        matches = [
            item.to_dict()
            for item in self._signals
            if item.symbol.upper()
            == normalized
        ]

        return matches[
            -max(
                1,
                int(limit),
            ):
        ]

    # =====================================================
    # FILTER BY MARKET
    # =====================================================

    def by_market(
        self,
        market: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:

        normalized = str(
            market
        ).lower()

        matches = [
            item.to_dict()
            for item in self._signals
            if item.market.lower()
            == normalized
        ]

        return matches[
            -max(
                1,
                int(limit),
            ):
        ]

    # =====================================================
    # OPEN SIGNALS
    # =====================================================

    def open_signals(
        self,
        limit: int = 100,
    ) -> list[dict[str, Any]]:

        matches = [
            item.to_dict()
            for item in self._signals
            if item.status.upper()
            == "OPEN"
        ]

        return matches[
            -max(
                1,
                int(limit),
            ):
        ]

    # =====================================================
    # CLOSE SIGNAL
    # =====================================================

    def close_signal(
        self,
        symbol: str,
        *,
        result: str,
        pnl_percent: float | None = None,
    ) -> bool:

        normalized = str(
            symbol
        ).upper()

        for item in reversed(
            self._signals
        ):

            if (
                item.symbol.upper()
                == normalized
                and item.status.upper()
                == "OPEN"
            ):

                item.status = "CLOSED"

                item.closed_at = (
                    datetime.now(
                        timezone.utc
                    ).isoformat()
                )

                item.result = str(
                    result
                ).upper()

                item.pnl_percent = (
                    pnl_percent
                )

                return True

        return False

    # =====================================================
    # CLEAR
    # =====================================================

    def clear(
        self,
    ) -> None:

        self._signals.clear()

    # =====================================================
    # STATUS
    # =====================================================

    def status(
        self,
    ) -> dict[str, Any]:

        open_count = sum(
            1
            for item in self._signals
            if item.status.upper()
            == "OPEN"
        )

        closed_count = (
            len(self._signals)
            - open_count
        )

        return {
            "total_records": len(
                self._signals
            ),
            "open_signals": open_count,
            "closed_signals": closed_count,
            "max_records": self.max_records,
            "storage": "memory",
            "persistent_database": False,
        }


signal_memory = SignalMemory()


__all__ = [
    "SignalRecord",
    "SignalMemory",
    "signal_memory",
]
