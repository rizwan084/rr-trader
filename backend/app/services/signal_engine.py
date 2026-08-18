from __future__ import annotations

import asyncio
from typing import Any

from app.services.indicators import indicator_engine
from app.services.market_data import market_data_service
from app.services.market_structure import (
    market_structure_engine,
)
from app.services.mtf_engine import mtf_engine


class SignalEngine:
    """
    RR Trader deterministic signal engine.

    Pipeline:

        Binance Market Data
            ↓
        15m / 1h / 4h indicators
            ↓
        Market Structure
            ↓
        MTF Confirmation
            ↓
        Preliminary LONG / SHORT / NO TRADE

    This layer does NOT execute trades.
    """

    CORE_TIMEFRAMES = (
        "15m",
        "1h",
        "4h",
    )

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

    # =====================================================
    # TIMEFRAME ANALYSIS
    # =====================================================

    def analyze_timeframe(
        self,
        timeframe: str,
        candles: list[Any],
    ) -> dict[str, Any]:

        indicators = (
            indicator_engine.calculate(
                candles
            )
        )

        if not indicators.get(
            "success",
            False,
        ):

            return {
                "success": False,
                "timeframe": timeframe,
                "direction": "NEUTRAL",
                "confidence": 0.0,
                "indicators": {},
                "structure": {},
                "reason": indicators.get(
                    "error",
                    "Indicator calculation failed.",
                ),
            }

        parsed = (
            indicator_engine
            .parse_candles(
                candles
            )
        )

        structure = (
            market_structure_engine.analyze(
                highs=parsed["highs"],
                lows=parsed["lows"],
                closes=parsed["closes"],
            )
        )

        direction_scores = {
            "LONG": 0.0,
            "SHORT": 0.0,
        }

        reasons: list[str] = []

        # -------------------------------------------------
        # EMA TREND
        # -------------------------------------------------

        price = self._float(
            indicators.get(
                "price"
            )
        )

        ema20 = self._float(
            indicators.get(
                "ema20"
            )
        )

        ema50 = self._float(
            indicators.get(
                "ema50"
            )
        )

        if (
            price > ema20 > ema50
            and price > 0
        ):

            direction_scores[
                "LONG"
            ] += 20.0

            reasons.append(
                "Price is above EMA20 and EMA50."
            )

        elif (
            price < ema20 < ema50
            and price > 0
        ):

            direction_scores[
                "SHORT"
            ] += 20.0

            reasons.append(
                "Price is below EMA20 and EMA50."
            )

        # -------------------------------------------------
        # RSI
        # -------------------------------------------------

        rsi = self._float(
            indicators.get(
                "rsi",
                50,
            )
        )

        if 50 < rsi < 70:

            direction_scores[
                "LONG"
            ] += 10.0

            reasons.append(
                "RSI supports bullish momentum."
            )

        elif 30 < rsi < 50:

            direction_scores[
                "SHORT"
            ] += 10.0

            reasons.append(
                "RSI supports bearish momentum."
            )

        # Avoid automatically calling extreme RSI
        # bullish or bearish. Extreme readings can
        # indicate exhaustion.

        # -------------------------------------------------
        # MOMENTUM
        # -------------------------------------------------

        momentum = self._float(
            indicators.get(
                "momentum"
            )
        )

        if momentum > 0:

            direction_scores[
                "LONG"
            ] += min(
                15.0,
                abs(momentum) * 3.0,
            )

            reasons.append(
                "Momentum is positive."
            )

        elif momentum < 0:

            direction_scores[
                "SHORT"
            ] += min(
                15.0,
                abs(momentum) * 3.0,
            )

            reasons.append(
                "Momentum is negative."
            )

        # -------------------------------------------------
        # VOLUME
        # -------------------------------------------------

        volume_ratio = self._float(
            indicators.get(
                "volume_ratio"
            )
        )

        candle_direction = str(
            indicators.get(
                "candle_structure",
                {},
            ).get(
                "direction",
                "NEUTRAL",
            )
        ).upper()

        if volume_ratio >= 1.2:

            if candle_direction == "LONG":

                direction_scores[
                    "LONG"
                ] += 10.0

                reasons.append(
                    "Bullish candle has above-average volume."
                )

            elif candle_direction == "SHORT":

                direction_scores[
                    "SHORT"
                ] += 10.0

                reasons.append(
                    "Bearish candle has above-average volume."
                )

        # -------------------------------------------------
        # MARKET STRUCTURE
        # -------------------------------------------------

        structure_direction = str(
            structure.get(
                "direction",
                "NEUTRAL",
            )
        ).upper()

        if structure_direction == "LONG":

            direction_scores[
                "LONG"
            ] += 20.0

            reasons.append(
                "Market structure is bullish."
            )

        elif structure_direction == "SHORT":

            direction_scores[
                "SHORT"
            ] += 20.0

            reasons.append(
                "Market structure is bearish."
            )

        # -------------------------------------------------
        # BREAK OF STRUCTURE
        # -------------------------------------------------

        bos = structure.get(
            "break_of_structure",
            {},
        )

        bos_direction = str(
            bos.get(
                "direction",
                "NONE",
            )
        ).upper()

        if bos_direction == "LONG":

            direction_scores[
                "LONG"
            ] += 15.0

            reasons.append(
                "Bullish break of structure detected."
            )

        elif bos_direction == "SHORT":

            direction_scores[
                "SHORT"
            ] += 15.0

            reasons.append(
                "Bearish break of structure detected."
            )

        # -------------------------------------------------
        # VWAP
        # -------------------------------------------------

        vwap = self._float(
            indicators.get(
                "vwap"
            )
        )

        if (
            vwap > 0
            and price > vwap
        ):

            direction_scores[
                "LONG"
            ] += 5.0

            reasons.append(
                "Price is above VWAP."
            )

        elif (
            vwap > 0
            and price < vwap
        ):

            direction_scores[
                "SHORT"
            ] += 5.0

            reasons.append(
                "Price is below VWAP."
            )

        # -------------------------------------------------
        # BREAKOUT
        # -------------------------------------------------

        breakout = indicators.get(
            "breakout",
            {},
        )

        breakout_direction = str(
            breakout.get(
                "direction",
                "NONE",
            )
        ).upper()

        if breakout_direction == "LONG":

            direction_scores[
                "LONG"
            ] += 10.0

            reasons.append(
                "Upside breakout detected."
            )

        elif breakout_direction == "SHORT":

            direction_scores[
                "SHORT"
            ] += 10.0

            reasons.append(
                "Downside breakout detected."
            )

        # -------------------------------------------------
        # FINAL TIMEFRAME DIRECTION
        # -------------------------------------------------

        long_score = direction_scores[
            "LONG"
        ]

        short_score = direction_scores[
            "SHORT"
        ]

        if long_score > short_score:

            direction = "LONG"
            score = long_score

        elif short_score > long_score:

            direction = "SHORT"
            score = short_score

        else:

            direction = "NEUTRAL"
            score = 0.0

        confidence = min(
            100.0,
            score,
        )

        return {
            "success": True,
            "timeframe": timeframe,
            "direction": direction,
            "confidence": round(
                confidence,
                2,
            ),
            "score": round(
                score,
                2,
            ),
            "indicators": indicators,
            "structure": structure,
            "reasons": list(
                dict.fromkeys(
                    reasons
                )
            ),
        }

    # =====================================================
    # MULTI-TIMEFRAME
    # =====================================================

    async def analyze_symbol(
        self,
        symbol: str,
        market: str = "futures",
        candle_limit: int = 200,
    ) -> dict[str, Any]:

        symbol = str(
            symbol
        ).upper().strip()

        market = str(
            market
        ).lower().strip()

        if market not in {
            "spot",
            "futures",
        }:

            raise ValueError(
                "market must be 'spot' or 'futures'"
            )

        market_data = (
            await market_data_service
            .core_timeframes(
                symbol=symbol,
                market=market,
                limit=candle_limit,
            )
        )

        timeframe_tasks = []

        for timeframe in (
            self.CORE_TIMEFRAMES
        ):

            item = market_data.get(
                timeframe,
                {},
            )

            candles = []

            if isinstance(
                item,
                dict,
            ):

                candles = item.get(
                    "candles",
                    [],
                )

            timeframe_tasks.append(
                asyncio.to_thread(
                    self.analyze_timeframe,
                    timeframe,
                    candles,
                )
            )

        timeframe_results = (
            await asyncio.gather(
                *timeframe_tasks,
                return_exceptions=True,
            )
        )

        timeframe_analysis: dict[
            str,
            dict[str, Any],
        ] = {}

        for timeframe, result in zip(
            self.CORE_TIMEFRAMES,
            timeframe_results,
        ):

            if isinstance(
                result,
                Exception,
            ):

                timeframe_analysis[
                    timeframe
                ] = {
                    "success": False,
                    "timeframe": timeframe,
                    "direction": "NEUTRAL",
                    "confidence": 0.0,
                    "error": str(
                        result
                    ),
                }

            else:

                timeframe_analysis[
                    timeframe
                ] = result

        # -------------------------------------------------
        # MTF ENGINE
        # -------------------------------------------------

        mtf = mtf_engine.analyze(
            timeframe_analysis
        )

        # -------------------------------------------------
        # PRIMARY DIRECTION
        # -------------------------------------------------

        direction = mtf.get(
            "direction",
            "NEUTRAL",
        )

        # -------------------------------------------------
        # Confidence
        # -------------------------------------------------

        confidence = self._float(
            mtf.get(
                "weighted_confidence",
                0,
            )
        )

        # A strict conflict reduces confidence.
        if mtf.get(
            "status"
        ) == "CONFLICT":

            confidence *= 0.70

        # Incomplete 4H / 1H / 15m data
        # must never look like a strong signal.
        if mtf.get(
            "status"
        ) == "INCOMPLETE":

            confidence *= 0.50

        confidence = round(
            min(
                100.0,
                max(
                    0.0,
                    confidence,
                ),
            ),
            2,
        )

        # -------------------------------------------------
        # Publishability at this stage
        # -------------------------------------------------

        publishable = (
            mtf.get(
                "publishable_mtf",
                False,
            )
            and confidence
            >= 85.0
        )

        reasons: list[str] = []

        for timeframe in (
            self.CORE_TIMEFRAMES
        ):

            reasons.extend(
                timeframe_analysis.get(
                    timeframe,
                    {},
                ).get(
                    "reasons",
                    [],
                )
            )

        if mtf.get(
            "publishable_mtf"
        ):

            reasons.append(
                "15m, 1H and 4H are aligned."
            )

        else:

            reasons.append(
                "Core MTF alignment is not fully confirmed."
            )

        return {
            "success": True,
            "symbol": symbol,
            "market": market,
            "direction": direction,
            "confidence": confidence,
            "publishable": publishable,
            "timeframes":
                timeframe_analysis,
            "multi_timeframe": mtf,
            "reasons": list(
                dict.fromkeys(
                    reasons
                )
            ),
        }


signal_engine = SignalEngine()


__all__ = [
    "SignalEngine",
    "signal_engine",
]
