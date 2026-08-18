from __future__ import annotations

import asyncio
from typing import Any

from app.clients.binance import binance_client


class MarketDataService:
    """
    Centralized RR Trader market-data service.

    Handles:
    - Spot
    - Futures
    - 15m / 1h / 4h candles
    - Order book
    - Price / ticker
    - Futures derivatives data

    This service collects raw market data.
    It does NOT decide LONG or SHORT.
    """

    CORE_TIMEFRAMES = (
        "15m",
        "1h",
        "4h",
    )

    # =====================================================
    # BASIC MARKET DATA
    # =====================================================

    async def ticker_24h(
        self,
        market: str = "futures",
    ) -> Any:

        return await (
            binance_client.ticker_24h(
                market=market
            )
        )

    async def exchange_info(
        self,
        market: str = "futures",
    ) -> dict[str, Any]:

        return await (
            binance_client.exchange_info(
                market=market
            )
        )

    async def price(
        self,
        symbol: str,
        market: str = "futures",
    ) -> Any:

        return await (
            binance_client.price(
                symbol=symbol,
                market=market,
            )
        )

    # =====================================================
    # CANDLES
    # =====================================================

    async def klines(
        self,
        symbol: str,
        interval: str,
        market: str = "futures",
        limit: int = 200,
    ) -> Any:

        return await (
            binance_client.klines(
                symbol=symbol,
                interval=interval,
                market=market,
                limit=limit,
            )
        )

    async def core_timeframes(
        self,
        symbol: str,
        market: str = "futures",
        limit: int = 200,
    ) -> dict[str, Any]:

        tasks = [
            self.klines(
                symbol=symbol,
                interval=timeframe,
                market=market,
                limit=limit,
            )
            for timeframe
            in self.CORE_TIMEFRAMES
        ]

        results = await asyncio.gather(
            *tasks,
            return_exceptions=True,
        )

        output: dict[str, Any] = {}

        for timeframe, result in zip(
            self.CORE_TIMEFRAMES,
            results,
        ):

            if isinstance(
                result,
                Exception,
            ):

                output[timeframe] = {
                    "success": False,
                    "error": str(
                        result
                    ),
                    "candles": [],
                }

                continue

            output[timeframe] = {
                "success": True,
                "candles": result,
                "count": (
                    len(result)
                    if isinstance(
                        result,
                        list,
                    )
                    else 0
                ),
            }

        return output

    # =====================================================
    # ORDER BOOK
    # =====================================================

    async def order_book(
        self,
        symbol: str,
        market: str = "futures",
        limit: int = 100,
    ) -> Any:

        return await (
            binance_client.order_book(
                symbol=symbol,
                market=market,
                limit=limit,
            )
        )

    # =====================================================
    # FUTURES DERIVATIVES
    # =====================================================

    async def mark_price(
        self,
        symbol: str,
    ) -> Any:

        return await (
            binance_client.mark_price(
                symbol
            )
        )

    async def open_interest(
        self,
        symbol: str,
    ) -> Any:

        return await (
            binance_client.open_interest(
                symbol
            )
        )

    async def open_interest_history(
        self,
        symbol: str,
        period: str = "5m",
        limit: int = 30,
    ) -> list[dict[str, Any]]:

        return await (
            binance_client
            .open_interest_history(
                symbol=symbol,
                period=period,
                limit=limit,
            )
        )

    async def funding_rate(
        self,
        symbol: str,
        limit: int = 30,
    ) -> list[dict[str, Any]]:

        return await (
            binance_client.funding_rate(
                symbol=symbol,
                limit=limit,
            )
        )

    async def global_long_short_ratio(
        self,
        symbol: str,
        period: str = "5m",
        limit: int = 30,
    ) -> list[dict[str, Any]]:

        return await (
            binance_client
            .global_long_short_ratio(
                symbol=symbol,
                period=period,
                limit=limit,
            )
        )

    async def top_trader_long_short_ratio(
        self,
        symbol: str,
        period: str = "5m",
        limit: int = 30,
    ) -> list[dict[str, Any]]:

        return await (
            binance_client
            .top_trader_long_short_ratio(
                symbol=symbol,
                period=period,
                limit=limit,
            )
        )

    async def top_trader_position_ratio(
        self,
        symbol: str,
        period: str = "5m",
        limit: int = 30,
    ) -> list[dict[str, Any]]:

        return await (
            binance_client
            .top_trader_position_ratio(
                symbol=symbol,
                period=period,
                limit=limit,
            )
        )

    async def liquidation_orders(
        self,
        symbol: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:

        return await (
            binance_client
            .liquidation_orders(
                symbol=symbol,
                limit=limit,
            )
        )

    # =====================================================
    # COMPLETE SYMBOL SNAPSHOT
    # =====================================================

    async def symbol_snapshot(
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

        # -------------------------------------------------
        # Core market data
        # -------------------------------------------------

        core_task = (
            self.core_timeframes(
                symbol=symbol,
                market=market,
                limit=candle_limit,
            )
        )

        price_task = (
            self.price(
                symbol=symbol,
                market=market,
            )
        )

        ticker_task = (
            binance_client.ticker_24h(
                market=market,
                symbol=symbol,
            )
        )

        orderbook_task = (
            self.order_book(
                symbol=symbol,
                market=market,
                limit=100,
            )
        )

        base_tasks = [
            core_task,
            price_task,
            ticker_task,
            orderbook_task,
        ]

        # -------------------------------------------------
        # Futures-only data
        # -------------------------------------------------

        futures_tasks = []

        if market == "futures":

            futures_tasks = [
                self.mark_price(
                    symbol
                ),

                self.open_interest(
                    symbol
                ),

                self.open_interest_history(
                    symbol
                ),

                self.funding_rate(
                    symbol
                ),

                self.global_long_short_ratio(
                    symbol
                ),

                self.top_trader_long_short_ratio(
                    symbol
                ),

                self.top_trader_position_ratio(
                    symbol
                ),

                self.liquidation_orders(
                    symbol=symbol,
                    limit=100,
                ),
            ]

        else:

            futures_tasks = [
                asyncio.sleep(
                    0,
                    result=None,
                )
                for _ in range(8)
            ]

        results = await asyncio.gather(
            *base_tasks,
            *futures_tasks,
            return_exceptions=True,
        )

        core_data = results[0]
        price_data = results[1]
        ticker_data = results[2]
        order_book_data = results[3]

        futures_results = results[
            4:
        ]

        futures_data = {
            "mark_price": None,
            "open_interest": None,
            "open_interest_history": [],
            "funding_rate": [],
            "global_long_short_ratio": [],
            "top_trader_long_short_ratio": [],
            "top_trader_position_ratio": [],
            "liquidation_orders": [],
        }

        if market == "futures":

            keys = list(
                futures_data.keys()
            )

            for key, result in zip(
                keys,
                futures_results,
            ):

                if isinstance(
                    result,
                    Exception,
                ):

                    futures_data[key] = {
                        "error": str(
                            result
                        )
                    }

                else:

                    futures_data[key] = (
                        result
                    )

        return {
            "success": True,
            "symbol": symbol,
            "market": market,
            "timeframes": core_data,
            "price": price_data,
            "ticker_24h": ticker_data,
            "order_book": order_book_data,
            "derivatives": futures_data,
        }


market_data_service = MarketDataService()


__all__ = [
    "MarketDataService",
    "market_data_service",
]
