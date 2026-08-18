from __future__ import annotations

from typing import Any

from app.clients.binance import binance_client


class MarketDataService:
    """
    Centralized market-data access layer.

    Keeps Binance-specific calls outside the
    higher-level scanner and analysis engines.
    """

    async def ticker_24h(
        self,
        market: str = "futures",
    ) -> Any:
        return await binance_client.ticker_24h(
            market=market
        )

    async def klines(
        self,
        symbol: str,
        interval: str,
        market: str = "futures",
        limit: int = 200,
    ) -> Any:
        return await binance_client.klines(
            symbol=symbol,
            interval=interval,
            market=market,
            limit=limit,
        )

    async def order_book(
        self,
        symbol: str,
        market: str = "futures",
        limit: int = 100,
    ) -> Any:
        return await binance_client.order_book(
            symbol=symbol,
            market=market,
            limit=limit,
        )

    async def exchange_info(
        self,
        market: str = "futures",
    ) -> dict[str, Any]:
        return await binance_client.exchange_info(
            market=market
        )


market_data_service = MarketDataService()


__all__ = [
    "MarketDataService",
    "market_data_service",
]
