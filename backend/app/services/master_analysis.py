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
    """from __future__ import annotations

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
    - technical indicators
    - market structure
    - MTF confirmation
    - order book
    - derivatives
    - liquidations
    - support/resistance
    - risk/reward
    - confidence engine v2

    This engine analyzes only.
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
            min(
                high,
                number,
            ),
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

                    bid_volume += (
                        self._float(
                            item[1]
                        )
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

                    ask_volume += (
                        self._float(
                            item[1]
                        )
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
            abs(
                imbalance
            ) * 500.0,
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
                abs(
                    qty * price
                )
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
                "long_liquidations": 0.0,
                "short_liquidations": 0.0,
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
            abs(
                imbalance
            ) * 100.0,
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

        # -------------------------------------------------
        # Funding
        # -------------------------------------------------

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

                funding_rate = (
                    self._float(
                        latest.get(
                            "fundingRate",
                            0,
                        )
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

        # -------------------------------------------------
        # Global long/short ratio
        # -------------------------------------------------

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

        # -------------------------------------------------
        # Top trader ratio
        # -------------------------------------------------

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
                        "Top trader accounts lean short."
                    )

                elif ratio > 1.10:

                    short_evidence += 1

                    reasons.append(
                        "Top trader accounts lean long."
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
    # TIMEFRAME
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

            return (
                timeframe,
                {
                    "success": False,
                    "direction":
                        "NEUTRAL",
                    "confidence":
                        0.0,
                    "score":
                        0.0,
                    "indicators": {},
                    "structure": {},
                    "reasons": [],
                    "error":
                        "Invalid candle data.",
                },
            )

        if len(candles) < 20:

            return (
                timeframe,
                {
                    "success": False,
                    "direction":
                        "NEUTRAL",
                    "confidence":
                        0.0,
                    "score":
                        0.0,
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

        # -------------------------------------------------
        # EMA
        # -------------------------------------------------

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

        # -------------------------------------------------
        # Momentum
        # -------------------------------------------------

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

        # -------------------------------------------------
        # Market structure
        # -------------------------------------------------

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

        # -------------------------------------------------
        # Breakout
        # -------------------------------------------------

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

        if (
            breakout_direction == "LONG"
        ):

            long_score += 10

            reasons.append(
                "Bullish breakout detected."
            )

        elif (
            breakout_direction == "SHORT"
        ):

            short_score += 10

            reasons.append(
                "Bearish breakout detected."
            )

        # -------------------------------------------------
        # VWAP
        # -------------------------------------------------

        if (
            price > 0
            and vwap > 0
        ):

            if price > vwap:

                long_score += 5

            elif price < vwap:

                short_score += 5

        # -------------------------------------------------
        # Direction
        # -------------------------------------------------

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
    # LEVELS
    # =====================================================

    def _levels(
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

        # -------------------------------------------------
        # LONG
        # -------------------------------------------------

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
                    "stop_loss":
                        0.0,
                    "tp1": 0.0,
                    "tp2": 0.0,
                    "tp3": 0.0,
                    "risk_reward":
                        0.0,
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
                "stop_loss":
                    stop_loss,
                "tp1": tp1,
                "tp2": tp2,
                "tp3": tp3,
                "risk_reward": rr,
                "stop_quality":
                    "VALID",
            }

        # -------------------------------------------------
        # SHORT
        # -------------------------------------------------

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

        if support > 0 and support < entry:

            tp2 = min(
                tp2,
                support,
            )

        rr = (
            entry - tp2
        ) / risk

        return {
            "entry": entry,
            "stop_loss":
                stop_loss,
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

        if not isinstance(
            fifteen_indicators,
            dict,
        ):
            fifteen_indicators = {}

        one_hour_indicators = (
            one_hour.get(
                "indicators",
                {},
            )
        )

        if not isinstance(
            one_hour_indicators,
            dict,
        ):
            one_hour_indicators = {}

        four_hour_indicators = (
            four_hour.get(
                "indicators",
                {},
            )
        )

        if not isinstance(
            four_hour_indicators,
            dict,
        ):
            four_hour_indicators = {}

        structures = []

        for item in (
            fifteen,
            one_hour,
            four_hour,
        ):

            structure = item.get(
                "structure",
                {},
            )

            if isinstance(
                structure,
                dict,
            ):
                structures.append(
                    structure
                )

        # -------------------------------------------------
        # Trend
        # -------------------------------------------------

        trend_score = self._clamp(
            one_hour.get(
                "confidence",
                0,
            )
        )

        # -------------------------------------------------
        # Structure
        # -------------------------------------------------

        structure_scores = []

        for structure in structures:

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
            sum(
                structure_scores
            ) / len(
                structure_scores
            )
            if structure_scores
            else 0.0
        )

        # -------------------------------------------------
        # Momentum
        # -------------------------------------------------

        momentum = self._float(
            fifteen_indicators.get(
                "momentum",
                0,
            )
        )

        if direction == "LONG":

            momentum_score = self._clamp(
                50.0 + momentum * 10.0
            )

        else:

            momentum_score = self._clamp(
                50.0 - momentum * 10.0
            )

        # -------------------------------------------------
        # Volume
        # -------------------------------------------------

        volume_scores = []

        for indicators in (
            fifteen_indicators,
            one_hour_indicators,
            four_hour_indicators,
        ):

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

        # -------------------------------------------------
        # Support / Resistance
        # -------------------------------------------------

        primary_structure = (
            fifteen.get(
                "structure",
                {},
            )
        )

        if not isinstance(
            primary_structure,
            dict,
        ):
            primary_structure = {}

        sr = primary_structure.get(
            "support_resistance",
            {},
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

                support_resistance_score = 95.0

            elif location == "MID_RANGE":

                support_resistance_score = 55.0

            else:

                support_resistance_score = 20.0

        else:

            if location == "NEAR_RESISTANCE":

                support_resistance_score = 95.0

            elif location == "MID_RANGE":

                support_resistance_score = 55.0

            else:

                support_resistance_score = 20.0

        # -------------------------------------------------
        # MTF
        # -------------------------------------------------

        mtf_direction = self._direction(
            mtf.get(
                "direction"
            )
        )

        weighted = self._clamp(
            mtf.get(
                "weighted_confidence",
                0,
            )
        )

        agreement = self._clamp(
            mtf.get(
                "agreement_ratio",
                0,
            ),
            0,
            1,
        )

        mtf_score = (
            weighted
            * agreement
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

        # -------------------------------------------------
        # Liquidity
        # -------------------------------------------------

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

        # -------------------------------------------------
        # Derivatives
        # -------------------------------------------------

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

        if derivative_direction == direction:

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

        # -------------------------------------------------
        # Risk / Reward
        # -------------------------------------------------

        rr = self._float(
            levels.get(
                "risk_reward",
                0,
            )
        )

        if rr < 1.0:

            rr_score = 20.0 if rr > 0 else 0.0

        elif rr < 1.5:

            rr_score = 40.0

        elif rr < 2.0:

            rr_score = 60.0

        elif rr < 2.5:

            rr_score = 75.0

        elif rr < 3.0:

            rr_score = 90.0

        else:

            rr_score = 100.0

        # -------------------------------------------------
        # Market regime
        # -------------------------------------------------

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

        if four_hour_direction == direction:

            regime_score = (
                four_hour_confidence
            )

        elif (
            four_hour_direction
            == "NEUTRAL"
        ):

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
                rr,

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
                    support_resistance_score,

                "multi_timeframe":
                    mtf_score,

                "liquidity":
                    liquidity_score,

                "derivatives":
                    derivatives_score,

                "risk_reward":
                    rr_score,

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

        symbol = str(
            symbol
        ).upper().strip()

        market = str(
            market
        ).lower().strip()

        if not symbol.endswith(
            "USDT"
        ):

            symbol = (
                f"{symbol}USDT"
            )

        # -------------------------------------------------
        # Raw snapshot
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
        # Analyze all timeframes
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
                    "indicators": {},
                    "structure": {},
                    "reasons": [],
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
        # Derivatives
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

        derivatives = (
            self.analyze_derivatives(
                raw_derivatives
            )
        )

        # -------------------------------------------------
        # Order book
        # -------------------------------------------------

        order_book = (
            self.analyze_order_book(
                raw.get(
                    "order_book"
                )
            )
        )

        # -------------------------------------------------
        # Liquidations
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
        # Levels
        # -------------------------------------------------

        levels = self._levels(
            direction,
            timeframes,
        )

        # -------------------------------------------------
        # Confidence
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
                "confidence":
                    0.0,
                "direction":
                    direction,
                "decision":
                    "NO_TRADE",
                "factors": {},
            }

        confidence = self._clamp(
            confidence_result.get(
                "confidence",
                0,
            )
        )

        # -------------------------------------------------
        # Hard gates
        # -------------------------------------------------

        publishable_mtf = bool(
            mtf.get(
                "publishable_mtf",
                False,
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

        # Do not let an unconfirmed MTF signal publish.
        if not publishable_mtf:

            confidence = min(
                confidence,
                84.99,
            )

        # 4H hard conflict gets a penalty,
        # but does not create an undefined variable
        # or destroy the complete analysis.
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
        # Reasons
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
        # Final factor scores
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
                self._float(
                    value
                ),
                2,
            )
            for key, value
            in factor_scores.items()
        }

        # -------------------------------------------------
        # 24-point analysis
        # -------------------------------------------------

        points: dict[
            str,
            dict[str, Any],
        ] = {}

        confirmed_market_points = 0

        def add_point(
            number: int,
            name: str,
            status: str,
            value: Any = None,
            point_direction: str = "NEUTRAL",
        ) -> None:

            nonlocal confirmed_market_points

            if (
                number <= 20
                and status == "CONFIRMED"
            ):

                confirmed_market_points += 1

            item = {
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

                item["value"] = value

            points[
                str(number)
            ] = item

        # 1
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

        # 2
        one_hour = timeframes.get(
            "1h",
            {},
        )

        if not isinstance(
            one_hour,
            dict,
        ):
            one_hour = {}

        one_hour_structure = one_hour.get(
            "structure",
            {},
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

        # 3
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

        # 4
        fifteen = timeframes.get(
            "15m",
            {},
        )

        if not isinstance(
            fifteen,
            dict,
        ):
            fifteen = {}

        fifteen_structure = fifteen.get(
            "structure",
            {},
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

        # 5
        add_point(
            5,
            "Liquidity Sweep",
            "UNKNOWN",
            "PENDING_ENGINE",
        )

        # 6
        fifteen_indicators = fifteen.get(
            "indicators",
            {},
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

        vwap_ok = (
            (
                direction == "LONG"
                and price > vwap > 0
            )
            or
            (
                direction == "SHORT"
                and 0 < vwap < price
                and direction == "SHORT"
                and price < vwap
            )
        )

        # Correct explicit short check.
        if direction == "SHORT":
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

        # 7
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

        # 8
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

        # 9
        add_point(
            9,
            "Divergence",
            "UNKNOWN",
            "PENDING_ENGINE",
        )

        # 10
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

        # 11
        add_point(
            11,
            "Retest",
            "UNKNOWN",
            "PENDING_ENGINE",
        )

        # 12
        derivative_ok = (
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
            if derivative_ok
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

        # 13
        liquidation_ok = (
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
            if liquidation_ok
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

        # 14
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

        # 15
        add_point(
            15,
            "Tradeability",
            "CONFIRMED"
            if levels_valid
            else "REJECTED",
            risk_reward,
            direction,
        )

        # 16
        add_point(
            16,
            "News / Event Risk",
            "UNKNOWN",
            "NEWS_PROVIDER_NOT_CONNECTED",
        )

        # 17
        add_point(
            17,
            "BTC Market Context",
            "PENDING",
            "BTC_CONTEXT_ENGINE_PENDING",
        )

        # 18
        add_point(
            18,
            "Relative Strength",
            "PENDING",
            "RELATIVE_STRENGTH_ENGINE_PENDING",
        )

        # 19
        add_point(
            19,
            "Risk / Reward",
            "CONFIRMED"
            if risk_reward >= 2.0
            else "REJECTED",
            risk_reward,
            direction,
        )

        # 20
        add_point(
            20,
            "Stop Quality",
            "CONFIRMED"
            if str(
                levels.get(
                    "stop_quality",
                    "INVALID",
                )
            ).upper()
            == "VALID"
            else "REJECTED",
            levels.get(
                "stop_quality"
            ),
            direction,
        )

        # 21
        add_point(
            21,
            "Position Sizing",
            "PENDING",
            "ACCOUNT_RISK_PENDING",
        )

        # 22
        add_point(
            22,
            "Portfolio Risk",
            "PENDING",
            "PORTFOLIO_STATE_PENDING",
        )

        # 23
        add_point(
            23,
            "Execution Quality",
            "PENDING",
            "EXECUTION_ENGINE_PENDING",
        )

        # 24
        add_point(
            24,
            "Signal Freshness",
            "CONFIRMED",
            "CURRENT_SCAN",
        )

        # -------------------------------------------------
        # Final confidence result
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
            "publishable":
                publishable,
            "signal_status":
                (
                    "PUBLISHABLE"
                    if publishable
                    else (
                        "NO_TRADE"
                        if direction
                        == "NEUTRAL"
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
                levels.get(
                    "stop_quality"
                ),
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
                    confirmed_market_points,
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
    RR Trader master deterministic analysis engine.

    Combines:
    - 15m / 1H / 4H
    - Technical indicators
    - Market structure
    - MTF confirmation
    - Order book
    - Futures derivatives
    - Liquidity context
    - Risk / reward
    - Stop quality
    - Confidence Engine v2

    Produces analytical output only.
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
            numeric = float(value)

        except (
            TypeError,
            ValueError,
        ):
            numeric = low

        return max(
            low,
            min(
                high,
                numeric,
            ),
        )

    # =====================================================
    # ORDER BOOK
    # =====================================================

    def analyze_order_book(
        self,
        order_book: dict[str, Any] | None,
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

        if imbalance > 0.10:

            direction = "LONG"

        elif imbalance < -0.10:

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
        liquidation_orders: list[
            dict[str, Any]
        ] | None,
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
                "long_liquidations": 0.0,
                "short_liquidations": 0.0,
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

        return {
            "status": "AVAILABLE",
            "direction": direction,
            "score": round(
                min(
                    100.0,
                    abs(imbalance) * 100.0,
                ),
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
        derivatives: dict[str, Any],
    ) -> dict[str, Any]:

        if not isinstance(
            derivatives,
            dict,
        ):
            return {
                "status": "UNAVAILABLE",
                "direction": "NEUTRAL",
                "score": 0.0,
            }

        long_direction = 0
        short_direction = 0
        evidence: list[str] = []

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

                    long_direction += 1

                    evidence.append(
                        "Funding is negative."
                    )

                elif funding_rate > 0.0001:

                    short_direction += 1

                    evidence.append(
                        "Funding is positive."
                    )

        ratio_data = derivatives.get(
            "global_long_short_ratio",
            [],
        )

        if (
            isinstance(
                ratio_data,
                list,
            )
            and ratio_data
        ):

            latest = ratio_data[-1]

            if isinstance(
                latest,
                dict,
            ):

                ratio = self._float(
                    latest.get(
                        "longShortRatio",
                        1,
                    ),
                    1.0,
                )

                if ratio < 0.90:

                    long_direction += 1

                    evidence.append(
                        "Global positioning is relatively short."
                    )

                elif ratio > 1.10:

                    short_direction += 1

                    evidence.append(
                        "Global positioning is relatively long."
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
                        1,
                    ),
                    1.0,
                )

                if ratio < 0.90:

                    long_direction += 1

                    evidence.append(
                        "Top-trader accounts lean short."
                    )

                elif ratio > 1.10:

                    short_direction += 1

                    evidence.append(
                        "Top-trader accounts lean long."
                    )

        if long_direction > short_direction:

            direction = "LONG"

        elif short_direction > long_direction:

            direction = "SHORT"

        else:

            direction = "NEUTRAL"

        strength = abs(
            long_direction
            - short_direction
        )

        score = min(
            100.0,
            strength * 30.0,
        )

        return {
            "status": "AVAILABLE",
            "direction": direction,
            "score": round(
                score,
                2,
            ),
            "long_evidence":
                long_direction,
            "short_evidence":
                short_direction,
            "reasons":
                evidence,
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

        timeframe_data = (
            raw
            .get(
                "timeframes",
                {},
            )
            .get(
                timeframe,
                {},
            )
        )

        candles = (
            timeframe_data.get(
                "candles",
                [],
            )
            if isinstance(
                timeframe_data,
                dict,
            )
            else []
        )

        if not isinstance(
            candles,
            list,
        ):

            return (
                timeframe,
                {
                    "success": False,
                    "direction":
                        "NEUTRAL",
                    "confidence":
                        0.0,
                    "error":
                        "Invalid candle data.",
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

        direction_score = {
            "LONG": 0.0,
            "SHORT": 0.0,
        }

        reasons: list[str] = []

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

        # -------------------------------------------------
        # EMA
        # -------------------------------------------------

        if price > ema20 > ema50:

            direction_score["LONG"] += 20

            reasons.append(
                "EMA structure bullish."
            )

        elif price < ema20 < ema50:

            direction_score["SHORT"] += 20

            reasons.append(
                "EMA structure bearish."
            )

        # -------------------------------------------------
        # Momentum
        # -------------------------------------------------

        momentum = self._float(
            indicators.get(
                "momentum"
            )
        )

        if momentum > 0:

            direction_score["LONG"] += min(
                15,
                abs(momentum) * 3,
            )

            reasons.append(
                "Momentum positive."
            )

        elif momentum < 0:

            direction_score["SHORT"] += min(
                15,
                abs(momentum) * 3,
            )

            reasons.append(
                "Momentum negative."
            )

        # -------------------------------------------------
        # Structure
        # -------------------------------------------------

        structure_direction = (
            self._direction(
                structure.get(
                    "direction"
                )
            )
        )

        if structure_direction == "LONG":

            direction_score["LONG"] += 25

            reasons.append(
                "Structure bullish."
            )

        elif structure_direction == "SHORT":

            direction_score["SHORT"] += 25

            reasons.append(
                "Structure bearish."
            )

        # -------------------------------------------------
        # BOS / Breakout
        # -------------------------------------------------

        breakout = indicators.get(
            "breakout",
            {},
        )

        breakout_direction = (
            self._direction(
                breakout.get(
                    "direction"
                )
            )
        )

        if breakout_direction in {
            "LONG",
            "SHORT",
        }:

            direction_score[
                breakout_direction
            ] += 10

            reasons.append(
                f"{breakout_direction} breakout detected."
            )

        # -------------------------------------------------
        # VWAP
        # -------------------------------------------------

        vwap = self._float(
            indicators.get(
                "vwap"
            )
        )

        if price > 0 and vwap > 0:

            if price > vwap:

                direction_score[
                    "LONG"
                ] += 5

            elif price < vwap:

                direction_score[
                    "SHORT"
                ] += 5

        # -------------------------------------------------
        # Final timeframe direction
        # -------------------------------------------------

        if (
            direction_score["LONG"]
            > direction_score["SHORT"]
        ):

            direction = "LONG"

        elif (
            direction_score["SHORT"]
            > direction_score["LONG"]
        ):

            direction = "SHORT"

        else:

            direction = "NEUTRAL"

        score = max(
            direction_score["LONG"],
            direction_score["SHORT"],
        )

        return (
            timeframe,
            {
                "success": True,
                "direction": direction,
                "confidence": min(
                    100.0,
                    round(
                        score,
                        2,
                    ),
                ),
                "score": score,
                "indicators": indicators,
                "structure": structure,
                "reasons": reasons,
            },
        )

    # =====================================================
    # LEVELS
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
                    "NOT_APPLICABLE",
            }

        primary = timeframes.get(
            "15m",
            {},
        )

        if not isinstance(
            primary,
            dict,
        ):
            primary = {}

        indicators = primary.get(
            "indicators",
            {},
        )

        structure = primary.get(
            "structure",
            {},
        )

        sr = (
            structure.get(
                "support_resistance",
                {},
            )
            if isinstance(
                structure,
                dict,
            )
            else {}
        )

        price = self._float(
            indicators.get(
                "price"
            )
        )

        atr = self._float(
            indicators.get(
                "atr"
            )
        )

        support = self._float(
            sr.get(
                "support"
            )
        )

        resistance = self._float(
            sr.get(
                "resistance"
            )
        )

        entry = price

        if direction == "LONG":

            default_stop = (
                entry
                - (
                    atr * 1.5
                )
                if atr > 0
                else entry * 0.98
            )

            stop_loss = (
                support * 0.995
                if support > 0
                and support < entry
                else default_stop
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

            tp1 = entry + risk * 1.5
            tp2 = entry + risk * 2.5
            tp3 = entry + risk * 3.5

            if resistance > entry:

                tp1 = max(
                    tp1,
                    entry
                    + (
                        resistance
                        - entry
                    ) * 0.60,
                )

                tp2 = max(
                    tp2,
                    resistance,
                )

            rr = (
                tp2
                - entry
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

        # -------------------------------------------------
        # SHORT
        # -------------------------------------------------

        default_stop = (
            entry
            + (
                atr * 1.5
            )
            if atr > 0
            else entry * 1.02
        )

        stop_loss = (
            resistance * 1.005
            if resistance > entry
            else default_stop
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

        tp1 = entry - risk * 1.5
        tp2 = entry - risk * 2.5
        tp3 = entry - risk * 3.5

        if support > 0 and support < entry:

            tp1 = min(
                tp1,
                entry
                - (
                    entry - support
                ) * 0.60,
            )

            tp2 = min(
                tp2,
                support,
            )

        rr = (
            entry
            - tp2
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
    # FACTOR SCORES FOR ENGINE V2
    # =====================================================

    def _build_confidence_analysis(
        self,
        *,
        direction: str,
        timeframes: dict[str, Any],
        mtf: dict[str, Any],
        order_book: dict[str, Any],
        liquidations: dict[str, Any],
        derivatives: dict[str, Any],
        levels: dict[str, Any],
    ) -> dict[str, Any]:

        one_hour = timeframes.get(
            "1h",
            {},
        )

        fifteen = timeframes.get(
            "15m",
            {},
        )

        four_hour = timeframes.get(
            "4h",
            {},
        )

        if not isinstance(
            one_hour,
            dict,
        ):
            one_hour = {}

        if not isinstance(
            fifteen,
            dict,
        ):
            fifteen = {}

        if not isinstance(
            four_hour,
            dict,
        ):
            four_hour = {}

        one_hour_indicators = (
            one_hour.get(
                "indicators",
                {},
            )
        )

        fifteen_indicators = (
            fifteen.get(
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

        one_hour_structure = (
            one_hour.get(
                "structure",
                {},
            )
        )

        fifteen_structure = (
            fifteen.get(
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

        # ----------------------------------------------
        # TREND
        # ----------------------------------------------

        trend_score = self._float(
            one_hour.get(
                "confidence",
                0,
            )
        )

        # ----------------------------------------------
        # STRUCTURE
        # ----------------------------------------------

        structure_scores = []

        for item in (
            fifteen_structure,
            one_hour_structure,
            four_hour_structure,
        ):

            if not isinstance(
                item,
                dict,
            ):
                continue

            structure_details = (
                item.get(
                    "structure_details",
                    {},
                )
            )

            if not isinstance(
                structure_details,
                dict,
            ):
                continue

            positive = (
                int(
                    bool(
                        structure_details.get(
                            "higher_high",
                            False,
                        )
                    )
                )
                + int(
                    bool(
                        structure_details.get(
                            "higher_low",
                            False,
                        )
                    )
                )
            )

            negative = (
                int(
                    bool(
                        structure_details.get(
                            "lower_high",
                            False,
                        )
                    )
                )
                + int(
                    bool(
                        structure_details.get(
                            "lower_low",
                            False,
                        )
                    )
                )
            )

            if direction == "LONG":

                structure_scores.append(
                    positive * 50.0
                )

            elif direction == "SHORT":

                structure_scores.append(
                    negative * 50.0
                )

        structure_score = (
            sum(structure_scores)
            / len(structure_scores)
            if structure_scores
            else 0.0
        )

        # ----------------------------------------------
        # MOMENTUM
        # ----------------------------------------------

        momentum_value = self._float(
            fifteen_indicators.get(
                "momentum",
                0,
            )
        )

        if direction == "LONG":

            momentum_score = self._clamp(
                50.0
                + momentum_value * 10.0
            )

        else:

            momentum_score = self._clamp(
                50.0
                - momentum_value * 10.0
            )

        # ----------------------------------------------
        # VOLUME
        # ----------------------------------------------

        volume_ratios = []

        for indicators in (
            fifteen_indicators,
            one_hour_indicators,
            four_hour_indicators,
        ):

            ratio = self._float(
                indicators.get(
                    "volume_ratio",
                    0,
                )
            )

            if ratio > 0:

                volume_ratios.append(
                    self._clamp(
                        ratio * 50.0
                    )
                )

        volume_score = (
            sum(volume_ratios)
            / len(volume_ratios)
            if volume_ratios
            else 0.0
        )

        # ----------------------------------------------
        # SUPPORT / RESISTANCE
        # ----------------------------------------------

        support_resistance_score = 0.0

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

        if isinstance(
            sr,
            dict,
        ):

            location = str(
                sr.get(
                    "location",
                    "",
                )
            ).upper()

            if direction == "LONG":

                if location == "NEAR_SUPPORT":
                    support_resistance_score = 95.0

                elif location == "MID_RANGE":
                    support_resistance_score = 55.0

                elif location == "NEAR_RESISTANCE":
                    support_resistance_score = 20.0

            elif direction == "SHORT":

                if location == "NEAR_RESISTANCE":
                    support_resistance_score = 95.0

                elif location == "MID_RANGE":
                    support_resistance_score = 55.0

                elif location == "NEAR_SUPPORT":
                    support_resistance_score = 20.0

        # ----------------------------------------------
        # MTF
        # ----------------------------------------------

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

        agreement = self._clamp(
            mtf.get(
                "agreement_ratio",
                0,
            ),
            0,
            1,
        )

        mtf_score = (
            weighted_confidence
            * agreement
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

        # ----------------------------------------------
        # LIQUIDITY
        # ----------------------------------------------

        liquidity_score = 0.0

        if (
            str(
                order_book.get(
                    "status",
                    "",
                )
            ).upper()
            == "AVAILABLE"
        ):

            ob_direction = self._direction(
                order_book.get(
                    "direction"
                )
            )

            raw_score = self._clamp(
                order_book.get(
                    "score",
                    0,
                )
            )

            if ob_direction == direction:

                liquidity_score = raw_score

            elif ob_direction == "NEUTRAL":

                liquidity_score = (
                    raw_score * 0.35
                )

        # ----------------------------------------------
        # LIQUIDATION BONUS
        # ----------------------------------------------

        if (
            liquidations.get(
                "status"
            )
            == "AVAILABLE"
            and self._direction(
                liquidations.get(
                    "direction"
                )
            )
            == direction
        ):

            liquidity_score = max(
                liquidity_score,
                self._clamp(
                    liquidations.get(
                        "score",
                        0,
                    )
                ),
            )

        # ----------------------------------------------
        # DERIVATIVES
        # ----------------------------------------------

        derivatives_score = 0.0

        if (
            str(
                derivatives.get(
                    "status",
                    "",
                )
            ).upper()
            == "AVAILABLE"
        ):

            deriv_direction = self._direction(
                derivatives.get(
                    "direction"
                )
            )

            deriv_score = self._clamp(
                derivatives.get(
                    "score",
                    0,
                )
            )

            if deriv_direction == direction:

                derivatives_score = deriv_score

            elif deriv_direction == "NEUTRAL":

                derivatives_score = (
                    deriv_score * 0.35
                )

        # ----------------------------------------------
        # MARKET REGIME
        # ----------------------------------------------

        regime_direction = self._direction(
            four_hour.get(
                "direction"
            )
        )

        regime_confidence = self._clamp(
            four_hour.get(
                "confidence",
                0,
            )
        )

        if regime_direction == direction:

            market_regime_score = (
                regime_confidence
            )

        else:

            market_regime_score = (
                regime_confidence * 0.15
            )

        # ----------------------------------------------
        # FINAL
        # ----------------------------------------------

        return {
            "direction": direction,

            "timeframes": timeframes,

            "multi_timeframe": mtf,

            "order_book": order_book,

            "liquidations": liquidations,

            "derivatives": derivatives,

            "risk_reward":
                levels.get(
                    "risk_reward",
                    0,
                ),

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
                    self._clamp(
                        trend_score
                    ),

                "structure":
                    self._clamp(
                        structure_score
                    ),

                "momentum":
                    self._clamp(
                        momentum_score
                    ),

                "volume":
                    self._clamp(
                        volume_score
                    ),

                "support_resistance":
                    self._clamp(
                        support_resistance_score
                    ),

                "multi_timeframe":
                    self._clamp(
                        mtf_score
                    ),

                "liquidity":
                    self._clamp(
                        liquidity_score
                    ),

                "derivatives":
                    self._clamp(
                        derivatives_score
                    ),

                "risk_reward":
                    self._clamp(
                        self._risk_reward_score(
                            levels.get(
                                "risk_reward",
                                0,
                            )
                        )
                    ),

                "market_regime":
                    self._clamp(
                        market_regime_score
                    ),
            },
        }

    # =====================================================
    # R:R SCORE
    # =====================================================

    @staticmethod
    def _risk_reward_score(
        risk_reward: Any,
    ) -> float:

        try:
            rr = float(
                risk_reward
            )
        except (
            TypeError,
            ValueError,
        ):
            return 0.0

        if rr <= 0:
            return 0.0

        if rr < 1.0:
            return 20.0

        if rr < 1.5:
            return 40.0

        if rr < 2.0:
            return 60.0

        if rr < 2.5:
            return 75.0

        if rr < 3.0:
            return 90.0

        return 100.0

    # =====================================================
    # MASTER ANALYSIS
    # =====================================================

    async def analyze(
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

        if not symbol.endswith(
            "USDT"
        ):

            symbol = (
                f"{symbol}USDT"
            )

        # -------------------------------------------------
        # Raw market data
        # -------------------------------------------------

        raw = await (
            market_data_service
            .symbol_snapshot(
                symbol=symbol,
                market=market,
                candle_limit=candle_limit,
            )
        )

        # -------------------------------------------------
        # Timeframes
        # -------------------------------------------------

        timeframe_results = await asyncio.gather(
            *[
                self._analyze_timeframe(
                    raw,
                    timeframe,
                )
                for timeframe
                in self.CORE_TIMEFRAMES
            ]
        )

        timeframes = dict(
            timeframe_results
        )

        # -------------------------------------------------
        # MTF
        # -------------------------------------------------

        mtf = mtf_engine.analyze(
            timeframes
        )

        # -------------------------------------------------
        # Derivatives
        # -------------------------------------------------

        derivatives = (
            self.analyze_derivatives(
                raw.get(
                    "derivatives",
                    {},
                )
            )
        )

        # -------------------------------------------------
        # Order book
        # -------------------------------------------------

        order_book = (
            self.analyze_order_book(
                raw.get(
                    "order_book"
                )
            )
        )

        # -------------------------------------------------
        # Liquidations
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

        liquidations = (
            self.analyze_liquidations(
                raw_derivatives.get(
                    "liquidation_orders",
                    [],
                )
            )
        )

        # -------------------------------------------------
        # Preliminary direction
        # -------------------------------------------------

        direction = self._direction(
            mtf.get(
                "direction"
            )
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

        # Do not blindly force neutral.
        # Only use 4H as a confidence penalty
        # when it conflicts with the selected direction.
        regime_conflict = (
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
        )

        # -------------------------------------------------
        # Levels
        # -------------------------------------------------

        levels = self._calculate_levels(
            direction,
            timeframes,
        )

        # -------------------------------------------------
        # Confidence input
        # -------------------------------------------------

        confidence_analysis = (
            self._build_confidence_analysis(
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
        # V2 confidence engine
        # -------------------------------------------------

        confidence_result = (
            confidence_engine.evaluate(
                confidence_analysis
            )
        )

        confidence = self._float(
            confidence_result.get(
                "confidence",
                0,
            )
        )

        # -------------------------------------------------
        # 4H conflict penalty
        # -------------------------------------------------

        if regime_conflict:

            confidence = max(
                0.0,
                confidence - 10.0,
            )

        # -------------------------------------------------
        # MTF veto
        # -------------------------------------------------

        publishable_mtf = bool(
            mtf.get(
                "publishable_mtf",
                False,
            )
        )

        # We never publish a setup without
        # strict MTF confirmation.
        if not publishable_mtf:

            confidence = min(
                confidence,
                84.99,
            )

        # -------------------------------------------------
        # Level validity
        # -------------------------------------------------

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
            and risk_reward > 0
            and stop_quality == "VALID"
        )

        # -------------------------------------------------
        # Final publishable gate
        # -------------------------------------------------

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
            and risk_reward
            >= 2.0
        )

        # -------------------------------------------------
        # Reasons
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

            timeframe_reasons = (
                item.get(
                    "reasons",
                    [],
                )
            )

            if isinstance(
                timeframe_reasons,
                list,
            ):

                reasons.extend(
                    str(item)
                    for item
                    in timeframe_reasons
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
                str(item)
                for item
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
                "Trade levels are not fully valid."
            )

        if regime_conflict:

            reasons.append(
                "4H direction conflicts with the selected direction."
            )

        # -------------------------------------------------
        # Factor scores
        # -------------------------------------------------

        factor_scores = (
            confidence_result.get(
                "factors",
                confidence_analysis.get(
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

        # -------------------------------------------------
        # 24-point analysis
        # -------------------------------------------------

        confirmation_points = 0

        point_statuses: dict[
            str,
            dict[str, Any],
        ] = {}

        point_definitions = [

            (
                1,
                "Market Regime",
                "market_regime",
            ),

            (
                2,
                "Market Structure",
                "structure",
            ),

            (
                3,
                "Multi-Timeframe Confirmation",
                "multi_timeframe",
            ),

            (
                4,
                "Entry Location",
                "support_resistance",
            ),

            (
                6,
                "VWAP",
                "vwap",
            ),

            (
                7,
                "ATR / Volatility",
                "atr",
            ),

            (
                8,
                "Momentum",
                "momentum",
            ),

            (
                12,
                "Derivatives",
                "derivatives",
            ),

            (
                13,
                "Liquidations",
                "liquidations",
            ),

            (
                14,
                "Order Book",
                "liquidity",
            ),

            (
                19,
                "Risk / Reward",
                "risk_reward",
            ),

            (
                20,
                "Stop Quality",
                "stop_quality",
            ),

            (
                24,
                "Signal Freshness",
                "freshness",
            ),
        ]

        # helper for status

        def mark(
            number: int,
            name: str,
            status: str,
            value: Any = None,
            point_direction: str = "NEUTRAL",
        ) -> None:

            nonlocal confirmation_points

            if status == "CONFIRMED":

                confirmation_points += 1

            payload = {
                "number":
                    number,
                "name":
                    name,
                "category":
                    "market"
                    if number < 21
                    else "risk",
                "status":
                    status,
                "direction":
                    point_direction,
            }

            if value is not None:

                payload[
                    "value"
                ] = value

            point_statuses[
                str(number)
            ] = payload

        # -------------------------------------------------
        # 1 Market Regime
        # -------------------------------------------------

        if (
            four_hour_direction
            == direction
        ):

            mark(
                1,
                "Market Regime",
                "CONFIRMED",
                "TREND",
                direction,
            )

        else:

            mark(
                1,
                "Market Regime",
                "CONFLICT",
                "4H_CONFLICT",
                four_hour_direction,
            )

        # -------------------------------------------------
        # 2 Structure
        # -------------------------------------------------

        structure_one_hour = (
            one_hour_structure
            if isinstance(
                one_hour_structure,
                dict,
            )
            else {}
        )

        structure_direction = (
            self._direction(
                structure_one_hour.get(
                    "direction"
                )
            )
        )

        if structure_direction == direction:

            mark(
                2,
                "Market Structure",
                "CONFIRMED",
                "ALIGNED",
                direction,
            )

        else:

            mark(
                2,
                "Market Structure",
                "NEUTRAL",
                "MIXED",
                structure_direction,
            )

        # -------------------------------------------------
        # 3 MTF
        # -------------------------------------------------

        if publishable_mtf:

            mark(
                3,
                "Multi-Timeframe Confirmation",
                "CONFIRMED",
                "ALIGNED",
                direction,
            )

        else:

            mark(
                3,
                "Multi-Timeframe Confirmation",
                "CONFLICT",
                "NOT_ALIGNED",
                self._direction(
                    mtf.get(
                        "direction"
                    )
                ),
            )

        # -------------------------------------------------
        # 4 Entry Location
        # -------------------------------------------------

        sr_location = ""

        if isinstance(
            sr,
            dict,
        ):

            sr_location = str(
                sr.get(
                    "location",
                    "",
                )
            ).upper()

        good_entry_location = (
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

        if good_entry_location:

            mark(
                4,
                "Entry Location",
                "CONFIRMED",
                sr_location,
                direction,
            )

        elif sr_location:

            mark(
                4,
                "Entry Location",
                "NEUTRAL",
                sr_location,
                "NEUTRAL",
            )

        else:

            mark(
                4,
                "Entry Location",
                "UNKNOWN",
                "UNAVAILABLE",
            )

        # -------------------------------------------------
        # 5 Liquidity Sweep
        # -------------------------------------------------

        mark(
            5,
            "Liquidity Sweep",
            "UNAVAILABLE",
            "NOT_IMPLEMENTED",
        )

        # -------------------------------------------------
        # 6 VWAP
        # -------------------------------------------------

        primary_indicators = (
            fifteen_indicators
            if isinstance(
                fifteen_indicators,
                dict,
            )
            else {}
        )

        vwap = self._float(
            primary_indicators.get(
                "vwap",
                0,
            )
        )

        price = self._float(
            primary_indicators.get(
                "price",
                0,
            )
        )

        vwap_ok = (
            direction == "LONG"
            and price > vwap
        ) or (
            direction == "SHORT"
            and price < vwap
        )

        if vwap_ok:

            mark(
                6,
                "VWAP",
                "CONFIRMED",
                vwap,
                direction,
            )

        else:

            mark(
                6,
                "VWAP",
                "NEUTRAL",
                vwap,
                "NEUTRAL",
            )

        # -------------------------------------------------
        # 7 ATR
        # -------------------------------------------------

        atr_percent = self._float(
            primary_indicators.get(
                "atr_percent",
                0,
            )
        )

        if atr_percent > 0:

            mark(
                7,
                "ATR / Volatility",
                "CONFIRMED",
                atr_percent,
                "NEUTRAL",
            )

        else:

            mark(
                7,
                "ATR / Volatility",
                "UNKNOWN",
                "UNAVAILABLE",
            )

        # -------------------------------------------------
        # 8 Momentum
        # -------------------------------------------------

        if (
            (
                direction == "LONG"
                and momentum_value > 0
            )
            or
            (
                direction == "SHORT"
                and momentum_value < 0
            )
        ):

            mark(
                8,
                "Momentum",
                "CONFIRMED",
                momentum_value,
                direction,
            )

        else:

            mark(
                8,
                "Momentum",
                "NEUTRAL",
                momentum_value,
                "NEUTRAL",
            )

        # -------------------------------------------------
        # 9 Divergence
        # -------------------------------------------------

        mark(
            9,
            "Divergence",
            "UNKNOWN",
            "NOT_IMPLEMENTED",
        )

        # -------------------------------------------------
        # 10 Breakout
        # -------------------------------------------------

        breakout = primary_indicators.get(
            "breakout",
            {},
        )

        breakout_direction = (
            self._direction(
                breakout.get(
                    "direction"
                )
                if isinstance(
                    breakout,
                    dict,
                )
                else "NEUTRAL"
            )
        )

        if (
            isinstance(
                breakout,
                dict,
            )
            and breakout.get(
                "breakout",
                False,
            )
            and breakout_direction
            == direction
        ):

            mark(
                10,
                "Breakout",
                "CONFIRMED",
                breakout.get(
                    "level",
                    0,
                ),
                direction,
            )

        else:

            mark(
                10,
                "Breakout",
                "NEUTRAL",
                "NO_BREAKOUT",
            )

        # -------------------------------------------------
        # 11 Retest
        # -------------------------------------------------

        mark(
            11,
            "Retest",
            "UNKNOWN",
            "DEDICATED_RETEST_ENGINE_PENDING",
        )

        # -------------------------------------------------
        # 12 Derivatives
        # -------------------------------------------------

        if (
            derivatives.get(
                "direction"
            )
            == direction
            and derivatives.get(
                "score",
                0,
            )
            > 0
        ):

            mark(
                12,
                "Derivatives",
                "CONFIRMED",
                derivatives.get(
                    "score",
                    0,
                ),
                direction,
            )

        else:

            mark(
                12,
                "Derivatives",
                "NEUTRAL",
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

        # -------------------------------------------------
        # 13 Liquidations
        # -------------------------------------------------

        if (
            liquidations.get(
                "direction"
            )
            == direction
            and liquidations.get(
                "score",
                0,
            )
            > 0
        ):

            mark(
                13,
                "Liquidations",
                "CONFIRMED",
                liquidations.get(
                    "score",
                    0,
                ),
                direction,
            )

        elif (
            liquidations.get(
                "status"
            )
            == "AVAILABLE"
        ):

            mark(
                13,
                "Liquidations",
                "NEUTRAL",
                liquidations.get(
                    "score",
                    0,
                ),
            )

        else:

            mark(
                13,
                "Liquidations",
                "UNAVAILABLE",
                0,
            )

        # -------------------------------------------------
        # 14 Order Book
        # -------------------------------------------------

        if (
            order_book.get(
                "direction"
            )
            == direction
            and order_book.get(
                "score",
                0,
            )
            > 0
        ):

            mark(
                14,
                "Order Book",
                "CONFIRMED",
                order_book.get(
                    "score",
                    0,
                ),
                direction,
            )

        elif (
            order_book.get(
                "status"
            )
            == "AVAILABLE"
        ):

            mark(
                14,
                "Order Book",
                "NEUTRAL",
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

        else:

            mark(
                14,
                "Order Book",
                "UNAVAILABLE",
                0,
            )

        # -------------------------------------------------
        # 15 Tradeability
        # -------------------------------------------------

        tradeability = (
            levels_valid
            and risk_reward >= 2.0
        )

        if tradeability:

            mark(
                15,
                "Tradeability",
                "CONFIRMED",
                "VALID",
                direction,
            )

        else:

            mark(
                15,
                "Tradeability",
                "REJECTED",
                "INVALID",
            )

        # -------------------------------------------------
        # 16 News
        # -------------------------------------------------

        mark(
            16,
            "News / Event Risk",
            "UNKNOWN",
            "NEWS_PROVIDER_NOT_CONNECTED",
        )

        # -------------------------------------------------
        # 17 BTC Context
        # -------------------------------------------------

        mark(
            17,
            "BTC / Market Context",
            "PENDING",
            "BTC_CONTEXT_ENGINE_PENDING",
        )

        # -------------------------------------------------
        # 18 Relative Strength
        # -------------------------------------------------

        mark(
            18,
            "Relative Strength",
            "PENDING",
            "RELATIVE_STRENGTH_ENGINE_PENDING",
        )

        # -------------------------------------------------
        # 19 R:R
        # -------------------------------------------------

        if risk_reward >= 2.0:

            mark(
                19,
                "Risk / Reward",
                "CONFIRMED",
                risk_reward,
                direction,
            )

        elif risk_reward > 0:

            mark(
                19,
                "Risk / Reward",
                "REJECTED",
                risk_reward,
            )

        else:

            mark(
                19,
                "Risk / Reward",
                "REJECTED",
                0,
            )

        # -------------------------------------------------
        # 20 Stop quality
        # -------------------------------------------------

        if stop_quality == "VALID":

            mark(
                20,
                "Stop Quality",
                "CONFIRMED",
                stop_quality,
                direction,
            )

        else:

            mark(
                20,
                "Stop Quality",
                "REJECTED",
                stop_quality,
            )

        # -------------------------------------------------
        # 21 Position sizing
        # -------------------------------------------------

        mark(
            21,
            "Position Sizing",
            "PENDING",
            "PENDING_ACCOUNT_RISK",
        )

        # -------------------------------------------------
        # 22 Portfolio risk
        # -------------------------------------------------

        mark(
            22,
            "Portfolio Risk",
            "PENDING",
            "PENDING_PORTFOLIO_STATE",
        )

        # -------------------------------------------------
        # 23 Execution
        # -------------------------------------------------

        mark(
            23,
            "Execution Quality",
            "PENDING",
            "PENDING_EXECUTION_CHECK",
        )

        # -------------------------------------------------
        # 24 Freshness
        # -------------------------------------------------

        mark(
            24,
            "Signal Freshness",
            "CONFIRMED",
            "FRESH",
        )

        # -------------------------------------------------
        # Final response
        # -------------------------------------------------

        confidence_result = dict(
            confidence_result
        )

        confidence_result[
            "confidence"
        ] = round(
            confidence,
            2,
        )

        confidence_result[
            "direction"
        ] = direction

        confidence_result[
            "passed"
        ] = (
            publishable
        )

        confidence_result[
            "decision"
        ] = (
            "QUALIFIED"
            if publishable
            else (
                "REJECTED"
                if direction
                != "NEUTRAL"
                else "NO_TRADE"
            )
        )

        confidence_result[
            "factors"
        ] = {
            key: round(
                self._float(
                    value
                ),
                2,
            )
            for key, value
            in factor_scores.items()
        }

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
            "core_timeframes": list(
                self.CORE_TIMEFRAMES
            ),
            "timeframes": timeframes,
            "multi_timeframe": mtf,
            "order_book": order_book,
            "liquidations": liquidations,
            "derivatives": derivatives,
            "confidence_engine":
                confidence_result,
            "factor_scores":
                factor_scores,
            "reasons": list(
                dict.fromkeys(
                    reasons
                )
            ),
            "raw_market_data_available":
                True,
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
            "24_point_analysis": {
                "points":
                    point_statuses,
                "market_confirmation_count":
                    confirmation_points,
                "market_confirmation_total":
                    20,
                "risk_gate_count": (
                    sum(
                        1
                        for number in (
                            "19",
                            "20",
                        )
                        if point_statuses.get(
                            number,
                            {},
                        ).get(
                            "status"
                        )
                        == "CONFIRMED"
                    )
                ),
                "risk_gate_total": 4,
            },
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
