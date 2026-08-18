from __future__ import annotations

import random
from typing import Any


class PostGenerator:
    """
    RR Trader community post generator.

    Generates a short trading-community post from
    already-validated RR Trader signal data.

    It does NOT calculate market direction.
    """

    LONG_HOOKS = [
        "Look at this setup",
        "My community, watch this move",
        "This setup is getting interesting",
        "Buyers are showing strength",
        "Watch this bullish structure",
        "This could be a strong setup",
    ]

    SHORT_HOOKS = [
        "Watch this setup carefully",
        "Sellers are gaining control",
        "This bearish setup is developing",
        "Downside pressure is building",
        "Watch this bearish structure",
        "This short setup is getting interesting",
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
    def _coin(
        analysis: dict[str, Any],
    ) -> str:

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

        if symbol.endswith(
            "USDT"
        ):
            return symbol[:-4]

        return symbol

    @staticmethod
    def _price(
        value: Any,
    ) -> str:

        number = (
            PostGenerator._safe_float(
                value
            )
        )

        if number <= 0:
            return "-"

        if number >= 1000:
            return f"{number:,.2f}"

        if number >= 1:
            return f"{number:,.4f}"

        if number >= 0.01:
            return f"{number:,.6f}"

        return f"{number:.8f}"

    def generate(
        self,
        analysis: dict[str, Any],
    ) -> dict[str, Any]:

        if not isinstance(
            analysis,
            dict,
        ):
            raise ValueError(
                "analysis must be a dictionary."
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

        coin = self._coin(
            analysis
        )

        if not coin:
            raise ValueError(
                "Coin symbol is missing."
            )

        confidence = max(
            0.0,
            min(
                100.0,
                self._safe_float(
                    analysis.get(
                        "confidence",
                        0,
                    )
                ),
            ),
        )

        entry = self._price(
            analysis.get(
                "entry"
            )
        )

        stop_loss = self._price(
            analysis.get(
                "stop_loss"
            )
        )

        tp1 = self._price(
            analysis.get(
                "tp1"
            )
        )

        tp2 = self._price(
            analysis.get(
                "tp2"
            )
        )

        tp3 = self._price(
            analysis.get(
                "tp3"
            )
        )

        if direction == "LONG":

            hook = random.choice(
                self.LONG_HOOKS
            )

            body = (
                f"${coin} is showing "
                "improving buyer strength, "
                "with the current structure "
                "supporting a possible move higher."
            )

        else:

            hook = random.choice(
                self.SHORT_HOOKS
            )

            body = (
                f"${coin} is showing "
                "increasing seller pressure, "
                "with the current structure "
                "supporting a possible move lower."
            )

        post = (
            f"{hook}\n\n"
            f"${coin} {direction}\n\n"
            f"{body}\n\n"
            f"Confidence: {confidence:.0f}%\n\n"
            f"Entry: {entry}\n"
            f"SL: {stop_loss}\n"
            f"TP1: {tp1}\n"
            f"TP2: {tp2}\n"
            f"TP3: {tp3}"
        )

        return {
            "success": True,
            "symbol": f"{coin}USDT",
            "coin": coin,
            "direction": direction,
            "confidence": confidence,
            "post": post,
        }


post_generator = PostGenerator()


__all__ = [
    "PostGenerator",
    "post_generator",
]
