from __future__ import annotations

from typing import Any


class MarketScanner:
    """
    RR Trader market scanner.

    Responsibilities:
    - Retrieve 24h market data.
    - Filter valid USDT markets.
    - Rank markets by activity.
    - Return candidates for deep analysis.

    This service does NOT generate trade signals.
    """

    QUOTE_ASSET = "USDT"

    def __init__(
        self,
        market_data: Any,
    ) -> None:
        self.market_data = market_data

    # =====================================================
    # NORMALIZATION
    # =====================================================

    @staticmethod
    def _symbol(
        item: dict[str, Any],
    ) -> str:

        return str(
            item.get(
                "symbol",
                "",
            )
        ).upper().strip()

    @staticmethod
    def _float(
        value: Any,
    ) -> float:

        try:
            return float(value or 0)

        except (
            TypeError,
            ValueError,
        ):
            return 0.0

    # =====================================================
    # MARKET FILTER
    # =====================================================

    def is_valid_market(
        self,
        item: dict[str, Any],
    ) -> bool:

        symbol = self._symbol(
            item
        )

        if not symbol.endswith(
            self.QUOTE_ASSET
        ):
            return False

        if not symbol:
            return False

        status = str(
            item.get(
                "status",
                "TRADING",
            )
        ).upper()

        if status not in {
            "",
            "TRADING",
        }:
            return False

        return True

    # =====================================================
    # ACTIVITY SCORE
    # =====================================================

    def activity_score(
        self,
        item: dict[str, Any],
    ) -> float:

        quote_volume = self._float(
            item.get(
                "quoteVolume",
                item.get(
                    "quote_volume",
                    0,
                ),
            )
        )

        price_change = abs(
            self._float(
                item.get(
                    "priceChangePercent",
                    item.get(
                        "price_change_percent",
                        0,
                    ),
                )
            )
        )

        trades = self._float(
            item.get(
                "count",
                item.get(
                    "trade_count",
                    0,
                ),
            )
        )

        # Log-free normalized activity score.
        # Volume dominates, while movement and trade
        # activity provide additional ranking information.

        volume_component = min(
            quote_volume / 1_000_000_000,
            100.0,
        )

        movement_component = min(
            price_change,
            20.0,
        )

        trade_component = min(
            trades / 100_000,
            20.0,
        )

        return (
            volume_component
            + movement_component
            + trade_component
        )

    # =====================================================
    # FILTER + RANK
    # =====================================================

    def rank_markets(
        self,
        ticker_data: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:

        candidates: list[
            dict[str, Any]
        ] = []


        for item in ticker_data:

            if not isinstance(
                item,
                dict,
            ):
                continue

            if not self.is_valid_market(
                item
            ):
                continue

            symbol = self._symbol(
                item
            )

            score = self.activity_score(
                item
            )

            candidates.append(
                {
                    **item,
                    "symbol": symbol,
                    "activity_score": round(
                        score,
                        4,
                    ),
                }
            )


        candidates.sort(
            key=lambda x:
                x.get(
                    "activity_score",
                    0,
                ),
            reverse=True,
        )

        return candidates

    # =====================================================
    # FULL MARKET SCAN
    # =====================================================

    async def scan_market(
        self,
        market: str = "futures",
    ) -> dict[str, Any]:

        raw_data = (
            await self.market_data.ticker_24h(
                market=market
            )
        )

        if isinstance(
            raw_data,
            dict,
        ):

            ticker_data = raw_data.get(
                "data",
                raw_data.get(
                    "result",
                    [],
                ),
            )

        else:

            ticker_data = raw_data


        if not isinstance(
            ticker_data,
            list,
        ):

            ticker_data = []


        ranked = self.rank_markets(
            ticker_data
        )


        return {
            "success": True,
            "market": market,
            "universe_mode": "FULL_MARKET",
            "total_markets": len(
                ticker_data
            ),
            "eligible_markets": len(
                ranked
            ),
            "markets": ranked,
        }

    # =====================================================
    # TOP CANDIDATES
    # =====================================================

    async def top_candidates(
        self,
        market: str = "futures",
        limit: int = 6,
    ) -> dict[str, Any]:

        limit = max(
            1,
            int(limit),
        )

        result = await self.scan_market(
            market=market
        )

        markets = result.get(
            "markets",
            [],
        )

        selected = markets[
            :limit
        ]


        return {
            **result,
            "deep_analysis_limit": limit,
            "candidates": selected,
        }


__all__ = [
    "MarketScanner",
]
