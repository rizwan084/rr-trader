from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AnalysisPoint:
    number: int
    name: str
    category: str


class AnalysisEngine:
    """
    RR Trader 24-point market analysis framework.

    Points 1-20:
        Actual market confirmations.

    Points 21-24:
        Risk / execution gates.

    This phase defines the canonical structure.
    Calculation logic is added incrementally after
    the Binance data layer is validated.
    """

    MARKET_POINTS = (
        AnalysisPoint(
            1,
            "Market Regime",
            "market",
        ),
        AnalysisPoint(
            2,
            "Market Structure",
            "market",
        ),
        AnalysisPoint(
            3,
            "Multi-Timeframe Confirmation",
            "market",
        ),
        AnalysisPoint(
            4,
            "Entry Location",
            "market",
        ),
        AnalysisPoint(
            5,
            "Liquidity Sweep",
            "market",
        ),
        AnalysisPoint(
            6,
            "VWAP",
            "market",
        ),
        AnalysisPoint(
            7,
            "ATR / Volatility",
            "market",
        ),
        AnalysisPoint(
            8,
            "Momentum",
            "market",
        ),
        AnalysisPoint(
            9,
            "Divergence",
            "market",
        ),
        AnalysisPoint(
            10,
            "Breakout",
            "market",
        ),
        AnalysisPoint(
            11,
            "Retest",
            "market",
        ),
        AnalysisPoint(
            12,
            "Derivatives",
            "market",
        ),
        AnalysisPoint(
            13,
            "Liquidations",
            "market",
        ),
        AnalysisPoint(
            14,
            "Order Book",
            "market",
        ),
        AnalysisPoint(
            15,
            "Tradeability",
            "market",
        ),
        AnalysisPoint(
            16,
            "News / Event Risk",
            "market",
        ),
        AnalysisPoint(
            17,
            "BTC / Market Context",
            "market",
        ),
        AnalysisPoint(
            18,
            "Relative Strength",
            "market",
        ),
        AnalysisPoint(
            19,
            "Risk / Reward",
            "market",
        ),
        AnalysisPoint(
            20,
            "Stop Quality",
            "market",
        ),
    )

    RISK_POINTS = (
        AnalysisPoint(
            21,
            "Position Sizing",
            "risk",
        ),
        AnalysisPoint(
            22,
            "Portfolio Risk",
            "risk",
        ),
        AnalysisPoint(
            23,
            "Execution Quality",
            "risk",
        ),
        AnalysisPoint(
            24,
            "Signal Freshness",
            "risk",
        ),
    )

    @classmethod
    def all_points(
        cls,
    ) -> tuple[AnalysisPoint, ...]:
        return (
            cls.MARKET_POINTS
            + cls.RISK_POINTS
        )

    @classmethod
    def point_definitions(
        cls,
    ) -> list[dict[str, Any]]:
        return [
            {
                "number": point.number,
                "name": point.name,
                "category": point.category,
            }
            for point in cls.all_points()
        ]

    @classmethod
    def empty_result(
        cls,
        *,
        symbol: str,
        market: str,
        direction: str = "NEUTRAL",
    ) -> dict[str, Any]:

        points: dict[str, dict[str, Any]] = {}

        for point in cls.all_points():
            points[str(point.number)] = {
                "number": point.number,
                "name": point.name,
                "category": point.category,
                "status": "PENDING",
                "direction": "NEUTRAL",
                "score": 0.0,
                "reason": "",
            }

        return {
            "success": True,
            "symbol": symbol.upper(),
            "market": market.lower(),
            "direction": direction.upper(),
            "points": points,
            "market_confirmation_count": 0,
            "risk_gate_count": 0,
            "market_confirmation_total": 20,
            "risk_gate_total": 4,
            "critical_failures": [],
            "status": "analysis_framework_ready",
        }

    async def analyze(
        self,
        *,
        symbol: str,
        market: str,
        market_data: dict[str, Any] | None = None,
        direction: str = "NEUTRAL",
    ) -> dict[str, Any]:

        result = self.empty_result(
            symbol=symbol,
            market=market,
            direction=direction,
        )

        if market_data:
            result["market_data_received"] = True
            result["market_data_keys"] = sorted(
                market_data.keys()
            )
        else:
            result["market_data_received"] = False
            result["market_data_keys"] = []

        return result


analysis_engine = AnalysisEngine()


__all__ = [
    "AnalysisPoint",
    "AnalysisEngine",
    "analysis_engine",
]
