from __future__ import annotations

import asyncio
from typing import Any

from app.services.indicators import indicator_engine
from app.services.market_data import market_data_service
from app.services.market_structure import (
    market_structure_engine,
)
from app.services.mtf_engine import mtf_engine
from app.services.confidence_engine import (
    confidence_engine,
)


class MasterAnalysisEngine:
    """
    RR Trader master deterministic analysis engine.

    Combines:

    - 15m
    - 1H
    - 4H
    - Technical indicators
    - Market structure
    - Multi-timeframe confirmation
    - Order book
    - Derivatives
    - Liquidations
    - Support / resistance
    - Risk / reward
    - Confidence Engine v2

    This engine performs analysis only.
    Trade execution remains separate.
    """

    CORE_TIMEFRAMES = (
        "15m",
        "1h",
        "4h",
    )

    MIN_CONFIDENCE = 85.0

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
        direction = str(
            value or "NEUTRAL"
        ).upper().strip()

        if direction not in {
            "LONG",
            "SHORT",
            "NEUTRAL",
        }:
            return "NEUTRAL"

        return direction

    @staticmethod
    def _clamp(
        value: Any,
        low: float = 0.0,
        high: float = 100.0,
    ) -> float:
        try:
            number = float(value)
        except (
            TypeError,
            ValueError,
        ):
            number = low

        return max(
            low,
            min(high, number),
        )

    # =====================================================
    # ORDER BOOK
    # =====================================================

    def analyze_order_book(
        self,
        order_book: Any,
    ) -> dict[str, Any]:

        if not isinstance(
            order_book,
            dict,
        ):
            return {
                "status": "UNAVAILABLE",
                "direction": "NEUTRAL",
                "score": 0.0,
                "imbalance": 0.0,
            }

        bids = order_book.get(
            "bids",
            [],
        )

        asks = order_book.get(
            "asks",
            [],
        )

        bid_volume = 0.0
        ask_volume = 0.0

        if isinstance(
            bids,
            list,
        ):
            for item in bids[:50]:
                if (
                    isinstance(
                        item,
                        (list, tuple),
                    )
                    and len(item) >= 2
                ):
                    bid_volume += self._float(
                        item[1]
                    )

        if isinstance(
            asks,
            list,
        ):
            for item in asks[:50]:
                if (
                    isinstance(
                        item,
                        (list, tuple),
                    )
                    and len(item) >= 2
                ):
                    ask_volume += self._float(
                        item[1]
                    )

        total = (
            bid_volume
            + ask_volume
        )

        if total <= 0:
            return {
                "status": "UNAVAILABLE",
                "direction": "NEUTRAL",
                "score": 0.0,
                "imbalance": 0.0,
            }

        imbalance = (
            bid_volume - ask_volume
        ) / total

        if imbalance >= 0.10:
            direction = "LONG"

        elif imbalance <= -0.10:
            direction = "SHORT"

        else:
            direction = "NEUTRAL"

        score = min(
            100.0,
            abs(imbalance) * 500.0,
        )

        return {
            "status": "AVAILABLE",
            "direction": direction,
            "score": round(
                score,
                2,
            ),
            "imbalance": round(
                imbalance,
                6,
            ),
            "bid_volume": bid_volume,
            "ask_volume": ask_volume,
        }

    # =====================================================
    # LIQUIDATIONS
    # =====================================================

    def analyze_liquidations(
        self,
        liquidation_orders: Any,
    ) -> dict[str, Any]:

        if not isinstance(
            liquidation_orders,
            list,
        ):
            return {
                "status": "UNAVAILABLE",
                "direction": "NEUTRAL",
                "score": 0.0,
            }

        long_liquidations = 0.0
        short_liquidations = 0.0

        for item in liquidation_orders:

            if not isinstance(
                item,
                dict,
            ):
                continue

            side = str(
                item.get(
                    "side",
                    "",
                )
            ).upper()

            qty = self._float(
                item.get(
                    "origQty",
                    item.get(
                        "executedQty",
                        0,
                    ),
                )
            )

            price = self._float(
                item.get(
                    "price",
                    0,
                )
            )

            notional = (
                abs(qty * price)
                if price > 0
                else abs(qty)
            )

            if side == "SELL":
                long_liquidations += (
                    notional
                )

            elif side == "BUY":
                short_liquidations += (
                    notional
                )

        total = (
            long_liquidations
            + short_liquidations
        )

        if total <= 0:
            return {
                "status": "AVAILABLE",
                "direction": "NEUTRAL",
                "score": 0.0,
                "long_liquidations":
                    long_liquidations,
                "short_liquidations":
                    short_liquidations,
            }

        imbalance = (
            short_liquidations
            - long_liquidations
        ) / total

        if imbalance > 0.20:
            direction = "LONG"

        elif imbalance < -0.20:
            direction = "SHORT"

        else:
            direction = "NEUTRAL"

        score = min(
            100.0,
            abs(imbalance) * 100.0,
        )

        return {
            "status": "AVAILABLE",
            "direction": direction,
            "score": round(
                score,
                2,
            ),
            "long_liquidations":
                long_liquidations,
            "short_liquidations":
                short_liquidations,
            "imbalance":
                round(
                    imbalance,
                    6,
                ),
        }

    # =====================================================
    # DERIVATIVES
    # =====================================================

    def analyze_derivatives(
        self,
        derivatives: Any,
    ) -> dict[str, Any]:

        if not isinstance(
            derivatives,
            dict,
        ):
            return {
                "status": "UNAVAILABLE",
                "direction": "NEUTRAL",
                "score": 0.0,
                "reasons": [],
            }

        long_evidence = 0
        short_evidence = 0
        reasons: list[str] = []

        funding = derivatives.get(
            "funding_rate",
            [],
        )

        if (
            isinstance(
                funding,
                list,
            )
            and funding
        ):
            latest = funding[-1]

            if isinstance(
                latest,
                dict,
            ):
                funding_rate = self._float(
                    latest.get(
                        "fundingRate",
                        0,
                    )
                )

                if funding_rate < -0.0001:
                    long_evidence += 1
                    reasons.append(
                        "Funding is negative."
                    )

                elif funding_rate > 0.0001:
                    short_evidence += 1
                    reasons.append(
                        "Funding is positive."
                    )

        global_ratio = derivatives.get(
            "global_long_short_ratio",
            [],
        )

        if (
            isinstance(
                global_ratio,
                list,
            )
            and global_ratio
        ):
            latest = global_ratio[-1]

            if isinstance(
                latest,
                dict,
            ):
                ratio = self._float(
                    latest.get(
                        "longShortRatio",
                        1.0,
                    ),
                    1.0,
                )

                if ratio < 0.90:
                    long_evidence += 1
                    reasons.append(
                        "Global positioning leans short."
                    )

                elif ratio > 1.10:
                    short_evidence += 1
                    reasons.append(
                        "Global positioning leans long."
                    )

        top_ratio = derivatives.get(
            "top_trader_long_short_ratio",
            [],
        )

        if (
            isinstance(
                top_ratio,
                list,
            )
            and top_ratio
        ):
            latest = top_ratio[-1]

            if isinstance(
                latest,
                dict,
            ):
                ratio = self._float(
                    latest.get(
                        "longShortRatio",
                        1.0,
                    ),
                    1.0,
                )

                if ratio < 0.90:
                    long_evidence += 1
                    reasons.append(
                        "Top traders lean short."
                    )

                elif ratio > 1.10:
                    short_evidence += 1
                    reasons.append(
                        "Top traders lean long."
                    )

        if long_evidence > short_evidence:
            direction = "LONG"

        elif short_evidence > long_evidence:
            direction = "SHORT"

        else:
            direction = "NEUTRAL"

        score = min(
            100.0,
            abs(
                long_evidence
                - short_evidence
            ) * 30.0,
        )

        return {
            "status": "AVAILABLE",
            "direction": direction,
            "score": round(
                score,
                2,
            ),
            "long_evidence":
                long_evidence,
            "short_evidence":
                short_evidence,
            "reasons": reasons,
        }

    # =====================================================
    # TIMEFRAME ANALYSIS
    # =====================================================

    async def _analyze_timeframe(
        self,
        raw: dict[str, Any],
        timeframe: str,
    ) -> tuple[
        str,
        dict[str, Any],
    ]:

        raw_timeframes = raw.get(
            "timeframes",
            {},
        )

        if not isinstance(
            raw_timeframes,
            dict,
        ):
            raw_timeframes = {}

        timeframe_data = raw_timeframes.get(
            timeframe,
            {},
        )

        if not isinstance(
            timeframe_data,
            dict,
        ):
            timeframe_data = {}

        candles = timeframe_data.get(
            "candles",
            [],
        )

        if not isinstance(
            candles,
            list,
        ):
            candles = []

        if len(candles) < 20:
            return (
                timeframe,
                {
                    "success": False,
                    "direction": "NEUTRAL",
                    "confidence": 0.0,
                    "score": 0.0,
                    "indicators": {},
                    "structure": {},
                    "reasons": [],
                    "error":
                        "Insufficient candle data.",
                },
            )

        indicators = (
            indicator_engine.calculate(
                candles
            )
        )

        parsed = (
            indicator_engine.parse_candles(
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

        if not isinstance(
            indicators,
            dict,
        ):
            indicators = {}

        if not isinstance(
            structure,
            dict,
        ):
            structure = {}

        long_score = 0.0
        short_score = 0.0

        reasons: list[str] = []

        price = self._float(
            indicators.get(
                "price",
                0,
            )
        )

        ema20 = self._float(
            indicators.get(
                "ema20",
                0,
            )
        )

        ema50 = self._float(
            indicators.get(
                "ema50",
                0,
            )
        )

        momentum = self._float(
            indicators.get(
                "momentum",
                0,
            )
        )

        vwap = self._float(
            indicators.get(
                "vwap",
                0,
            )
        )

        # EMA
        if (
            price > 0
            and ema20 > 0
            and ema50 > 0
        ):

            if price > ema20 > ema50:
                long_score += 20
                reasons.append(
                    "EMA structure bullish."
                )

            elif price < ema20 < ema50:
                short_score += 20
                reasons.append(
                    "EMA structure bearish."
                )

        # Momentum
        if momentum > 0:
            long_score += min(
                15,
                abs(momentum) * 3,
            )
            reasons.append(
                "Momentum positive."
            )

        elif momentum < 0:
            short_score += min(
                15,
                abs(momentum) * 3,
            )
            reasons.append(
                "Momentum negative."
            )

        # Structure
        structure_direction = (
            self._direction(
                structure.get(
                    "direction"
                )
            )
        )

        if structure_direction == "LONG":
            long_score += 25
            reasons.append(
                "Market structure bullish."
            )

        elif structure_direction == "SHORT":
            short_score += 25
            reasons.append(
                "Market structure bearish."
            )

        # Breakout
        breakout = indicators.get(
            "breakout",
            {},
        )

        if not isinstance(
            breakout,
            dict,
        ):
            breakout = {}

        breakout_direction = (
            self._direction(
                breakout.get(
                    "direction"
                )
            )
        )

        if breakout_direction == "LONG":
            long_score += 10
            reasons.append(
                "Bullish breakout detected."
            )

        elif breakout_direction == "SHORT":
            short_score += 10
            reasons.append(
                "Bearish breakout detected."
            )

        # VWAP
        if (
            price > 0
            and vwap > 0
        ):

            if price > vwap:
                long_score += 5

            elif price < vwap:
                short_score += 5

        # Final direction
        if long_score > short_score:
            direction = "LONG"

        elif short_score > long_score:
            direction = "SHORT"

        else:
            direction = "NEUTRAL"

        score = max(
            long_score,
            short_score,
        )

        return (
            timeframe,
            {
                "success": True,
                "direction": direction,
                "confidence": round(
                    min(
                        100.0,
                        score,
                    ),
                    2,
                ),
                "score": round(
                    score,
                    2,
                ),
                "indicators": indicators,
                "structure": structure,
                "reasons": reasons,
            },
        )

    # =====================================================
    # TRADE LEVELS
    # =====================================================

    def _calculate_levels(
        self,
        direction: str,
        timeframes: dict[str, Any],
    ) -> dict[str, Any]:

        if direction not in {
            "LONG",
            "SHORT",
        }:
            return {
                "entry": 0.0,
                "stop_loss": 0.0,
                "tp1": 0.0,
                "tp2": 0.0,
                "tp3": 0.0,
                "risk_reward": 0.0,
                "stop_quality":
                    "INVALID",
            }

        fifteen = timeframes.get(
            "15m",
            {},
        )

        if not isinstance(
            fifteen,
            dict,
        ):
            fifteen = {}

        indicators = fifteen.get(
            "indicators",
            {},
        )

        structure = fifteen.get(
            "structure",
            {},
        )

        if not isinstance(
            indicators,
            dict,
        ):
            indicators = {}

        if not isinstance(
            structure,
            dict,
        ):
            structure = {}

        sr = structure.get(
            "support_resistance",
            {},
        )

        if not isinstance(
            sr,
            dict,
        ):
            sr = {}

        entry = self._float(
            indicators.get(
                "price",
                0,
            )
        )

        atr = self._float(
            indicators.get(
                "atr",
                0,
            )
        )

        support = self._float(
            sr.get(
                "support",
                0,
            )
        )

        resistance = self._float(
            sr.get(
                "resistance",
                0,
            )
        )

        if entry <= 0:
            return {
                "entry": 0.0,
                "stop_loss": 0.0,
                "tp1": 0.0,
                "tp2": 0.0,
                "tp3": 0.0,
                "risk_reward": 0.0,
                "stop_quality":
                    "INVALID",
            }

        # LONG
        if direction == "LONG":

            if (
                support > 0
                and support < entry
            ):
                stop_loss = (
                    support * 0.995
                )

            elif atr > 0:
                stop_loss = (
                    entry
                    - atr * 1.5
                )

            else:
                stop_loss = (
                    entry * 0.98
                )

            risk = (
                entry
                - stop_loss
            )

            if risk <= 0:
                return {
                    "entry": entry,
                    "stop_loss": 0.0,
                    "tp1": 0.0,
                    "tp2": 0.0,
                    "tp3": 0.0,
                    "risk_reward": 0.0,
                    "stop_quality":
                        "INVALID",
                }

            tp1 = (
                entry
                + risk * 1.5
            )

            tp2 = (
                entry
                + risk * 2.5
            )

            tp3 = (
                entry
                + risk * 3.5
            )

            if resistance > entry:
                tp2 = max(
                    tp2,
                    resistance,
                )

            rr = (
                tp2 - entry
            ) / risk

            return {
                "entry": entry,
                "stop_loss": stop_loss,
                "tp1": tp1,
                "tp2": tp2,
                "tp3": tp3,
                "risk_reward": rr,
                "stop_quality":
                    "VALID",
            }

        # SHORT
        if (
            resistance > 0
            and resistance > entry
        ):
            stop_loss = (
                resistance * 1.005
            )

        elif atr > 0:
            stop_loss = (
                entry
                + atr * 1.5
            )

        else:
            stop_loss = (
                entry * 1.02
            )

        risk = (
            stop_loss
            - entry
        )

        if risk <= 0:
            return {
                "entry": entry,
                "stop_loss": 0.0,
                "tp1": 0.0,
                "tp2": 0.0,
                "tp3": 0.0,
                "risk_reward": 0.0,
                "stop_quality":
                    "INVALID",
            }

        tp1 = (
            entry
            - risk * 1.5
        )

        tp2 = (
            entry
            - risk * 2.5
        )

        tp3 = (
            entry
            - risk * 3.5
        )

        if (
            support > 0
            and support < entry
        ):
            tp2 = min(
                tp2,
                support,
            )

        rr = (
            entry - tp2
        ) / risk

        return {
            "entry": entry,
            "stop_loss": stop_loss,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "risk_reward": rr,
            "stop_quality":
                "VALID",
        }

    # =====================================================
    # CONFIDENCE INPUT
    # =====================================================

    def _build_confidence_input(
        self,
        direction: str,
        timeframes: dict[str, Any],
        mtf: dict[str, Any],
        order_book: dict[str, Any],
        liquidations: dict[str, Any],
        derivatives: dict[str, Any],
        levels: dict[str, Any],
    ) -> dict[str, Any]:

        fifteen = timeframes.get(
            "15m",
            {},
        )

        one_hour = timeframes.get(
            "1h",
            {},
        )

        four_hour = timeframes.get(
            "4h",
            {},
        )

        if not isinstance(
            fifteen,
            dict,
        ):
            fifteen = {}

        if not isinstance(
            one_hour,
            dict,
        ):
            one_hour = {}

        if not isinstance(
            four_hour,
            dict,
        ):
            four_hour = {}

        fifteen_indicators = (
            fifteen.get(
                "indicators",
                {},
            )
        )

        one_hour_indicators = (
            one_hour.get(
                "indicators",
                {},
            )
        )

        four_hour_indicators = (
            four_hour.get(
                "indicators",
                {},
            )
        )

        fifteen_structure = (
            fifteen.get(
                "structure",
                {},
            )
        )

        one_hour_structure = (
            one_hour.get(
                "structure",
                {},
            )
        )

        four_hour_structure = (
            four_hour.get(
                "structure",
                {},
            )
        )

        for name, value in (
            (
                "fifteen_indicators",
                fifteen_indicators,
            ),
            (
                "one_hour_indicators",
                one_hour_indicators,
            ),
            (
                "four_hour_indicators",
                four_hour_indicators,
            ),
            (
                "fifteen_structure",
                fifteen_structure,
            ),
            (
                "one_hour_structure",
                one_hour_structure,
            ),
            (
                "four_hour_structure",
                four_hour_structure,
            ),
        ):

            if not isinstance(
                value,
                dict,
            ):
                if name.endswith(
                    "_structure"
                ):
                    locals()[name] = {}
                else:
                    locals()[name] = {}

        # Structure
        structure_scores: list[float] = []

        for structure in (
            fifteen_structure,
            one_hour_structure,
            four_hour_structure,
        ):

            if not isinstance(
                structure,
                dict,
            ):
                continue

            details = structure.get(
                "structure_details",
                {},
            )

            if not isinstance(
                details,
                dict,
            ):
                continue

            bullish = (
                int(
                    bool(
                        details.get(
                            "higher_high",
                            False,
                        )
                    )
                )
                + int(
                    bool(
                        details.get(
                            "higher_low",
                            False,
                        )
                    )
                )
            )

            bearish = (
                int(
                    bool(
                        details.get(
                            "lower_high",
                            False,
                        )
                    )
                )
                + int(
                    bool(
                        details.get(
                            "lower_low",
                            False,
                        )
                    )
                )
            )

            if direction == "LONG":
                structure_scores.append(
                    bullish * 50.0
                )

            elif direction == "SHORT":
                structure_scores.append(
                    bearish * 50.0
                )

        structure_score = (
            sum(structure_scores)
            / len(structure_scores)
            if structure_scores
            else 0.0
        )

        # Trend
        trend_score = self._clamp(
            one_hour.get(
                "confidence",
                0,
            )
        )

        # Momentum
        momentum = self._float(
            fifteen_indicators.get(
                "momentum",
                0,
            )
        )

        if direction == "LONG":
            momentum_score = self._clamp(
                50.0
                + momentum * 10.0
            )
        else:
            momentum_score = self._clamp(
                50.0
                - momentum * 10.0
            )

        # Volume
        volume_scores: list[
            float
        ] = []

        for indicators in (
            fifteen_indicators,
            one_hour_indicators,
            four_hour_indicators,
        ):

            if not isinstance(
                indicators,
                dict,
            ):
                continue

            ratio = self._float(
                indicators.get(
                    "volume_ratio",
                    0,
                )
            )

            if ratio > 0:
                volume_scores.append(
                    self._clamp(
                        ratio * 50.0
                    )
                )

        volume_score = (
            sum(volume_scores)
            / len(volume_scores)
            if volume_scores
            else 0.0
        )

        # Support / Resistance
        support_resistance = 0.0

        sr = (
            fifteen_structure.get(
                "support_resistance",
                {},
            )
            if isinstance(
                fifteen_structure,
                dict,
            )
            else {}
        )

        if not isinstance(
            sr,
            dict,
        ):
            sr = {}

        location = str(
            sr.get(
                "location",
                "",
            )
        ).upper()

        if direction == "LONG":

            if location == "NEAR_SUPPORT":
                support_resistance = 95.0

            elif location == "MID_RANGE":
                support_resistance = 55.0

            else:
                support_resistance = 20.0

        elif direction == "SHORT":

            if location == "NEAR_RESISTANCE":
                support_resistance = 95.0

            elif location == "MID_RANGE":
                support_resistance = 55.0

            else:
                support_resistance = 20.0

        # MTF
        mtf_direction = self._direction(
            mtf.get(
                "direction"
            )
        )

        weighted_confidence = self._clamp(
            mtf.get(
                "weighted_confidence",
                0,
            )
        )

        agreement_ratio = self._clamp(
            mtf.get(
                "agreement_ratio",
                0,
            ),
            0,
            1,
        )

        mtf_score = (
            weighted_confidence
            * agreement_ratio
        )

        if (
            bool(
                mtf.get(
                    "aligned",
                    False,
                )
            )
            and mtf_direction == direction
        ):
            mtf_score += 20.0

        mtf_score = self._clamp(
            mtf_score
        )

        # Liquidity
        liquidity_score = 0.0

        ob_direction = self._direction(
            order_book.get(
                "direction"
            )
        )

        ob_score = self._clamp(
            order_book.get(
                "score",
                0,
            )
        )

        if ob_direction == direction:
            liquidity_score = ob_score

        elif ob_direction == "NEUTRAL":
            liquidity_score = (
                ob_score * 0.35
            )

        liquidation_direction = (
            self._direction(
                liquidations.get(
                    "direction"
                )
            )
        )

        liquidation_score = self._clamp(
            liquidations.get(
                "score",
                0,
            )
        )

        if (
            liquidation_direction
            == direction
        ):
            liquidity_score = max(
                liquidity_score,
                liquidation_score,
            )

        # Derivatives
        derivative_direction = (
            self._direction(
                derivatives.get(
                    "direction"
                )
            )
        )

        derivative_score = self._clamp(
            derivatives.get(
                "score",
                0,
            )
        )

        if (
            derivative_direction
            == direction
        ):
            derivatives_score = (
                derivative_score
            )

        elif derivative_direction == "NEUTRAL":
            derivatives_score = (
                derivative_score
                * 0.35
            )

        else:
            derivatives_score = 0.0

        # Risk / Reward
        risk_reward = self._float(
            levels.get(
                "risk_reward",
                0,
            )
        )

        if risk_reward <= 0:
            risk_reward_score = 0.0

        elif risk_reward < 1.0:
            risk_reward_score = 20.0

        elif risk_reward < 1.5:
            risk_reward_score = 40.0

        elif risk_reward < 2.0:
            risk_reward_score = 60.0

        elif risk_reward < 2.5:
            risk_reward_score = 75.0

        elif risk_reward < 3.0:
            risk_reward_score = 90.0

        else:
            risk_reward_score = 100.0

        # Market regime
        four_hour_direction = (
            self._direction(
                four_hour.get(
                    "direction"
                )
            )
        )

        four_hour_confidence = (
            self._clamp(
                four_hour.get(
                    "confidence",
                    0,
                )
            )
        )

        if (
            four_hour_direction
            == direction
        ):
            regime_score = (
                four_hour_confidence
            )

        elif four_hour_direction == "NEUTRAL":
            regime_score = (
                four_hour_confidence
                * 0.35
            )

        else:
            regime_score = 0.0

        return {
            "direction":
                direction,

            "timeframes":
                timeframes,

            "multi_timeframe":
                mtf,

            "order_book":
                order_book,

            "liquidations":
                liquidations,

            "derivatives":
                derivatives,

            "risk_reward":
                risk_reward,

            "entry":
                levels.get(
                    "entry",
                    0,
                ),

            "stop_loss":
                levels.get(
                    "stop_loss",
                    0,
                ),

            "tp1":
                levels.get(
                    "tp1",
                    0,
                ),

            "tp2":
                levels.get(
                    "tp2",
                    0,
                ),

            "tp3":
                levels.get(
                    "tp3",
                    0,
                ),

            "factor_scores": {
                "trend":
                    trend_score,

                "structure":
                    self._clamp(
                        structure_score
                    ),

                "momentum":
                    momentum_score,

                "volume":
                    volume_score,

                "support_resistance":
                    support_resistance,

                "multi_timeframe":
                    mtf_score,

                "liquidity":
                    liquidity_score,

                "derivatives":
                    derivatives_score,

                "risk_reward":
                    risk_reward_score,

                "market_regime":
                    regime_score,
            },
        }

    # =====================================================
    # MASTER ANALYSIS
    # =====================================================

    async def analyze(
        self,
        symbol: str,
        market: str = "futures",
        candle_limit: int = 200,
    ) -> dict[str, Any]:

        symbol = (
            str(
                symbol
            )
            .upper()
            .strip()
        )

        market = (
            str(
                market
            )
            .lower()
            .strip()
        )

        if not symbol.endswith(
            "USDT"
        ):
            symbol = (
                f"{symbol}USDT"
            )

        # -------------------------------------------------
        # MARKET SNAPSHOT
        # -------------------------------------------------

        raw = await (
            market_data_service
            .symbol_snapshot(
                symbol=symbol,
                market=market,
                candle_limit=candle_limit,
            )
        )

        if not isinstance(
            raw,
            dict,
        ):
            raise RuntimeError(
                "Market snapshot returned invalid data."
            )

        # -------------------------------------------------
        # TIMEFRAME ANALYSIS
        # -------------------------------------------------

        results = await asyncio.gather(
            *[
                self._analyze_timeframe(
                    raw,
                    timeframe,
                )
                for timeframe
                in self.CORE_TIMEFRAMES
            ],
            return_exceptions=True,
        )

        timeframes: dict[
            str,
            dict[str, Any],
        ] = {}

        for result in results:

            if isinstance(
                result,
                Exception,
            ):
                continue

            timeframe, data = result

            timeframes[
                timeframe
            ] = data

        for timeframe in (
            self.CORE_TIMEFRAMES
        ):

            if timeframe not in timeframes:
                timeframes[
                    timeframe
                ] = {
                    "success": False,
                    "direction":
                        "NEUTRAL",
                    "confidence":
                        0.0,
                    "score":
                        0.0,
                    "indicators":
                        {},
                    "structure":
                        {},
                    "reasons":
                        [],
                    "error":
                        "Timeframe analysis failed.",
                }

        # -------------------------------------------------
        # MTF
        # -------------------------------------------------

        mtf = mtf_engine.analyze(
            timeframes
        )

        if not isinstance(
            mtf,
            dict,
        ):
            mtf = {
                "direction":
                    "NEUTRAL",
                "weighted_confidence":
                    0.0,
                "agreement_ratio":
                    0.0,
                "aligned":
                    False,
                "publishable_mtf":
                    False,
            }

        direction = self._direction(
            mtf.get(
                "direction"
            )
        )

        # -------------------------------------------------
        # RAW DERIVATIVES
        # -------------------------------------------------

        raw_derivatives = raw.get(
            "derivatives",
            {},
        )

        if not isinstance(
            raw_derivatives,
            dict,
        ):
            raw_derivatives = {}

        # -------------------------------------------------
        # DERIVATIVES
        # -------------------------------------------------

        derivatives = (
            self.analyze_derivatives(
                raw_derivatives
            )
        )

        # -------------------------------------------------
        # ORDER BOOK
        # -------------------------------------------------

        order_book = (
            self.analyze_order_book(
                raw.get(
                    "order_book"
                )
            )
        )

        # -------------------------------------------------
        # LIQUIDATIONS
        # -------------------------------------------------

        liquidations = (
            self.analyze_liquidations(
                raw_derivatives.get(
                    "liquidation_orders",
                    [],
                )
            )
        )

        # -------------------------------------------------
        # LEVELS
        # -------------------------------------------------

        levels = (
            self._calculate_levels(
                direction,
                timeframes,
            )
        )

        risk_reward = self._float(
            levels.get(
                "risk_reward",
                0,
            )
        )

        stop_quality = str(
            levels.get(
                "stop_quality",
                "INVALID",
            )
        ).upper()

        levels_valid = (
            direction
            in {
                "LONG",
                "SHORT",
            }
            and self._float(
                levels.get(
                    "entry",
                    0,
                )
            ) > 0
            and self._float(
                levels.get(
                    "stop_loss",
                    0,
                )
            ) > 0
            and risk_reward >= 2.0
            and stop_quality == "VALID"
        )

        # -------------------------------------------------
        # CONFIDENCE INPUT
        # -------------------------------------------------

        confidence_input = (
            self._build_confidence_input(
                direction=direction,
                timeframes=timeframes,
                mtf=mtf,
                order_book=order_book,
                liquidations=liquidations,
                derivatives=derivatives,
                levels=levels,
            )
        )

        # -------------------------------------------------
        # CONFIDENCE ENGINE
        # -------------------------------------------------

        confidence_result = (
            confidence_engine.evaluate(
                confidence_input
            )
        )

        if not isinstance(
            confidence_result,
            dict,
        ):
            confidence_result = {
                "success": False,
                "direction":
                    direction,
                "confidence":
                    0.0,
                "decision":
                    "NO_TRADE",
                "factors":
                    {},
            }

        confidence = self._clamp(
            confidence_result.get(
                "confidence",
                0,
            )
        )

        # -------------------------------------------------
        # HARD GATES
        # -------------------------------------------------

        publishable_mtf = bool(
            mtf.get(
                "publishable_mtf",
                False,
            )
        )

        if not publishable_mtf:
            confidence = min(
                confidence,
                84.99,
            )

        four_hour = timeframes.get(
            "4h",
            {},
        )

        if not isinstance(
            four_hour,
            dict,
        ):
            four_hour = {}

        four_hour_direction = (
            self._direction(
                four_hour.get(
                    "direction"
                )
            )
        )

        # 4H conflict is a penalty,
        # not a Python-scope failure.
        if (
            direction
            in {
                "LONG",
                "SHORT",
            }
            and four_hour_direction
            in {
                "LONG",
                "SHORT",
            }
            and four_hour_direction
            != direction
        ):

            confidence = max(
                0.0,
                confidence - 10.0,
            )

        publishable = (
            direction
            in {
                "LONG",
                "SHORT",
            }
            and confidence
            >= self.MIN_CONFIDENCE
            and publishable_mtf
            and levels_valid
        )

        # -------------------------------------------------
        # REASONS
        # -------------------------------------------------

        reasons: list[str] = []

        for timeframe in (
            self.CORE_TIMEFRAMES
        ):

            item = timeframes.get(
                timeframe,
                {},
            )

            if not isinstance(
                item,
                dict,
            ):
                continue

            item_reasons = item.get(
                "reasons",
                [],
            )

            if isinstance(
                item_reasons,
                list,
            ):
                reasons.extend(
                    str(x)
                    for x
                    in item_reasons
                )

        derivative_reasons = (
            derivatives.get(
                "reasons",
                [],
            )
        )

        if isinstance(
            derivative_reasons,
            list,
        ):
            reasons.extend(
                str(x)
                for x
                in derivative_reasons
            )

        if (
            order_book.get(
                "direction"
            )
            == direction
        ):
            reasons.append(
                "Order book supports the direction."
            )

        if (
            liquidations.get(
                "direction"
            )
            == direction
        ):
            reasons.append(
                "Liquidation flow supports the direction."
            )

        if publishable_mtf:
            reasons.append(
                "15m, 1H and 4H are aligned."
            )
        else:
            reasons.append(
                "Strict MTF alignment has not been confirmed."
            )

        if risk_reward >= 2.0:
            reasons.append(
                f"Risk/reward is {risk_reward:.2f}R."
            )

        if not levels_valid:
            reasons.append(
                "Trade levels failed the minimum risk gate."
            )

        if (
            four_hour_direction
            in {
                "LONG",
                "SHORT",
            }
            and four_hour_direction
            != direction
        ):
            reasons.append(
                "4H conflicts with the selected direction."
            )

        # -------------------------------------------------
        # FACTOR SCORES
        # -------------------------------------------------

        factor_scores = (
            confidence_result.get(
                "factors",
                confidence_input.get(
                    "factor_scores",
                    {},
                ),
            )
        )

        if not isinstance(
            factor_scores,
            dict,
        ):
            factor_scores = {}

        factor_scores = {
            str(key): round(
                self._float(value),
                2,
            )
            for key, value
            in factor_scores.items()
        }

        # -------------------------------------------------
        # 24-POINT ANALYSIS
        # -------------------------------------------------

        points: dict[
            str,
            dict[str, Any],
        ] = {}

        confirmation_count = 0

        def add_point(
            number: int,
            name: str,
            status: str,
            value: Any = None,
            point_direction: str = "NEUTRAL",
        ) -> None:

            nonlocal confirmation_count

            if (
                number <= 20
                and status == "CONFIRMED"
            ):
                confirmation_count += 1

            point = {
                "number":
                    number,
                "name":
                    name,
                "status":
                    status,
                "direction":
                    point_direction,
            }

            if value is not None:
                point["value"] = value

            points[
                str(number)
            ] = point

        # 1 Market Regime
        add_point(
            1,
            "Market Regime",
            "CONFIRMED"
            if (
                four_hour_direction
                == direction
            )
            else "CONFLICT",
            four_hour_direction,
            four_hour_direction,
        )

        # 2 Market Structure
        one_hour = timeframes.get(
            "1h",
            {},
        )

        if not isinstance(
            one_hour,
            dict,
        ):
            one_hour = {}

        one_hour_structure = (
            one_hour.get(
                "structure",
                {},
            )
        )

        if not isinstance(
            one_hour_structure,
            dict,
        ):
            one_hour_structure = {}

        one_hour_structure_direction = (
            self._direction(
                one_hour_structure.get(
                    "direction"
                )
            )
        )

        add_point(
            2,
            "Market Structure",
            "CONFIRMED"
            if (
                one_hour_structure_direction
                == direction
            )
            else "NEUTRAL",
            one_hour_structure_direction,
            one_hour_structure_direction,
        )

        # 3 MTF
        add_point(
            3,
            "Multi-Timeframe Confirmation",
            "CONFIRMED"
            if publishable_mtf
            else "CONFLICT",
            mtf.get(
                "direction"
            ),
            self._direction(
                mtf.get(
                    "direction"
                )
            ),
        )

        # 4 Entry Location
        fifteen = timeframes.get(
            "15m",
            {},
        )

        if not isinstance(
            fifteen,
            dict,
        ):
            fifteen = {}

        fifteen_structure = (
            fifteen.get(
                "structure",
                {},
            )
        )

        if not isinstance(
            fifteen_structure,
            dict,
        ):
            fifteen_structure = {}

        sr = fifteen_structure.get(
            "support_resistance",
            {},
        )

        if not isinstance(
            sr,
            dict,
        ):
            sr = {}

        sr_location = str(
            sr.get(
                "location",
                "",
            )
        ).upper()

        entry_location_ok = (
            (
                direction == "LONG"
                and sr_location
                == "NEAR_SUPPORT"
            )
            or
            (
                direction == "SHORT"
                and sr_location
                == "NEAR_RESISTANCE"
            )
        )

        add_point(
            4,
            "Entry Location",
            "CONFIRMED"
            if entry_location_ok
            else (
                "NEUTRAL"
                if sr_location
                else "UNKNOWN"
            ),
            sr_location,
            direction
            if entry_location_ok
            else "NEUTRAL",
        )

        # 5 Liquidity Sweep
        add_point(
            5,
            "Liquidity Sweep",
            "PENDING",
            "PENDING_ENGINE",
        )

        # 6 VWAP
        fifteen_indicators = (
            fifteen.get(
                "indicators",
                {},
            )
        )

        if not isinstance(
            fifteen_indicators,
            dict,
        ):
            fifteen_indicators = {}

        price = self._float(
            fifteen_indicators.get(
                "price",
                0,
            )
        )

        vwap = self._float(
            fifteen_indicators.get(
                "vwap",
                0,
            )
        )

        if direction == "LONG":
            vwap_ok = (
                price > 0
                and vwap > 0
                and price > vwap
            )
        else:
            vwap_ok = (
                price > 0
                and vwap > 0
                and price < vwap
            )

        add_point(
            6,
            "VWAP",
            "CONFIRMED"
            if vwap_ok
            else "NEUTRAL",
            vwap,
            direction
            if vwap_ok
            else "NEUTRAL",
        )

        # 7 ATR
        atr_percent = self._float(
            fifteen_indicators.get(
                "atr_percent",
                0,
            )
        )

        add_point(
            7,
            "ATR / Volatility",
            "CONFIRMED"
            if atr_percent > 0
            else "UNKNOWN",
            atr_percent,
        )

        # 8 Momentum
        momentum = self._float(
            fifteen_indicators.get(
                "momentum",
                0,
            )
        )

        momentum_ok = (
            (
                direction == "LONG"
                and momentum > 0
            )
            or
            (
                direction == "SHORT"
                and momentum < 0
            )
        )

        add_point(
            8,
            "Momentum",
            "CONFIRMED"
            if momentum_ok
            else "NEUTRAL",
            momentum,
            direction
            if momentum_ok
            else "NEUTRAL",
        )

        # 9 Divergence
        add_point(
            9,
            "Divergence",
            "PENDING",
            "PENDING_ENGINE",
        )

        # 10 Breakout
        breakout = fifteen_indicators.get(
            "breakout",
            {},
        )

        if not isinstance(
            breakout,
            dict,
        ):
            breakout = {}

        breakout_direction = (
            self._direction(
                breakout.get(
                    "direction"
                )
            )
        )

        breakout_ok = (
            bool(
                breakout.get(
                    "breakout",
                    False,
                )
            )
            and breakout_direction
            == direction
        )

        add_point(
            10,
            "Breakout",
            "CONFIRMED"
            if breakout_ok
            else "NEUTRAL",
            breakout.get(
                "level"
            ),
            breakout_direction,
        )

        # 11 Retest
        add_point(
            11,
            "Retest",
            "PENDING",
            "PENDING_ENGINE",
        )

        # 12 Derivatives
        derivatives_ok = (
            derivatives.get(
                "direction"
            )
            == direction
            and self._float(
                derivatives.get(
                    "score",
                    0,
                )
            ) > 0
        )

        add_point(
            12,
            "Derivatives",
            "CONFIRMED"
            if derivatives_ok
            else "NEUTRAL",
            derivatives.get(
                "score",
                0,
            ),
            self._direction(
                derivatives.get(
                    "direction"
                )
            ),
        )

        # 13 Liquidations
        liquidations_ok = (
            liquidations.get(
                "direction"
            )
            == direction
            and self._float(
                liquidations.get(
                    "score",
                    0,
                )
            ) > 0
        )

        add_point(
            13,
            "Liquidations",
            "CONFIRMED"
            if liquidations_ok
            else "NEUTRAL",
            liquidations.get(
                "score",
                0,
            ),
            self._direction(
                liquidations.get(
                    "direction"
                )
            ),
        )

        # 14 Order Book
        order_book_ok = (
            order_book.get(
                "direction"
            )
            == direction
            and self._float(
                order_book.get(
                    "score",
                    0,
                )
            ) > 0
        )

        add_point(
            14,
            "Order Book",
            "CONFIRMED"
            if order_book_ok
            else "NEUTRAL",
            order_book.get(
                "score",
                0,
            ),
            self._direction(
                order_book.get(
                    "direction"
                )
            ),
        )

        # 15 Tradeability
        add_point(
            15,
            "Tradeability",
            "CONFIRMED"
            if levels_valid
            else "REJECTED",
            risk_reward,
            direction,
        )

        # 16 News
        add_point(
            16,
            "News / Event Risk",
            "PENDING",
            "NEWS_PROVIDER_NOT_CONNECTED",
        )

        # 17 BTC context
        add_point(
            17,
            "BTC Market Context",
            "PENDING",
            "BTC_CONTEXT_PENDING",
        )

        # 18 Relative strength
        add_point(
            18,
            "Relative Strength",
            "PENDING",
            "RELATIVE_STRENGTH_PENDING",
        )

        # 19 Risk / Reward
        add_point(
            19,
            "Risk / Reward",
            "CONFIRMED"
            if risk_reward >= 2.0
            else "REJECTED",
            risk_reward,
            direction,
        )

        # 20 Stop quality
        add_point(
            20,
            "Stop Quality",
            "CONFIRMED"
            if (
                stop_quality
                == "VALID"
            )
            else "REJECTED",
            stop_quality,
            direction,
        )

        # 21 Position sizing
        add_point(
            21,
            "Position Sizing",
            "PENDING",
            "ACCOUNT_RISK_PENDING",
        )

        # 22 Portfolio risk
        add_point(
            22,
            "Portfolio Risk",
            "PENDING",
            "PORTFOLIO_STATE_PENDING",
        )

        # 23 Execution
        add_point(
            23,
            "Execution Quality",
            "PENDING",
            "EXECUTION_ENGINE_PENDING",
        )

        # 24 Freshness
        add_point(
            24,
            "Signal Freshness",
            "CONFIRMED",
            "CURRENT_SCAN",
        )

        # -------------------------------------------------
        # FINAL CONFIDENCE
        # -------------------------------------------------

        confidence_result = dict(
            confidence_result
        )

        confidence_result[
            "direction"
        ] = direction

        confidence_result[
            "confidence"
        ] = round(
            confidence,
            2,
        )

        confidence_result[
            "passed"
        ] = publishable

        confidence_result[
            "decision"
        ] = (
            "QUALIFIED"
            if publishable
            else (
                "REJECTED"
                if direction
                in {
                    "LONG",
                    "SHORT",
                }
                else "NO_TRADE"
            )
        )

        confidence_result[
            "factors"
        ] = factor_scores

        return {
            "success": True,
            "symbol": symbol,
            "market": market,
            "direction": direction,
            "confidence": round(
                confidence,
                2,
            ),
            "publishable": publishable,
            "signal_status": (
                "PUBLISHABLE"
                if publishable
                else (
                    "NO_TRADE"
                    if direction == "NEUTRAL"
                    else "UNQUALIFIED"
                )
            ),
            "core_timeframes":
                list(
                    self.CORE_TIMEFRAMES
                ),
            "timeframes":
                timeframes,
            "multi_timeframe":
                mtf,
            "order_book":
                order_book,
            "liquidations":
                liquidations,
            "derivatives":
                derivatives,
            "confidence_engine":
                confidence_result,
            "factor_scores":
                factor_scores,
            "entry":
                levels.get(
                    "entry",
                    0,
                ),
            "stop_loss":
                levels.get(
                    "stop_loss",
                    0,
                ),
            "tp1":
                levels.get(
                    "tp1",
                    0,
                ),
            "tp2":
                levels.get(
                    "tp2",
                    0,
                ),
            "tp3":
                levels.get(
                    "tp3",
                    0,
                ),
            "risk_reward":
                risk_reward,
            "stop_quality":
                stop_quality,
            "reasons":
                list(
                    dict.fromkeys(
                        reasons
                    )
                ),
            "24_point_analysis": {
                "points":
                    points,
                "market_confirmation_count":
                    confirmation_count,
                "market_confirmation_total":
                    20,
                "risk_gate_count":
                    sum(
                        1
                        for number
                        in (
                            "19",
                            "20",
                        )
                        if points.get(
                            number,
                            {},
                        ).get(
                            "status"
                        )
                        == "CONFIRMED"
                    ),
                "risk_gate_total":
                    2,
            },
            "raw_market_data_available":
                True,
        }


# =========================================================
# SHARED INSTANCE
# =========================================================

master_analysis_engine = (
    MasterAnalysisEngine()
)


__all__ = [
    "MasterAnalysisEngine",
    "master_analysis_engine",
]
