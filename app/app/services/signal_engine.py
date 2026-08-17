from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional
import math


@dataclass
class SignalResult:
    symbol: str
    market: str
    timeframe: str
    signal: str
    confidence: float
    entry: Optional[float]
    stop_loss: Optional[float]
    targets: List[float]
    risk_reward: Optional[float]
    reasons: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SignalEngine:
    """
    RR Trader signal engine.

    Converts scanner market data into a LONG / SHORT / WAIT decision.

    Supports:
    - Binance Futures
    - Binance Spot
    - EMA trend
    - Momentum
    - Higher-high / lower-low structure
    - Volume confirmation
    - Support / resistance
    - Risk management
    """

    MIN_CONFIDENCE = 70.0

    def __init__(self, min_confidence: float = MIN_CONFIDENCE) -> None:
        self.min_confidence = float(min_confidence)

    @staticmethod
    def _num(value: Any, default: float = 0.0) -> float:
        try:
            number = float(value)
            if math.isfinite(number):
                return number
        except (TypeError, ValueError):
            pass
        return default

    @staticmethod
    def _get(data: Dict[str, Any], *keys: str, default: Any = None) -> Any:
        for key in keys:
            if key in data and data[key] is not None:
                return data[key]
        return default

    def _calculate_confidence(
        self,
        direction: str,
        trend: str,
        momentum: float,
        volume_ratio: float,
        structure: str,
        price: float,
        ema_fast: float,
        ema_slow: float,
        support: float,
        resistance: float,
    ) -> tuple[float, List[str]]:

        score = 0.0
        reasons: List[str] = []

        # Trend confirmation
        if direction == "LONG":
            if trend == "bullish" or ema_fast > ema_slow:
                score += 20
                reasons.append("Bullish EMA trend confirmed")
        elif direction == "SHORT":
            if trend == "bearish" or ema_fast < ema_slow:
                score += 20
                reasons.append("Bearish EMA trend confirmed")

        # Momentum
        if direction == "LONG" and momentum > 0:
            score += min(20, abs(momentum))
            reasons.append("Positive momentum")
        elif direction == "SHORT" and momentum < 0:
            score += min(20, abs(momentum))
            reasons.append("Negative momentum")

        # Volume
        if volume_ratio >= 1.20:
            score += 15
            reasons.append("Strong volume confirmation")
        elif volume_ratio >= 1.00:
            score += 8
            reasons.append("Normal volume confirmation")

        # Market structure
        if direction == "LONG" and structure in {
            "bullish",
            "higher_high",
            "higher_highs",
        }:
            score += 20
            reasons.append("Higher-high bullish structure")

        if direction == "SHORT" and structure in {
            "bearish",
            "lower_low",
            "lower_lows",
        }:
            score += 20
            reasons.append("Lower-low bearish structure")

        # Location
        if direction == "LONG" and support > 0:
            distance = abs(price - support) / price * 100
            if distance <= 3:
                score += 10
                reasons.append("Price is close to support")

        if direction == "SHORT" and resistance > 0:
            distance = abs(resistance - price) / price * 100
            if distance <= 3:
                score += 10
                reasons.append("Price is close to resistance")

        return min(100.0, max(0.0, score)), reasons

    @staticmethod
    def _risk_levels(
        direction: str,
        price: float,
        support: float,
        resistance: float,
    ) -> tuple[Optional[float], List[float], Optional[float]]:

        if price <= 0:
            return None, [], None

        # Use market structure when available.
        if direction == "LONG":
            if support > 0 and support < price:
                stop_loss = support * 0.995
            else:
                stop_loss = price * 0.98

            risk = price - stop_loss

            if risk <= 0:
                return None, [], None

            targets = [
                price + risk * 1.5,
                price + risk * 2.5,
                price + risk * 4.0,
            ]

        else:
            if resistance > price:
                stop_loss = resistance * 1.005
            else:
                stop_loss = price * 1.02

            risk = stop_loss - price

            if risk <= 0:
                return None, [], None

            targets = [
                price - risk * 1.5,
                price - risk * 2.5,
                price - risk * 4.0,
            ]

            targets = [max(0.0, target) for target in targets]

        risk_reward = abs(targets[1] - price) / risk

        return stop_loss, targets, risk_reward

    def analyze(
        self,
        market_data: Dict[str, Any],
        market: str = "futures",
        timeframe: str = "15m",
    ) -> Dict[str, Any]:

        symbol = str(
            self._get(
                market_data,
                "symbol",
                "ticker",
                "pair",
                default="UNKNOWN",
            )
        ).upper()

        price = self._num(
            self._get(
                market_data,
                "price",
                "last_price",
                "lastPrice",
                "close",
            )
        )

        ema_fast = self._num(
            self._get(
                market_data,
                "ema_fast",
                "ema20",
                "ema_20",
                "fast_ema",
            )
        )

        ema_slow = self._num(
            self._get(
                market_data,
                "ema_slow",
                "ema50",
                "ema_50",
                "slow_ema",
            )
        )

        momentum = self._num(
            self._get(
                market_data,
                "momentum",
                "momentum_score",
                "roc",
                default=0,
            )
        )

        volume_ratio = self._num(
            self._get(
                market_data,
                "volume_ratio",
                "volumeRatio",
                "relative_volume",
                default=1,
            ),
            1,
        )

        trend = str(
            self._get(
                market_data,
                "trend",
                "trend_direction",
                default="neutral",
            )
        ).lower()

        structure = str(
            self._get(
                market_data,
                "structure",
                "market_structure",
                default="neutral",
            )
        ).lower()

        support = self._num(
            self._get(
                market_data,
                "support",
                "support_level",
                default=0,
            )
        )

        resistance = self._num(
            self._get(
                market_data,
                "resistance",
                "resistance_level",
                default=0,
            )
        )

        # Determine direction.
        bullish_votes = 0
        bearish_votes = 0

        if trend == "bullish":
            bullish_votes += 2
        elif trend == "bearish":
            bearish_votes += 2

        if ema_fast > 0 and ema_slow > 0:
            if ema_fast > ema_slow:
                bullish_votes += 2
            elif ema_fast < ema_slow:
                bearish_votes += 2

        if momentum > 0:
            bullish_votes += 1
        elif momentum < 0:
            bearish_votes += 1

        if structure in {"bullish", "higher_high", "higher_highs"}:
            bullish_votes += 2
        elif structure in {"bearish", "lower_low", "lower_lows"}:
            bearish_votes += 2

        if bullish_votes > bearish_votes:
            direction = "LONG"
        elif bearish_votes > bullish_votes:
            direction = "SHORT"
        else:
            direction = "WAIT"

        # No valid price = no trade.
        if price <= 0:
            result = SignalResult(
                symbol=symbol,
                market=market.lower(),
                timeframe=timeframe,
                signal="WAIT",
                confidence=0.0,
                entry=None,
                stop_loss=None,
                targets=[],
                risk_reward=None,
                reasons=["Invalid market price"],
            )
            return result.to_dict()

        if direction == "WAIT":
            result = SignalResult(
                symbol=symbol,
                market=market.lower(),
                timeframe=timeframe,
                signal="WAIT",
                confidence=50.0,
                entry=price,
                stop_loss=None,
                targets=[],
                risk_reward=None,
                reasons=["Market structure is not sufficiently confirmed"],
            )
            return result.to_dict()

        confidence, reasons = self._calculate_confidence(
            direction=direction,
            trend=trend,
            momentum=momentum,
            volume_ratio=volume_ratio,
            structure=structure,
            price=price,
            ema_fast=ema_fast,
            ema_slow=ema_slow,
            support=support,
            resistance=resistance,
        )

        stop_loss, targets, risk_reward = self._risk_levels(
            direction=direction,
            price=price,
            support=support,
            resistance=resistance,
        )

        if confidence < self.min_confidence:
            signal = "WAIT"
            reasons.append(
                f"Confidence below threshold ({self.min_confidence:.0f}%)"
            )
        else:
            signal = direction

        result = SignalResult(
            symbol=symbol,
            market=market.lower(),
            timeframe=timeframe,
            signal=signal,
            confidence=round(confidence, 2),
            entry=price,
            stop_loss=stop_loss,
            targets=targets,
            risk_reward=round(risk_reward, 2)
            if risk_reward is not None
            else None,
            reasons=reasons,
        )

        return result.to_dict()

    def analyze_many(
        self,
        candidates: List[Dict[str, Any]],
        market: str = "futures",
        timeframe: str = "15m",
    ) -> List[Dict[str, Any]]:

        results: List[Dict[str, Any]] = []

        for candidate in candidates:
            try:
                result = self.analyze(
                    candidate,
                    market=market,
                    timeframe=timeframe,
                )
                results.append(result)
            except Exception as exc:
                symbol = str(candidate.get("symbol", "UNKNOWN")).upper()

                results.append(
                    {
                        "symbol": symbol,
                        "market": market.lower(),
                        "timeframe": timeframe,
                        "signal": "WAIT",
                        "confidence": 0.0,
                        "entry": None,
                        "stop_loss": None,
                        "targets": [],
                        "risk_reward": None,
                        "reasons": [f"Signal analysis error: {exc}"],
                    }
                )

        results.sort(
            key=lambda item: float(item.get("confidence", 0)),
            reverse=True,
        )

        return results


# Singleton instance for the application.
signal_engine = SignalEngine()


def analyze_signal(
    market_data: Dict[str, Any],
    market: str = "futures",
    timeframe: str = "15m",
) -> Dict[str, Any]:
    """
    Simple application-level helper.
    """
    return signal_engine.analyze(
        market_data,
        market=market,
        timeframe=timeframe,
    )
