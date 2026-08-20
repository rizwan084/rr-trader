from __future__ import annotations

from typing import Any


class IndicatorEngine:
    """
    RR Trader deterministic technical-indicator engine.

    Responsibilities:
    - Parse Binance klines.
    - Calculate trend indicators.
    - Calculate momentum.
    - Calculate volatility.
    - Calculate volume confirmation.
    - Analyse candle structure.
    - Detect breakout conditions.
    - Produce technical evidence for downstream engines.

    IMPORTANT:
    This engine does NOT make the final LONG/SHORT decision.

    Final trade decisions are handled by downstream analysis,
    confidence and signal engines.
    """

    # =====================================================
    # CONFIGURATION
    # =====================================================

    EMA_FAST = 20
    EMA_MEDIUM = 50
    EMA_SLOW = 200

    RSI_PERIOD = 14

    ATR_PERIOD = 14

    VOLUME_PERIOD = 20

    MOMENTUM_LOOKBACK = 5

    RANGE_LOOKBACK = 20

    BREAKOUT_LOOKBACK = 20

    # Minimum volume multiplier required for a strong
    # volume confirmation.
    STRONG_VOLUME_RATIO = 1.50

    # Normal confirmation threshold.
    CONFIRM_VOLUME_RATIO = 1.20

    # RSI zones.
    RSI_BULLISH = 55.0
    RSI_BEARISH = 45.0

    RSI_OVERBOUGHT = 70.0
    RSI_OVERSOLD = 30.0

    # Candle rejection thresholds.
    MIN_WICK_RATIO = 0.35

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
    # SAFE LIST
    # =====================================================

    @classmethod
    def _clean_values(
        cls,
        values: list[Any],
    ) -> list[float]:

        return [
            cls._float(value)
            for value in values
        ]

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

            open_price = cls._float(
                candle[1]
            )

            high_price = cls._float(
                candle[2]
            )

            low_price = cls._float(
                candle[3]
            )

            close_price = cls._float(
                candle[4]
            )

            volume = cls._float(
                candle[5]
            )

            if (
                high_price <= 0
                or low_price <= 0
                or close_price <= 0
            ):
                continue

            if high_price < low_price:
                continue

            opens.append(
                open_price
            )

            highs.append(
                high_price
            )

            lows.append(
                low_price
            )

            closes.append(
                close_price
            )

            volumes.append(
                max(
                    0.0,
                    volume,
                )
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

        period = int(period)

        if period <= 0:
            return 0.0

        if len(values) < period:

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
                values[:period]
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
    # EMA SERIES
    # =====================================================

    @classmethod
    def ema_series(
        cls,
        values: list[float],
        period: int,
    ) -> list[float]:

        if not values:
            return []

        period = max(
            1,
            int(period),
        )

        if len(values) < period:

            average = (
                sum(values)
                / len(values)
            )

            return [
                round(
                    average,
                    8,
                )
                for _ in values
            ]

        multiplier = (
            2.0
            / (period + 1.0)
        )

        first_ema = (
            sum(
                values[:period]
            )
            / period
        )

        series = [
            first_ema
        ]

        ema_value = first_ema

        for value in values[period:]:

            ema_value = (
                (
                    value
                    - ema_value
                )
                * multiplier
            ) + ema_value

            series.append(
                ema_value
            )

        prefix_count = (
            len(values)
            - len(series)
        )

        prefix = [
            first_ema
            for _ in range(
                prefix_count
            )
        ]

        return [
            round(
                value,
                8,
            )
            for value
            in (
                prefix
                + series
            )
        ]

    # =====================================================
    # EMA SLOPE
    # =====================================================

    @classmethod
    def ema_slope(
        cls,
        values: list[float],
        period: int,
        lookback: int = 5,
    ) -> float:

        series = cls.ema_series(
            values,
            period,
        )

        if len(series) <= lookback:
            return 0.0

        previous = series[
            -lookback - 1
        ]

        current = series[-1]

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
    # EMA ALIGNMENT
    # =====================================================

    @classmethod
    def ema_alignment(
        cls,
        price: float,
        ema20: float,
        ema50: float,
        ema200: float,
    ) -> dict[str, Any]:

        if (
            price <= 0
            or ema20 <= 0
            or ema50 <= 0
        ):

            return {
                "state": "UNKNOWN",
                "bullish": False,
                "bearish": False,
                "score": 0,
            }

        bullish = (
            price > ema20
            and ema20 > ema50
        )

        bearish = (
            price < ema20
            and ema20 < ema50
        )

        strong_bullish = (
            bullish
            and (
                ema50 > ema200
                if ema200 > 0
                else True
            )
        )

        strong_bearish = (
            bearish
            and (
                ema50 < ema200
                if ema200 > 0
                else True
            )
        )

        if strong_bullish:

            state = "STRONG_BULLISH"
            score = 3

        elif strong_bearish:

            state = "STRONG_BEARISH"
            score = -3

        elif bullish:

            state = "BULLISH"
            score = 2

        elif bearish:

            state = "BEARISH"
            score = -2

        else:

            state = "MIXED"
            score = 0

        return {
            "state": state,
            "bullish": bullish,
            "bearish": bearish,
            "strong_bullish": strong_bullish,
            "strong_bearish": strong_bearish,
            "score": score,
        }

    # =====================================================
    # RSI
    # =====================================================

    @classmethod
    def rsi(
        cls,
        closes: list[float],
        period: int = RSI_PERIOD,
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
    # RSI SERIES
    # =====================================================

    @classmethod
    def rsi_series(
        cls,
        closes: list[float],
        period: int = RSI_PERIOD,
    ) -> list[float]:

        if len(closes) <= period:
            return []

        output: list[float] = []

        for end in range(
            period + 1,
            len(closes) + 1,
        ):

            value = cls.rsi(
                closes[:end],
                period,
            )

            output.append(
                value
            )

        return output

    # =====================================================
    # RSI DIRECTION
    # =====================================================

    @classmethod
    def rsi_direction(
        cls,
        closes: list[float],
        period: int = RSI_PERIOD,
    ) -> dict[str, Any]:

        series = cls.rsi_series(
            closes,
            period,
        )

        if len(series) < 2:

            value = cls.rsi(
                closes,
                period,
            )

            return {
                "current": value,
                "previous": value,
                "change": 0.0,
                "direction": "NEUTRAL",
                "rising": False,
                "falling": False,
            }

        current = series[-1]
        previous = series[-2]

        change = (
            current
            - previous
        )

        if change > 0.5:

            direction = "RISING"

        elif change < -0.5:

            direction = "FALLING"

        else:

            direction = "FLAT"

        return {
            "current": round(
                current,
                4,
            ),
            "previous": round(
                previous,
                4,
            ),
            "change": round(
                change,
                4,
            ),
            "direction": direction,
            "rising": change > 0,
            "falling": change < 0,
        }

    # =====================================================
    # ATR
    # =====================================================

    @classmethod
    def atr(
        cls,
        highs: list[float],
        lows: list[float],
        closes: list[float],
        period: int = ATR_PERIOD,
    ) -> float:

        if (
            len(highs) < 2
            or len(lows) < 2
            or len(closes) < 2
        ):
            return 0.0

        true_ranges: list[float] = []

        length = min(
            len(highs),
            len(lows),
            len(closes),
        )

        for index in range(
            1,
            length,
        ):

            high = cls._float(
                highs[index]
            )

            low = cls._float(
                lows[index]
            )

            previous_close = cls._float(
                closes[index - 1]
            )

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
                sum(true_ranges)
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
    # ATR PERCENT
    # =====================================================

    @classmethod
    def atr_percent(
        cls,
        atr: float,
        price: float,
    ) -> float:

        if (
            atr <= 0
            or price <= 0
        ):
            return 0.0

        return round(
            (
                atr
                / price
            )
            * 100.0,
            6,
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

            cumulative_volume += (
                volume
            )

        if cumulative_volume <= 0:
            return 0.0

        return round(
            cumulative_price_volume
            / cumulative_volume,
            8,
        )

    # =====================================================
    # PRICE DISTANCE
    # =====================================================

    @classmethod
    def price_distance(
        cls,
        price: float,
        level: float,
    ) -> float:

        if (
            price <= 0
            or level <= 0
        ):
            return 0.0

        return round(
            (
                (
                    price
                    - level
                )
                / level
            )
            * 100.0,
            6,
        )

    # =====================================================
    # VOLUME AVERAGE
    # =====================================================

    @classmethod
    def average_volume(
        cls,
        volumes: list[float],
        period: int = VOLUME_PERIOD,
    ) -> float:

        if not volumes:
            return 0.0

        period = max(
            1,
            int(period),
        )

        sample = volumes[
            -period:
        ]

        if not sample:
            return 0.0

        return round(
            sum(sample)
            / len(sample),
            8,
        )

    # =====================================================
    # VOLUME ANALYSIS
    # =====================================================

    @classmethod
    def volume_analysis(
        cls,
        volumes: list[float],
        period: int = VOLUME_PERIOD,
    ) -> dict[str, Any]:

        if not volumes:

            return {
                "current": 0.0,
                "average": 0.0,
                "ratio": 0.0,
                "state": "UNKNOWN",
                "confirmation": False,
                "strong_confirmation": False,
            }

        current = cls._float(
            volumes[-1]
        )

        average = cls.average_volume(
            volumes,
            period,
        )

        if average <= 0:

            ratio = 0.0

        else:

            ratio = (
                current
                / average
            )

        if ratio >= (
            cls.STRONG_VOLUME_RATIO
        ):

            state = "STRONG"
            confirmation = True
            strong_confirmation = True

        elif ratio >= (
            cls.CONFIRM_VOLUME_RATIO
        ):

            state = "CONFIRMED"
            confirmation = True
            strong_confirmation = False

        elif ratio >= 0.80:

            state = "NORMAL"
            confirmation = False
            strong_confirmation = False

        else:

            state = "LOW"
            confirmation = False
            strong_confirmation = False

        return {
            "current": round(
                current,
                8,
            ),
            "average": round(
                average,
                8,
            ),
            "ratio": round(
                ratio,
                6,
            ),
            "state": state,
            "confirmation": confirmation,
            "strong_confirmation": (
                strong_confirmation
            ),
        }

    # =====================================================
    # MOMENTUM
    # =====================================================

    @classmethod
    def momentum(
        cls,
        closes: list[float],
        lookback: int = MOMENTUM_LOOKBACK,
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
    # MOMENTUM ACCELERATION
    # =====================================================

    @classmethod
    def momentum_acceleration(
        cls,
        closes: list[float],
        lookback: int = MOMENTUM_LOOKBACK,
    ) -> dict[str, Any]:

        if len(closes) <= (
            lookback * 2
        ):

            return {
                "current": 0.0,
                "previous": 0.0,
                "acceleration": 0.0,
                "state": "UNKNOWN",
            }

        current = cls.momentum(
            closes,
            lookback,
        )

        previous_closes = closes[
            : -lookback
        ]

        previous = cls.momentum(
            previous_closes,
            lookback,
        )

        acceleration = (
            current
            - previous
        )

        if acceleration > 0.20:

            state = "ACCELERATING_UP"

        elif acceleration < -0.20:

            state = "ACCELERATING_DOWN"

        else:

            state = "STABLE"

        return {
            "current": round(
                current,
                6,
            ),
            "previous": round(
                previous,
                6,
            ),
            "acceleration": round(
                acceleration,
                6,
            ),
            "state": state,
        }

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
    ) -> dict[str, Any]:

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
                "upper_wick_ratio": 0.0,
                "lower_wick_ratio": 0.0,
                "bullish_rejection": False,
                "bearish_rejection": False,
            }

        open_price = cls._float(
            opens[-1]
        )

        high_price = cls._float(
            highs[-1]
        )

        low_price = cls._float(
            lows[-1]
        )

        close_price = cls._float(
            closes[-1]
        )

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

        if candle_range > 0:

            body_ratio = (
                body
                / candle_range
            )

            upper_wick_ratio = (
                upper_wick
                / candle_range
            )

            lower_wick_ratio = (
                lower_wick
                / candle_range
            )

        else:

            body_ratio = 0.0
            upper_wick_ratio = 0.0
            lower_wick_ratio = 0.0

        if close_price > open_price:

            direction = "LONG"

        elif close_price < open_price:

            direction = "SHORT"

        else:

            direction = "NEUTRAL"

        bullish_rejection = (
            direction == "LONG"
            and lower_wick_ratio
            >= cls.MIN_WICK_RATIO
            and body_ratio
            >= 0.20
        )

        bearish_rejection = (
            direction == "SHORT"
            and upper_wick_ratio
            >= cls.MIN_WICK_RATIO
            and body_ratio
            >= 0.20
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

            "upper_wick_ratio": round(
                upper_wick_ratio,
                6,
            ),

            "lower_wick_ratio": round(
                lower_wick_ratio,
                6,
            ),

            "bullish_rejection": (
                bullish_rejection
            ),

            "bearish_rejection": (
                bearish_rejection
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
        closes: list[float],
        lookback: int = RANGE_LOOKBACK,
    ) -> dict[str, float]:

        if not highs or not lows:

            return {
                "high": 0.0,
                "low": 0.0,
                "position_percent": 50.0,
                "range_percent": 0.0,
            }

        safe_lookback = max(
            1,
            int(lookback),
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
                closes[-1]
            )
            if closes
            else (
                cls._float(
                    highs[-1]
                )
                + cls._float(
                    lows[-1]
                )
            )
            / 2.0
        )

        price_range = (
            range_high
            - range_low
        )

        if price_range <= 0:

            position_percent = 50.0
            range_percent = 0.0

        else:

            position_percent = (
                (
                    current
                    - range_low
                )
                / price_range
                * 100.0
            )

            range_percent = (
                price_range
                / current
                * 100.0
                if current > 0
                else 0.0
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
            "range_percent": round(
                range_percent,
                6,
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
        lookback: int = BREAKOUT_LOOKBACK,
    ) -> dict[str, Any]:

        if len(closes) <= lookback:

            return {
                "direction": "NONE",
                "breakout": False,
                "level": 0.0,
                "distance_percent": 0.0,
                "strength": "NONE",
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

            distance = (
                (
                    current_close
                    - previous_high
                )
                / previous_high
                * 100.0
                if previous_high > 0
                else 0.0
            )

            if distance >= 1.0:
                strength = "STRONG"

            elif distance >= 0.30:
                strength = "CONFIRMED"

            else:
                strength = "WEAK"

            return {
                "direction": "LONG",
                "breakout": True,
                "level": round(
                    previous_high,
                    8,
                ),
                "distance_percent": round(
                    distance,
                    6,
                ),
                "strength": strength,
            }

        if current_close < previous_low:

            distance = (
                (
                    previous_low
                    - current_close
                )
                / previous_low
                * 100.0
                if previous_low > 0
                else 0.0
            )

            if distance >= 1.0:
                strength = "STRONG"

            elif distance >= 0.30:
                strength = "CONFIRMED"

            else:
                strength = "WEAK"

            return {
                "direction": "SHORT",
                "breakout": True,
                "level": round(
                    previous_low,
                    8,
                ),
                "distance_percent": round(
                    distance,
                    6,
                ),
                "strength": strength,
            }

        return {
            "direction": "NONE",
            "breakout": False,
            "level": 0.0,
            "distance_percent": 0.0,
            "strength": "NONE",
        }

    # =====================================================
    # TREND STATE
    # =====================================================

    @classmethod
    def trend_state(
        cls,
        price: float,
        ema20: float,
        ema50: float,
        ema200: float,
        ema20_slope: float,
        ema50_slope: float,
    ) -> dict[str, Any]:

        bullish_points = 0
        bearish_points = 0

        if price > ema20:
            bullish_points += 1

        elif price < ema20:
            bearish_points += 1

        if ema20 > ema50:
            bullish_points += 1

        elif ema20 < ema50:
            bearish_points += 1

        if ema200 > 0:

            if ema50 > ema200:
                bullish_points += 1

            elif ema50 < ema200:
                bearish_points += 1

        if ema20_slope > 0:
            bullish_points += 1

        elif ema20_slope < 0:
            bearish_points += 1

        if ema50_slope > 0:
            bullish_points += 1

        elif ema50_slope < 0:
            bearish_points += 1

        if bullish_points >= 4:

            state = "STRONG_BULLISH"

        elif bearish_points >= 4:

            state = "STRONG_BEARISH"

        elif bullish_points > bearish_points:

            state = "BULLISH"

        elif bearish_points > bullish_points:

            state = "BEARISH"

        else:

            state = "NEUTRAL"

        return {
            "state": state,
            "bullish_points": bullish_points,
            "bearish_points": bearish_points,
        }

    # =====================================================
    # TECHNICAL CONFIRMATION
    # =====================================================

    @classmethod
    def technical_confirmation(
        cls,
        *,
        trend: dict[str, Any],
        rsi: float,
        rsi_direction: dict[str, Any],
        momentum: float,
        momentum_acceleration: dict[str, Any],
        volume: dict[str, Any],
        candle: dict[str, Any],
        breakout: dict[str, Any],
    ) -> dict[str, Any]:

        long_score = 0
        short_score = 0

        long_reasons: list[str] = []
        short_reasons: list[str] = []

        # -------------------------------------------------
        # TREND
        # -------------------------------------------------

        if trend.get(
            "state"
        ) in {
            "BULLISH",
            "STRONG_BULLISH",
        }:

            long_score += 2
            long_reasons.append(
                "bullish_trend"
            )

        if trend.get(
            "state"
        ) in {
            "BEARISH",
            "STRONG_BEARISH",
        }:

            short_score += 2
            short_reasons.append(
                "bearish_trend"
            )

        # -------------------------------------------------
        # RSI
        # -------------------------------------------------

        if (
            rsi >= cls.RSI_BULLISH
            and rsi < cls.RSI_OVERBOUGHT
        ):

            long_score += 1
            long_reasons.append(
                "bullish_rsi"
            )

        if (
            rsi <= cls.RSI_BEARISH
            and rsi > cls.RSI_OVERSOLD
        ):

            short_score += 1
            short_reasons.append(
                "bearish_rsi"
            )

        # -------------------------------------------------
        # RSI DIRECTION
        # -------------------------------------------------

        if rsi_direction.get(
            "rising",
            False,
        ):

            long_score += 1
            long_reasons.append(
                "rsi_rising"
            )

        if rsi_direction.get(
            "falling",
            False,
        ):

            short_score += 1
            short_reasons.append(
                "rsi_falling"
            )

        # -------------------------------------------------
        # MOMENTUM
        # -------------------------------------------------

        if momentum > 0:

            long_score += 1
            long_reasons.append(
                "positive_momentum"
            )

        elif momentum < 0:

            short_score += 1
            short_reasons.append(
                "negative_momentum"
            )

        # -------------------------------------------------
        # MOMENTUM ACCELERATION
        # -------------------------------------------------

        if (
            momentum_acceleration.get(
                "state"
            )
            == "ACCELERATING_UP"
        ):

            long_score += 1
            long_reasons.append(
                "momentum_acceleration_up"
            )

        elif (
            momentum_acceleration.get(
                "state"
            )
            == "ACCELERATING_DOWN"
        ):

            short_score += 1
            short_reasons.append(
                "momentum_acceleration_down"
            )

        # -------------------------------------------------
        # VOLUME
        # -------------------------------------------------

        if volume.get(
            "confirmation",
            False,
        ):

            long_score += 1
            short_score += 1

            long_reasons.append(
                "volume_confirmation"
            )

            short_reasons.append(
                "volume_confirmation"
            )

        # -------------------------------------------------
        # CANDLE
        # -------------------------------------------------

        if candle.get(
            "bullish_rejection",
            False,
        ):

            long_score += 2
            long_reasons.append(
                "bullish_rejection_candle"
            )

        if candle.get(
            "bearish_rejection",
            False,
        ):

            short_score += 2
            short_reasons.append(
                "bearish_rejection_candle"
            )

        # -------------------------------------------------
        # BREAKOUT
        # -------------------------------------------------

        if (
            breakout.get(
                "direction"
            )
            == "LONG"
        ):

            long_score += 2
            long_reasons.append(
                "bullish_breakout"
            )

        elif (
            breakout.get(
                "direction"
            )
            == "SHORT"
        ):

            short_score += 2
            short_reasons.append(
                "bearish_breakout"
            )

        max_score = 11

        long_percentage = (
            long_score
            / max_score
            * 100.0
        )

        short_percentage = (
            short_score
            / max_score
            * 100.0
        )

        if (
            long_score
            > short_score
        ):

            bias = "LONG"

        elif (
            short_score
            > long_score
        ):

            bias = "SHORT"

        else:

            bias = "NEUTRAL"

        return {
            "bias": bias,

            "long_score": long_score,

            "short_score": short_score,

            "long_percentage": round(
                long_percentage,
                2,
            ),

            "short_percentage": round(
                short_percentage,
                2,
            ),

            "long_reasons": long_reasons,

            "short_reasons": short_reasons,
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

        opens = parsed[
            "opens"
        ]

        highs = parsed[
            "highs"
        ]

        lows = parsed[
            "lows"
        ]

        closes = parsed[
            "closes"
        ]

        volumes = parsed[
            "volumes"
        ]

        if not closes:

            return {
                "success": False,
                "candle_count": 0,
                "error": (
                    "No valid candles."
                ),
            }

        current_price = cls._float(
            closes[-1]
        )

        # -------------------------------------------------
        # EMA
        # -------------------------------------------------

        ema20 = cls.ema(
            closes,
            cls.EMA_FAST,
        )

        ema50 = cls.ema(
            closes,
            cls.EMA_MEDIUM,
        )

        ema200 = cls.ema(
            closes,
            cls.EMA_SLOW,
        )

        ema20_slope = (
            cls.ema_slope(
                closes,
                cls.EMA_FAST,
            )
        )

        ema50_slope = (
            cls.ema_slope(
                closes,
                cls.EMA_MEDIUM,
            )
        )

        ema_alignment = (
            cls.ema_alignment(
                price=current_price,
                ema20=ema20,
                ema50=ema50,
                ema200=ema200,
            )
        )

        # -------------------------------------------------
        # RSI
        # -------------------------------------------------

        rsi = cls.rsi(
            closes,
            cls.RSI_PERIOD,
        )

        rsi_info = (
            cls.rsi_direction(
                closes,
                cls.RSI_PERIOD,
            )
        )

        # -------------------------------------------------
        # ATR
        # -------------------------------------------------

        atr = cls.atr(
            highs,
            lows,
            closes,
            cls.ATR_PERIOD,
        )

        atr_percent = (
            cls.atr_percent(
                atr,
                current_price,
            )
        )

        # -------------------------------------------------
        # VWAP
        # -------------------------------------------------

        vwap = cls.vwap(
            highs,
            lows,
            closes,
            volumes,
        )

        price_vs_vwap = (
            cls.price_distance(
                current_price,
                vwap,
            )
        )

        price_vs_ema20 = (
            cls.price_distance(
                current_price,
                ema20,
            )
        )

        price_vs_ema50 = (
            cls.price_distance(
                current_price,
                ema50,
            )
        )

        # -------------------------------------------------
        # VOLUME
        # -------------------------------------------------

        volume_info = (
            cls.volume_analysis(
                volumes,
                cls.VOLUME_PERIOD,
            )
        )

        # -------------------------------------------------
        # MOMENTUM
        # -------------------------------------------------

        momentum = cls.momentum(
            closes,
            cls.MOMENTUM_LOOKBACK,
        )

        momentum_info = (
            cls.momentum_acceleration(
                closes,
                cls.MOMENTUM_LOOKBACK,
            )
        )

        # -------------------------------------------------
        # CANDLE
        # -------------------------------------------------

        candle = (
            cls.candle_structure(
                opens,
                highs,
                lows,
                closes,
            )
        )

        # -------------------------------------------------
        # RANGE
        # -------------------------------------------------

        recent_range = (
            cls.recent_range(
                highs,
                lows,
                closes,
                cls.RANGE_LOOKBACK,
            )
        )

        # -------------------------------------------------
        # BREAKOUT
        # -------------------------------------------------

        breakout = cls.breakout(
            highs,
            lows,
            closes,
            cls.BREAKOUT_LOOKBACK,
        )

        # -------------------------------------------------
        # TREND
        # -------------------------------------------------

        trend = cls.trend_state(
            price=current_price,
            ema20=ema20,
            ema50=ema50,
            ema200=ema200,
            ema20_slope=ema20_slope,
            ema50_slope=ema50_slope,
        )

        # -------------------------------------------------
        # TECHNICAL CONFIRMATION
        # -------------------------------------------------

        confirmation = (
            cls.technical_confirmation(
                trend=trend,
                rsi=rsi,
                rsi_direction=rsi_info,
                momentum=momentum,
                momentum_acceleration=momentum_info,
                volume=volume_info,
                candle=candle,
                breakout=breakout,
            )
        )

        # -------------------------------------------------
        # Return
        # -------------------------------------------------

        return {
            "success": True,

            "candle_count": len(
                closes
            ),

            "price": current_price,

            # -------------------------------------------------
            # TREND
            # -------------------------------------------------

            "trend": trend,

            "ema_alignment": (
                ema_alignment
            ),

            "ema20": ema20,

            "ema50": ema50,

            "ema200": ema200,

            "ema20_slope": ema20_slope,

            "ema50_slope": ema50_slope,

            "price_vs_ema20_percent": (
                price_vs_ema20
            ),

            "price_vs_ema50_percent": (
                price_vs_ema50
            ),

            # -------------------------------------------------
            # RSI
            # -------------------------------------------------

            "rsi": rsi,

            "rsi_analysis": rsi_info,

            # -------------------------------------------------
            # VOLATILITY
            # -------------------------------------------------

            "atr": atr,

            "atr_percent": atr_percent,

            # -------------------------------------------------
            # VWAP
            # -------------------------------------------------

            "vwap": vwap,

            "price_vs_vwap_percent": (
                price_vs_vwap
            ),

            # -------------------------------------------------
            # VOLUME
            # -------------------------------------------------

            "average_volume": (
                volume_info[
                    "average"
                ]
            ),

            "current_volume": (
                volume_info[
                    "current"
                ]
            ),

            "volume_ratio": (
                volume_info[
                    "ratio"
                ]
            ),

            "volume_analysis": (
                volume_info
            ),

            # -------------------------------------------------
            # MOMENTUM
            # -------------------------------------------------

            "momentum": momentum,

            "momentum_analysis": (
                momentum_info
            ),

            # -------------------------------------------------
            # CANDLE
            # -------------------------------------------------

            "candle_structure": candle,

            # -------------------------------------------------
            # RANGE
            # -------------------------------------------------

            "recent_range": (
                recent_range
            ),

            # -------------------------------------------------
            # BREAKOUT
            # -------------------------------------------------

            "breakout": breakout,

            # -------------------------------------------------
            # TECHNICAL CONFIRMATION
            # -------------------------------------------------

            "technical_confirmation": (
                confirmation
            ),
        }


# =========================================================
# SHARED INSTANCE
# =========================================================

indicator_engine = (
    IndicatorEngine()
)


# =========================================================
# EXPORTS
# =========================================================

__all__ = [
    "IndicatorEngine",
    "indicator_engine",
]
