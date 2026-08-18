from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TimeframeAnalysis:
    """
    Analysis result for one core timeframe.

    RR Trader core MTF:
    - 15m
    - 1h
    - 4h
    """

    timeframe: str

    direction: str = "NEUTRAL"

    confidence: float = 0.0

    strength: float = 0.0

    reason: str = ""

    indicators: dict[str, Any] = field(
        default_factory=dict
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "timeframe": self.timeframe,
            "direction": self.direction,
            "confidence": self.confidence,
            "strength": self.strength,
            "reason": self.reason,
            "indicators": dict(
                self.indicators
            ),
        }


@dataclass
class MTFAnalysis:
    """
    Multi-timeframe analysis using the
    three locked RR Trader core timeframes.
    """

    fifteen_minute: TimeframeAnalysis
    one_hour: TimeframeAnalysis
    four_hour: TimeframeAnalysis

    direction: str = "NEUTRAL"

    aligned: bool = False

    status: str = "INCOMPLETE"

    agreement_ratio: float = 0.0

    critical_conflict: bool = False

    reasons: list[str] = field(
        default_factory=list
    )

    @property
    def timeframes(self) -> list[str]:
        return [
            "15m",
            "1h",
            "4h",
        ]

    def _directions(self) -> list[str]:
        return [
            self.fifteen_minute.direction.upper(),
            self.one_hour.direction.upper(),
            self.four_hour.direction.upper(),
        ]

    def calculate_alignment(
        self,
    ) -> None:

        directions = (
            self._directions()
        )

        bullish_count = directions.count(
            "LONG"
        )

        bearish_count = directions.count(
            "SHORT"
        )

        neutral_count = directions.count(
            "NEUTRAL"
        )

        total = len(
            directions
        )

        if total <= 0:
            self.direction = "NEUTRAL"
            self.aligned = False
            self.status = "INCOMPLETE"
            self.agreement_ratio = 0.0
            self.critical_conflict = True
            return

        if (
            bullish_count == total
            and neutral_count == 0
        ):
            self.direction = "LONG"
            self.aligned = True
            self.status = "ALIGNED"
            self.agreement_ratio = 1.0
            self.critical_conflict = False
            return

        if (
            bearish_count == total
            and neutral_count == 0
        ):
            self.direction = "SHORT"
            self.aligned = True
            self.status = "ALIGNED"
            self.agreement_ratio = 1.0
            self.critical_conflict = False
            return

        if neutral_count > 0:
            self.direction = (
                "LONG"
                if bullish_count > bearish_count
                else "SHORT"
                if bearish_count > bullish_count
                else "NEUTRAL"
            )

            self.aligned = False
            self.status = "INCOMPLETE"

            self.agreement_ratio = (
                max(
                    bullish_count,
                    bearish_count,
                )
                / total
            )

            self.critical_conflict = (
                neutral_count > 0
            )

            return

        self.direction = (
            "LONG"
            if bullish_count > bearish_count
            else "SHORT"
            if bearish_count > bullish_count
            else "NEUTRAL"
        )

        self.aligned = False

        self.status = "CONFLICT"

        self.agreement_ratio = (
            max(
                bullish_count,
                bearish_count,
            )
            / total
        )

        self.critical_conflict = True

    def to_dict(self) -> dict[str, Any]:

        self.calculate_alignment()

        return {
            "core_timeframes": [
                "15m",
                "1h",
                "4h",
            ],
            "15m": (
                self.fifteen_minute.to_dict()
            ),
            "1h": (
                self.one_hour.to_dict()
            ),
            "4h": (
                self.four_hour.to_dict()
            ),
            "direction": self.direction,
            "aligned": self.aligned,
            "status": self.status,
            "agreement_ratio": round(
                self.agreement_ratio,
                4,
            ),
            "critical_conflict": (
                self.critical_conflict
            ),
            "reasons": list(
                self.reasons
            ),
        }


@dataclass
class AnalysisResult:
    """
    Full symbol-level analysis result.

    This becomes the central contract between
    Market Scanner, 24-Point Analysis Engine,
    Confidence Engine, Risk Engine and API.
    """

    symbol: str
    market: str

    direction: str = "NEUTRAL"

    confidence: float = 0.0

    publishable: bool = False

    mtf: MTFAnalysis | None = None

    points: dict[str, Any] = field(
        default_factory=dict
    )

    reasons: list[str] = field(
        default_factory=list
    )

    entry: float | None = None

    stop_loss: float | None = None

    tp1: float | None = None

    tp2: float | None = None

    tp3: float | None = None

    risk_reward: float = 0.0

    critical_failures: list[str] = field(
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
            "direction": self.direction,
            "confidence": round(
                self.confidence,
                2,
            ),
            "publishable": (
                self.publishable
            ),
            "multi_timeframe": (
                self.mtf.to_dict()
                if self.mtf is not None
                else None
            ),
            "points": dict(
                self.points
            ),
            "reasons": list(
                self.reasons
            ),
            "entry": self.entry,
            "stop_loss": self.stop_loss,
            "tp1": self.tp1,
            "tp2": self.tp2,
            "tp3": self.tp3,
            "risk_reward": self.risk_reward,
            "critical_failures": list(
                self.critical_failures
            ),
            "metadata": dict(
                self.metadata
            ),
        }


__all__ = [
    "TimeframeAnalysis",
    "MTFAnalysis",
    "AnalysisResult",
]
