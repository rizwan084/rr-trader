from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid


# ============================================================
# TIME
# ============================================================

def utc_now() -> str:
    """Return current UTC time in ISO format."""
    return datetime.now(timezone.utc).isoformat()


# ============================================================
# STORED SIGNAL
# ============================================================

@dataclass
class StoredSignal:
    """
    RR Trader persistent-style signal memory record.

    Stores:
    - Signal direction
    - Entry
    - Stop loss
    - TP1 / TP2 / TP3
    - Current price
    - TP/SL hit status
    - Result
    - Monitoring information
    - AI analysis
    """

    id: str

    symbol: str
    market: str
    timeframe: str

    signal: str
    confidence: float

    entry: Optional[float]
    stop_loss: Optional[float]

    tp1: Optional[float]
    tp2: Optional[float]
    tp3: Optional[float]

    status: str = "OPEN"

    tp1_hit: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False
    sl_hit: bool = False

    current_price: Optional[float] = None
    last_checked_price: Optional[float] = None

    result: Optional[str] = None

    created_at: str = ""
    updated_at: str = ""

    tp1_hit_at: Optional[str] = None
    tp2_hit_at: Optional[str] = None
    tp3_hit_at: Optional[str] = None
    sl_hit_at: Optional[str] = None

    closed_at: Optional[str] = None

    ai_analysis: Optional[str] = None

    notes: Optional[List[str]] = None

    def __post_init__(self) -> None:

        if self.notes is None:
            self.notes = []

        now = utc_now()

        if not self.created_at:
            self.created_at = now

        if not self.updated_at:
            self.updated_at = now

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ============================================================
# SIGNAL MEMORY
# ============================================================

