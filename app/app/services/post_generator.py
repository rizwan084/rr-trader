from __future__ import annotations

import random
from typing import Any, Dict


class PostGenerator:
    """
    RR Trader Binance community post generator.

    The generator creates short, attractive trading posts
    from structured scanner data.

    It does NOT calculate market direction itself.
    Direction, confidence and levels must come from the
    RR Trader analysis engine.
    """

    LONG_HOOKS = [
        "🔥 LOOK AT THIS SETUP — BUYERS ARE STEPPING IN!",
        "🚨 THIS COIN IS STARTING TO HEAT UP — WATCH THIS MOVE!",
        "👀 BUYERS ARE GAINING CONTROL — DON’T MISS THIS SETUP!",
        "🔥 STRONG BUYER PRESSURE IS BUILDING — KEEP THIS ONE ON WATCH!",
        "🚀 THIS LONG SETUP IS GETTING INTERESTING!",
        "⚡ BUYERS ARE SHOWING STRENGTH — THIS SETUP DESERVES ATTENTION!",
    ]

    SHORT_HOOKS = [
        "🔥 SELLERS ARE TAKING CONTROL — WATCH THIS SETUP!",
        "🚨 THIS COIN IS STARTING TO WEAKEN — KEEP AN EYE ON IT!",
        "👀 SELL-SIDE PRESSURE IS BUILDING — THIS SETUP DESERVES ATTENTION!",
        "🔥 BEARS ARE STEPPING IN — WATCH THIS MOVE!",
        "⚡ THIS SHORT SETUP IS STARTING TO ALIGN!",
        "🚨 DOWNWARD PRESSURE IS BUILDING — DON’T MISS THIS SETUP!",
    ]

    LONG_PARAGRAPHS = [
        (
            "Buyer pressure is building as active traders show "
            "stronger interest and the current market structure "
            "continues to support the upside."
        ),
        (
            "The setup is attracting buyer interest as the market "
            "continues to show bullish strength and upside momentum."
        ),
        (
            "Buyers are becoming more active and the current structure "
            "is giving this setup a bullish bias."
        ),
        (
            "The market is showing improving buyer control, with the "
            "current setup favoring a potential move higher."
        ),
    ]

    SHORT_PARAGRAPHS = [
        (
            "Sell-side pressure is increasing as active traders show "
            "stronger downside interest and the market structure "
            "continues to weaken."
        ),
        (
            "The setup is attracting seller interest as the market "
            "continues to show bearish pressure and downside momentum."
        ),
        (
            "Sellers are becoming more active and the current structure "
            "is giving this setup a bearish bias."
        ),
        (
            "The market is showing increasing seller control, with the "
            "current setup favoring a potential move lower."
        ),
    ]

    @staticmethod
    def _safe_float(
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
    def _coin_name(
        analysis: Dict[str, Any],
    ) -> str:
        """
        Return BTC instead of BTCUSDT.
        """

        coin = str(
            analysis.get(
                "coin",
                "",
            )
        ).upper().strip()

        if coin:
            return coin.replace(
                "USDT",
                "",
            )

        symbol = str(
            analysis.get(
                "symbol",
                "",
            )
        ).upper().strip()

        if symbol.endswith("USDT"):
            return symbol[:-4]

        return symbol

    @staticmethod
    def _money(
        value: Any,
    ) -> str:
        """
        Format prices without unnecessary zeros.
        """

        number = PostGenerator._safe_float(
            value
        )

        if number <= 0:
            return "—"

        if number >= 1000:
            return f"${number:,.2f}"

        if number >= 1:
            return f"${number:,.4f}"

        if number >= 0.01:
            return f"${number:,.6f}"

        return f"${number:.8f}"

    @staticmethod
    def _confidence(
        value: Any,
    ) -> float:
        return max(
            0.0,
            min(
                100.0,
                PostGenerator._safe_float(
                    value
                ),
            ),
        )

    def generate(
        self,
        analysis: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Generate an attractive community post.

        Expected analysis fields:
        - symbol / coin
        - direction
        - confidence
        - entry
        - stop_loss
        - tp1
        - tp2
        - tp3

        Only structured analysis data is used.
        """

        if not isinstance(
            analysis,
            dict,
        ):
            raise ValueError(
                "analysis must be a dictionary"
            )

        direction = str(
            analysis.get(
                "direction",
                "NEUTRAL",
            )
        ).upper().strip()

        if direction not in {
            "LONG",
            "SHORT",
        }:
            raise ValueError(
                "Post can only be generated "
                "for LONG or SHORT signals."
            )

        coin = self._coin_name(
            analysis
        )

        if not coin:
            raise ValueError(
                "Coin symbol is missing."
            )

        confidence = self._confidence(
            analysis.get(
                "confidence",
                0,
            )
        )

        entry = self._money(
            analysis.get(
                "entry"
            )
        )

        stop_loss = self._money(
            analysis.get(
                "stop_loss"
            )
        )

        tp1 = self._money(
            analysis.get(
                "tp1"
            )
        )

        tp2 = self._money(
            analysis.get(
                "tp2"
            )
        )

        tp3 = self._money(
            analysis.get(
                "tp3"
            )
        )

        if direction == "LONG":

            hook = random.choice(
                self.LONG_HOOKS
            )

            paragraph = random.choice(
                self.LONG_PARAGRAPHS
            )

            direction_text = (
                f"${coin} — LONG 🚀"
            )

        else:

            hook = random.choice(
                self.SHORT_HOOKS
            )

            paragraph = random.choice(
                self.SHORT_PARAGRAPHS
            )

            direction_text = (
                f"${coin} — SHORT 🔻"
            )

        post = (
            f"{hook}\n\n"
            f"{direction_text}\n\n"
            f"{paragraph}\n\n"
            f"Confidence: "
            f"{confidence:.0f}%\n\n"
            f"Entry: {entry}\n"
            f"SL: {stop_loss}\n"
            f"TP1: {tp1}\n"
            f"TP2: {tp2}\n"
            f"TP3: {tp3}"
        )

        return {
            "success": True,
            "coin": coin,
            "symbol": (
                f"{coin}USDT"
            ),
            "direction": direction,
            "confidence": confidence,
            "post": post,
        }


__all__ = [
    "PostGenerator",
]
