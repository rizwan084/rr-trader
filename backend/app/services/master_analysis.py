from __future__ import annotations

import asyncio
from typing import Any

from app.services.indicators import indicator_engine
from app.services.market_data import market_data_service
from app.services.market_structure import market_structure_engine
from app.services.mtf_engine import mtf_engine
from app.services.confidence_engine import confidence_engine


class MasterAnalysisEngine:
    """
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

    It produces analytical output only.
    Trade execution remains separate.
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

    # =====================================================
    # ORDER BOOK ANALYSIS
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
                isinstance(item, (list, tuple))
                and len(item) >= 2
            ):
                bid_volume += self._float(
                    item[1]
                )

        for item in asks[:50]:

            if (
                isinstance(item, (list, tuple))
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
            bid_volume
            - ask_volume
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
    # LIQUIDATION ANALYSIS
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

            # Binance force-order semantics:
            # SELL liquidation = long position liquidation
            # BUY liquidation = short position liquidation

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
    # DERIVATIVES ANALYSIS
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

        # -------------------------------------------------
        # Funding
        # -------------------------------------------------

        funding = derivatives.get(
            "funding_rate",
            [],
        )

        if isinstance(
            funding,
            list
        ) and funding:

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

                # Positive funding = long crowding.
                # Negative funding = short crowding.
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

        # -------------------------------------------------
        # Global long/short ratio
        # -------------------------------------------------

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

        # -------------------------------------------------
        # Top trader account ratio
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

        strength = (
            abs(
                long_direction
                - short_direction
            )
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
    # TIMEFRAME POINTS
    # =====================================================

    def timeframe_points(
        self,
        timeframe_data: dict[str, Any],
    ) -> dict[str, Any]:

        points: dict[
            str,
            dict[str, Any],
        ] = {}

        for timeframe in (
            self.CORE_TIMEFRAMES
        ):

            item = timeframe_data.get(
                timeframe,
                {},
            )

            if not isinstance(
                item,
                dict,
            ):

                points[timeframe] = {
                    "status": "UNAVAILABLE",
                    "direction": "NEUTRAL",
                    "score": 0.0,
                }

                continue

            direction = self._direction(
                item.get(
                    "direction"
                )
            )

            confidence = self._float(
                item.get(
                    "confidence",
                    0,
                )
            )

            points[timeframe] = {
                "status": (
                    "AVAILABLE"
                    if item.get(
                        "success",
                        False,
                    )
                    else "UNAVAILABLE"
                ),
                "direction": direction,
                "score": confidence,
            }

        return points

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
        # Collect raw data
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
        # Technical timeframe analysis
        # -------------------------------------------------

        async def timeframe_task(
            timeframe: str,
        ) -> tuple[
            str,
            dict[str, Any],
        ]:

            timeframe_data = raw[
                "timeframes"
            ].get(
                timeframe,
                {},
            )

            candles = (
                timeframe_data.get(
                    "candles",
                    []
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

                return timeframe, {
                    "success": False,
                    "direction": "NEUTRAL",
                    "confidence": 0.0,
                    "error":
                        "Invalid candle data.",
                }

            indicators = (
                indicator_engine.calculate(
                    candles
                )
            )

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

            if (
                price > ema20 > ema50
            ):

                direction_score[
                    "LONG"
                ] += 20

                reasons.append(
                    "EMA structure bullish."
                )

            elif (
                price < ema20 < ema50
            ):

                direction_score[
                    "SHORT"
                ] += 20

                reasons.append(
                    "EMA structure bearish."
                )

            momentum = self._float(
                indicators.get(
                    "momentum"
                )
            )

            if momentum > 0:

                direction_score[
                    "LONG"
                ] += min(
                    15,
                    abs(momentum) * 3,
                )

                reasons.append(
                    "Momentum positive."
                )

            elif momentum < 0:

                direction_score[
                    "SHORT"
                ] += min(
                    15,
                    abs(momentum) * 3,
                )

                reasons.append(
                    "Momentum negative."
                )

            if (
                structure.get(
                    "direction"
                )
                == "LONG"
            ):

                direction_score[
                    "LONG"
                ] += 25

                reasons.append(
                    "Structure bullish."
                )

            elif (
                structure.get(
                    "direction"
                )
                == "SHORT"
            ):

                direction_score[
                    "SHORT"
                ] += 25

                reasons.append(
                    "Structure bearish."
                )

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

            if (
                breakout_direction
                in {
                    "LONG",
                    "SHORT",
                }
            ):

                direction_score[
                    breakout_direction
                ] += 10

                reasons.append(
                    f"{breakout_direction} breakout detected."
                )

            vwap = self._float(
                indicators.get(
                    "vwap"
                )
            )

            if (
                price > 0
                and vwap > 0
            ):

                if price > vwap:

                    direction_score[
                        "LONG"
                    ] += 5

                elif price < vwap:

                    direction_score[
                        "SHORT"
                    ] += 5

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
                direction_score[
                    "LONG"
                ],
                direction_score[
                    "SHORT"
                ],
            )

            return timeframe, {
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
            }

        timeframe_results = await asyncio.gather(
            *[
                timeframe_task(
                    timeframe
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

        liquidations = (
            self.analyze_liquidations(
                raw.get(
                    "derivatives",
                    {}
                ).get(
                    "liquidation_orders",
                    [],
                )
            )
        )

        # -------------------------------------------------
        # Final direction
        # -------------------------------------------------

        direction = self._direction(
            mtf.get(
                "direction"
            )
        )

        # 4H is the regime anchor.
        four_hour = timeframes.get(
            "4h",
            {},
        )

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
            != direction
        ):

            direction = "NEUTRAL"

        # -------------------------------------------------
        # Factor scores
        # -------------------------------------------------

        factor_scores = {
            "trend":
                self._float(
                    timeframes.get(
                        "1h",
                        {},
                    ).get(
                        "confidence",
                        0,
                    )
                ),
            "structure":
                self._float(
                    timeframes.get(
                        "1h",
                        {},
                    ).get(
                        "structure",
                        {},
                    ).get(
                        "score",
                        0,
                    )
                ),
            "momentum":
                self._float(
                    timeframes.get(
                        "15m",
                        {},
                    ).get(
                        "confidence",
                        0,
                    )
                ),
            "volume": 0.0,
            "support_resistance": 0.0,
            "multi_timeframe":
                self._float(
                    mtf.get(
                        "weighted_confidence",
                        0,
                    )
                ),
            "liquidity":
                liquidations.get(
                    "score",
                    0,
                ),
            "derivatives":
                derivatives.get(
                    "score",
                    0,
                ),
            "risk_reward": 0.0,
            "market_regime":
                self._float(
                    timeframes.get(
                        "4h",
                        {},
                    ).get(
                        "confidence",
                        0,
                    )
                ),
        }

        # -------------------------------------------------
        # Confidence
        # -------------------------------------------------

        confidence_result = (
            confidence_engine.evaluate(
                factor_scores
            )
        )

        confidence = float(
            confidence_result.get(
                "confidence",
                0,
            )
        )

        # Strict MTF veto
        if not mtf.get(
            "publishable_mtf",
            False,
        ):

            confidence = min(
                confidence,
                84.99,
            )

        if direction == "NEUTRAL":

            confidence = 0.0

        publishable = (
            direction
            in {
                "LONG",
                "SHORT",
            }
            and confidence >= 85.0
            and mtf.get(
                "publishable_mtf",
                False,
            )
        )

        # -------------------------------------------------
        # Reasons
        # -------------------------------------------------

        reasons: list[str] = []

        for timeframe in (
            self.CORE_TIMEFRAMES
        ):

            reasons.extend(
                timeframes.get(
                    timeframe,
                    {},
                ).get(
                    "reasons",
                    [],
                )
            )

        reasons.extend(
            derivatives.get(
                "reasons",
                [],
            )
        )

        if order_book.get(
            "direction"
        ) == direction:

            reasons.append(
                "Order book supports the direction."
            )

        if liquidations.get(
            "direction"
        ) == direction:

            reasons.append(
                "Liquidation flow supports the direction."
            )

        if mtf.get(
            "publishable_mtf"
        ):

            reasons.append(
                "15m, 1H and 4H are aligned."
            )

        else:

            reasons.append(
                "Strict MTF alignment has not been confirmed."
            )

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
            "confidence_engine": confidence_result,
            "factor_scores": factor_scores,
            "reasons": list(
                dict.fromkeys(
                    reasons
                )
            ),
            "raw_market_data_available": True,
        }


master_analysis_engine = (
    MasterAnalysisEngine()
)


__all__ = [
    "MasterAnalysisEngine",
    "master_analysis_engine",
]