class SignalMemory:
    """
    RR Trader signal memory.

    This version is designed for:

    Signal
       ↓
    Store
       ↓
    Monitor
       ↓
    TP1 / TP2 / TP3 / SL
       ↓
    AI result analysis
       ↓
    Telegram notification

    Current storage is in-memory.
    Later it can be moved to PostgreSQL/Supabase.
    """

    def __init__(self) -> None:
        self._signals: Dict[str, StoredSignal] = {}

    # ========================================================
    # CREATE SIGNAL
    # ========================================================

    def create_signal(
        self,
        symbol: str,
        market: str,
        timeframe: str,
        signal: str,
        confidence: float,
        entry: Optional[float],
        stop_loss: Optional[float],
        targets: Optional[List[float]] = None,
        notes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:

        targets = targets or []

        tp1 = targets[0] if len(targets) > 0 else None
        tp2 = targets[1] if len(targets) > 1 else None
        tp3 = targets[2] if len(targets) > 2 else None

        signal_id = str(uuid.uuid4())

        record = StoredSignal(
            id=signal_id,

            symbol=symbol.upper().replace("/", ""),
            market=market.lower(),
            timeframe=timeframe,

            signal=signal.upper(),
            confidence=float(confidence),

            entry=entry,
            stop_loss=stop_loss,

            tp1=tp1,
            tp2=tp2,
            tp3=tp3,

            notes=notes or [],
        )

        self._signals[signal_id] = record

        return record.to_dict()

    # ========================================================
    # GET SIGNAL
    # ========================================================

    def get_signal(
        self,
        signal_id: str,
    ) -> Optional[Dict[str, Any]]:

        signal = self._signals.get(signal_id)

        if signal is None:
            return None

        return signal.to_dict()

    # ========================================================
    # GET ALL SIGNALS
    # ========================================================

    def get_all_signals(self) -> List[Dict[str, Any]]:

        signals = [
            signal.to_dict()
            for signal in self._signals.values()
        ]

        signals.sort(
            key=lambda item: item.get(
                "created_at",
                "",
            ),
            reverse=True,
        )

        return signals

    # ========================================================
    # GET OPEN SIGNALS
    # ========================================================

    def get_open_signals(self) -> List[Dict[str, Any]]:

        signals = [
            signal.to_dict()
            for signal in self._signals.values()
            if signal.status == "OPEN"
        ]

        signals.sort(
            key=lambda item: item.get(
                "created_at",
                "",
            ),
            reverse=True,
        )

        return signals

    # ========================================================
    # UPDATE SIGNAL
    # ========================================================

    def update_signal(
        self,
        signal_id: str,
        **updates: Any,
    ) -> Optional[Dict[str, Any]]:

        signal = self._signals.get(signal_id)

        if signal is None:
            return None

        allowed_fields = {
            "status",
            "tp1_hit",
            "tp2_hit",
            "tp3_hit",
            "sl_hit",
            "current_price",
            "last_checked_price",
            "result",
            "updated_at",
            "tp1_hit_at",
            "tp2_hit_at",
            "tp3_hit_at",
            "sl_hit_at",
            "closed_at",
            "ai_analysis",
            "notes",
        }

        for key, value in updates.items():

            if key not in allowed_fields:
                continue

            setattr(
                signal,
                key,
                value,
            )

        signal.updated_at = utc_now()

        return signal.to_dict()

    # ========================================================
    # UPDATE CURRENT PRICE
    # ========================================================

    def update_price(
        self,
        signal_id: str,
        price: float,
    ) -> Optional[Dict[str, Any]]:

        signal = self._signals.get(signal_id)

        if signal is None:
            return None

        if signal.current_price is not None:
            signal.last_checked_price = (
                signal.current_price
            )

        signal.current_price = float(price)
        signal.updated_at = utc_now()

        return signal.to_dict()

    # ========================================================
    # MARK TP HIT
    # ========================================================

    def mark_tp_hit(
        self,
        signal_id: str,
        target: int,
        price: Optional[float] = None,
        note: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:

        signal = self._signals.get(signal_id)

        if signal is None:
            return None

        now = utc_now()

        if target == 1:

            if signal.tp1_hit:
                return signal.to_dict()

            signal.tp1_hit = True
            signal.tp1_hit_at = now

            result_note = "TP1 HIT"

        elif target == 2:

            if signal.tp2_hit:
                return signal.to_dict()

            signal.tp2_hit = True
            signal.tp2_hit_at = now

            result_note = "TP2 HIT"

        elif target == 3:

            if signal.tp3_hit:
                return signal.to_dict()

            signal.tp3_hit = True
            signal.tp3_hit_at = now

            result_note = "TP3 HIT"

        else:

            raise ValueError(
                "target must be 1, 2 or 3"
            )

        if price is not None:
            signal.current_price = float(price)

        signal.result = result_note

        if note:
            signal.notes.append(note)

        signal.notes.append(result_note)

        # TP3 completes the signal.
        if target == 3:

            signal.status = "WIN"
            signal.result = "TP3_HIT"
            signal.closed_at = now

        signal.updated_at = now

        return signal.to_dict()

    # ========================================================
    # MARK SL HIT
    # ========================================================

    def mark_sl_hit(
        self,
        signal_id: str,
        price: Optional[float] = None,
        note: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:

        signal = self._signals.get(signal_id)

        if signal is None:
            return None

        # Do not process SL twice.
        if signal.sl_hit:
            return signal.to_dict()

        now = utc_now()

        signal.sl_hit = True
        signal.status = "LOSS"
        signal.result = "SL_HIT"

        signal.sl_hit_at = now
        signal.closed_at = now
        signal.updated_at = now

        if price is not None:
            signal.current_price = float(price)

        signal.notes.append("SL HIT")

        if note:
            signal.notes.append(note)

        return signal.to_dict()

    # ========================================================
    # CLOSE SIGNAL
    # ========================================================

    def close_signal(
        self,
        signal_id: str,
        status: str = "CLOSED",
        note: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:

        signal = self._signals.get(signal_id)

        if signal is None:
            return None

        signal.status = status.upper()
        signal.closed_at = utc_now()
        signal.updated_at = utc_now()

        if note:
            signal.notes.append(note)

        return signal.to_dict()

    # ========================================================
    # AI ANALYSIS
    # ========================================================

    def save_ai_analysis(
        self,
        signal_id: str,
        analysis: str,
    ) -> Optional[Dict[str, Any]]:

        signal = self._signals.get(signal_id)

        if signal is None:
            return None

        signal.ai_analysis = analysis
        signal.updated_at = utc_now()

        return signal.to_dict()

    # ========================================================
    # FIND BY SYMBOL
    # ========================================================

    def find_by_symbol(
        self,
        symbol: str,
        market: Optional[str] = None,
    ) -> List[Dict[str, Any]]:

        symbol = symbol.upper().replace("/", "")

        results: List[Dict[str, Any]] = []

        for signal in self._signals.values():

            if signal.symbol != symbol:
                continue

            if (
                market is not None
                and signal.market != market.lower()
            ):
                continue

            results.append(
                signal.to_dict()
            )

        results.sort(
            key=lambda item: item.get(
                "created_at",
                "",
            ),
            reverse=True,
        )

        return results

    # ========================================================
    # PERFORMANCE
    # ========================================================

    def performance(self) -> Dict[str, Any]:

        signals = list(
            self._signals.values()
        )

        total = len(signals)

        tp1_hits = sum(
            signal.tp1_hit
            for signal in signals
        )

        tp2_hits = sum(
            signal.tp2_hit
            for signal in signals
        )

        tp3_hits = sum(
            signal.tp3_hit
            for signal in signals
        )

        sl_hits = sum(
            signal.sl_hit
            for signal in signals
        )

        open_count = sum(
            signal.status == "OPEN"
            for signal in signals
        )

        wins = sum(
            signal.status == "WIN"
            for signal in signals
        )

        losses = sum(
            signal.status == "LOSS"
            for signal in signals
        )

        closed_count = total - open_count

        win_rate = (
            (wins / closed_count) * 100
            if closed_count > 0
            else 0.0
        )

        return {
            "total_signals": total,
            "open_signals": open_count,
            "closed_signals": closed_count,
            "wins": wins,
            "losses": losses,
            "win_rate": round(
                win_rate,
                2,
            ),
            "tp1_hits": tp1_hits,
            "tp2_hits": tp2_hits,
            "tp3_hits": tp3_hits,
            "sl_hits": sl_hits,
        }


# ============================================================
# APPLICATION SINGLETON
# ============================================================

signal_memory = SignalMemory()


__all__ = [
    "StoredSignal",
    "SignalMemory",
    "signal_memory",
]
