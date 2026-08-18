from __future__ import annotations

from typing import Any


class IndicatorEngine:
    """
    Deterministic technical-indicator calculations for RR Trader.

    Input:
        Binance kline arrays.

    Output:
        Plain Python dictionaries suitable for the
        analysis engine.

    This layer does NOT decide LONG/SHORT by itself.
    """

    # =====================================================
    # SAFE NUMBER
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
    # CANDLE PARSER
    # =====================================================

    @classmethod
    def parse_candles(
        cls,
        candles: list[Any],
    ) -> dict[str, list[float]]:

        opens: list[float] = []
        highs: list[float] = []
        lows: list[float] = []
        closes: list[float] = []
        volumes: list[float] = []

        for candle in candles:

            if not isinstance(
                candle,
                (list, tuple),
            ):
                continue

            if len(candle) < 6:
                continue

            opens.append(
                cls._float(candle[1])
            )

            highs.append(
                cls._float(candle[2])
            )

            lows.append(
                cls._float(candle[3])
            )

            closes.append(
                cls._float(candle[4])
            )

            volumes.append(
                cls._float(candle[5])
            )

        return {
            "opens": opens,
            "highs": highs,
            "lows": lows,
            "closes": closes,
            "volumes": volumes,
        }

    # =====================================================
    # EMA
    # =====================================================

    @classmethod
    def ema(
        cls,
        values: list[float],
        period: int,
    ) -> float:

        if not values:
            return 0.0

        if period <= 0:
            return 0.0

        if len(values) < period:

            # Fallback to simple average when
            # there are not enough candles.
            return round(
                sum(values)
                / len(values),
                8,
            )

        multiplier = (
            2.0
            / (period + 1.0)
        )

        ema_value = (
            sum(
                values[
                    :period
                ]
            )
            / period
        )

        for value in values[period:]:

            ema_value = (
                (
                    value
                    - ema_value
                )
                * multiplier
            ) + ema_value

        return round(
            ema_value,
            8,
        )

    # =====================================================
    # RSI
    # =====================================================

    @classmethod
    def rsi(
        cls,
        closes: list[float],
        period: int = 14,
    ) -> float:

        if len(closes) <= period:
            return 50.0

        gains: list[float] = []
        losses: list[float] = []

        for index in range(
            1,
            len(closes),
        ):

            change = (
                closes[index]
                - closes[index - 1]
            )

            gains.append(
                max(
                    0.0,
                    change,
                )
            )

            losses.append(
                max(
                    0.0,
                    -change,
                )
            )

        avg_gain = (
            sum(
                gains[:period]
            )
            / period
        )

        avg_loss = (
            sum(
                losses[:period]
            )
            / period
        )

        for index in range(
            period,
            len(gains),
        ):

            avg_gain = (
                (
                    avg_gain
                    * (period - 1)
                )
                + gains[index]
            ) / period

            avg_loss = (
                (
                    avg_loss
                    * (period - 1)
                )
                + losses[index]
            ) / period

        if avg_loss == 0:
            return 100.0

        rs = (
            avg_gain
            / avg_loss
        )

        value = (
            100.0
            - (
                100.0
                / (1.0 + rs)
            )
        )

        return round(
            max(
                0.0,
                min(
                    100.0,
                    value,
                ),
            ),
            4,
        )

    # =====================================================
    # ATR
    # =====================================================

    @classmethod
    def atr(
        cls,
        highs: list[float],
        lows: list[float],
        closes: list[float],
        period: int = 14,
    ) -> float:

        if (
            len(highs) < 2
            or len(lows) < 2
            or len(closes) < 2
        ):
            return 0.0

        true_ranges: list[float] = []

        for index in range(
            1,
            len(closes),
        ):

            high = highs[index]
            low = lows[index]
            previous_close = closes[
                index - 1
            ]

            tr = max(
                high - low,
                abs(
                    high
                    - previous_close
                ),
                abs(
                    low
                    - previous_close
                ),
            )

            true_ranges.append(
                tr
            )

        if not true_ranges:
            return 0.0

        if len(
            true_ranges
        ) < period:

            return round(
                sum(
                    true_ranges
                )
                / len(true_ranges),
                8,
            )

        return round(
            sum(
                true_ranges[
                    -period:
                ]
            )
            / period,
            8,
        )

    # =====================================================
    # VWAP
    # =====================================================

    @classmethod
    def vwap(
        cls,
        highs: list[float],
        lows: list[float],
        closes: list[float],
        volumes: list[float],
    ) -> float:

        length = min(
            len(highs),
            len(lows),
            len(closes),
            len(volumes),
        )

        if length <= 0:
            return 0.0

        cumulative_price_volume = 0.0
        cumulative_volume = 0.0

        for index in range(
            length
        ):

            typical_price = (
                highs[index]
                + lows[index]
                + closes[index]
            ) / 3.0

            volume = max(
                0.0,
                volumes[index],
            )

            cumulative_price_volume += (
                typical_price
                * volume
            )

            cumulative_volume += volume

        if cumulative_volume <= 0:
            return 0.0

        return round(
            cumulative_price_volume
            / cumulative_volume,
            8,
        )

    # =====================================================
    # VOLUME AVERAGE
    # =====================================================

    @classmethod
    def average_volume(
        cls,
        volumes: list[float],
        period: int = 20,
    ) -> float:

        if not volumes:
            return 0.0

        sample = volumes[
            -max(
                1,
                period,
            ):
        ]

        return round(
            sum(sample)
            / len(sample),
            8,
        )

    # =====================================================
    # MOMENTUM
    # =====================================================

    @classmethod
    def momentum(
        cls,
        closes: list[float],
        lookback: int = 5,
    ) -> float:

        if len(closes) <= lookback:
            return 0.0

        previous = closes[
            -lookback - 1
        ]

        current = closes[-1]

        if previous == 0:
            return 0.0

        return round(
            (
                (
                    current
                    - previous
                )
                / previous
            )
            * 100.0,
            6,
        )

    # =====================================================
    # CANDLE STRUCTURE
    # =====================================================

    @classmethod
    def candle_structure(
        cls,
        opens: list[float],
        highs: list[float],
        lows: list[float],
        closes: list[float],
    ) -> dict[str, float | str]:

        if not (
            opens
            and highs
            and lows
            and closes
        ):

            return {
                "direction": "NEUTRAL",
                "body": 0.0,
                "range": 0.0,
                "body_ratio": 0.0,
                "upper_wick": 0.0,
                "lower_wick": 0.0,
            }

        open_price = opens[-1]
        high_price = highs[-1]
        low_price = lows[-1]
        close_price = closes[-1]

        candle_range = max(
            0.0,
            high_price
            - low_price,
        )

        body = abs(
            close_price
            - open_price
        )

        upper_wick = max(
            0.0,
            high_price
            - max(
                open_price,
                close_price,
            ),
        )

        lower_wick = max(
            0.0,
            min(
                open_price,
                close_price,
            )
            - low_price,
        )

        body_ratio = (
            body
            / candle_range
            if candle_range > 0
            else 0.0
        )

        direction = (
            "LONG"
            if close_price > open_price
            else "SHORT"
            if close_price < open_price
            else "NEUTRAL"
        )

        return {
            "direction": direction,
            "body": round(
                body,
                8,
            ),
            "range": round(
                candle_range,
                8,
            ),
            "body_ratio": round(
                body_ratio,
                6,
            ),
            "upper_wick": round(
                upper_wick,
                8,
            ),
            "lower_wick": round(
                lower_wick,
                8,
            ),
        }

    # =====================================================
    # RECENT RANGE
    # =====================================================

    @classmethod
    def recent_range(
        cls,
        highs: list[float],
        lows: list[float],
        lookback: int = 20,
    ) -> dict[str, float]:

        if not highs or not lows:
            return {
                "high": 0.0,
                "low": 0.0,
                "position_percent": 50.0,
            }

        safe_lookback = max(
            1,
            lookback,
        )

        recent_highs = highs[
            -safe_lookback:
        ]

        recent_lows = lows[
            -safe_lookback:
        ]

        range_high = max(
            recent_highs
        )

        range_low = min(
            recent_lows
        )

        current = (
            cls._float(
                highs[-1]
            )
            + cls._float(
                lows[-1]
            )
        ) / 2.0

        price_range = (
            range_high
            - range_low
        )

        if price_range <= 0:

            position_percent = 50.0

        else:

            position_percent = (
                (
                    current
                    - range_low
                )
                / price_range
                * 100.0
            )

        return {
            "high": round(
                range_high,
                8,
            ),
            "low": round(
                range_low,
                8,
            ),
            "position_percent": round(
                max(
                    0.0,
                    min(
                        100.0,
                        position_percent,
                    ),
                ),
                4,
            ),
        }

    # =====================================================
    # BREAKOUT
    # =====================================================

    @classmethod
    def breakout(
        cls,
        highs: list[float],
        lows: list[float],
        closes: list[float],
        lookback: int = 20,
    ) -> dict[str, Any]:

        if len(closes) <= lookback:
            return {
                "direction": "NONE",
                "breakout": False,
                "level": 0.0,
            }

        previous_high = max(
            highs[
                -lookback - 1:
                -1
            ]
        )

        previous_low = min(
            lows[
                -lookback - 1:
                -1
            ]
        )

        current_close = closes[-1]

        if current_close > previous_high:

            return {
                "direction": "LONG",
                "breakout": True,
                "level": previous_high,
            }

        if current_close < previous_low:

            return {
                "direction": "SHORT",
                "breakout": True,
                "level": previous_low,
            }

        return {
            "direction": "NONE",
            "breakout": False,
            "level": 0.0,
        }

    # =====================================================
    # COMPLETE TIMEFRAME INDICATORS
    # =====================================================

    @classmethod
    def calculate(
        cls,
        candles: list[Any],
    ) -> dict[str, Any]:

        parsed = cls.parse_candles(
            candles
        )

        opens = parsed["opens"]
        highs = parsed["highs"]
        lows = parsed["lows"]
        closes = parsed["closes"]
        volumes = parsed["volumes"]

        if not closes:

            return {
                "success": False,
                "candle_count": 0,
                "error": "No valid candles.",
            }

        current_price = closes[-1]

        ema20 = cls.ema(
            closes,
            20,
        )

        ema50 = cls.ema(
            closes,
            50,
        )

        rsi = cls.rsi(
            closes,
            14,
        )

        atr = cls.atr(
            highs,
            lows,
            closes,
            14,
        )

        vwap = cls.vwap(
            highs,
            lows,
            closes,
            volumes,
        )

        avg_volume = cls.average_volume(
            volumes,
            20,
        )

        momentum = cls.momentum(
            closes,
            5,
        )

        candle = cls.candle_structure(
            opens,
            highs,
            lows,
            closes,
        )

        recent_range = (
            cls.recent_range(
                highs,
                lows,
                20,
            )
        )

        breakout = cls.breakout(
            highs,
            lows,
            closes,
            20,
        )

        atr_percent = (
            atr
            / current_price
            * 100.0
            if current_price > 0
            else 0.0
        )

        volume_ratio = (
            volumes[-1]
            / avg_volume
            if avg_volume > 0
            else 0.0
        )

        return {
            "success": True,
            "candle_count": len(
                closes
            ),
            "price": current_price,
            "ema20": ema20,
            "ema50": ema50,
            "rsi": rsi,
            "atr": atr,
            "atr_percent": round(
                atr_percent,
                6,
            ),
            "vwap": vwap,
            "momentum": momentum,
            "average_volume": avg_volume,
            "current_volume": volumes[-1],
            "volume_ratio": round(
                volume_ratio,
                6,
            ),
            "candle_structure": candle,
            "recent_range": recent_range,
            "breakout": breakout,
        }


indicator_engine = IndicatorEngine()


__all__ = [
    "IndicatorEngine",
    "indicator_engine",
]
