from __future__ import annotations

from typing import Any, Callable, Awaitable

from app.clients.binance import binance_client
from app.services.market_data import market_data_service


_installed = False


def _ticker_rows(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []

    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").upper().replace("_USDT", "USDT")
        if not symbol.endswith("USDT"):
            continue
        last = row.get("lastPrice", row.get("lastPr", row.get("last", 0)))
        quote_volume = row.get("quoteVolume", row.get("usdtVolume", row.get("quoteVol", 0)))
        try:
            last_f = float(last or 0)
            volume_f = float(quote_volume or 0)
        except (TypeError, ValueError):
            continue
        if last_f <= 0:
            continue
        normalized.append({
            "symbol": symbol,
            "lastPrice": last_f,
            "price": last_f,
            "quoteVolume": volume_f,
            "quote_volume": volume_f,
            "priceChangePercent": float(row.get("change24h", row.get("priceChangePercent", 0)) or 0),
            "status": "TRADING",
            "source_exchange": "bitget",
        })
    return normalized


def install_market_data_resilience() -> None:
    global _installed
    if _installed:
        return

    original_ticker = market_data_service.ticker_24h
    original_klines = market_data_service.klines
    original_price = market_data_service.price
    original_order_book = market_data_service.order_book

    async def ticker_24h(market: str = "futures") -> Any:
        try:
            result = await original_ticker(market=market)
            if isinstance(result, list) and result:
                return result
            if isinstance(result, dict) and result.get("data"):
                return result
        except Exception:
            pass

        if str(market).lower() == "futures":
            try:
                rows = await binance_client.bitget_tickers()
                normalized = _ticker_rows(rows)
                if normalized:
                    return normalized
            except Exception:
                pass

        return []

    async def klines(symbol: str, interval: str, market: str = "futures", limit: int = 250) -> Any:
        try:
            result = await original_klines(symbol=symbol, interval=interval, market=market, limit=limit)
            if isinstance(result, list) and len(result) >= 20:
                return result
        except Exception:
            pass

        if str(market).lower() == "futures":
            try:
                result = await binance_client.bitget_klines(symbol, interval, limit=limit)
                if isinstance(result, list) and result:
                    return result
            except Exception:
                pass

        return []

    async def price(symbol: str, market: str = "futures") -> Any:
        try:
            result = await original_price(symbol=symbol, market=market)
            if result:
                return result
        except Exception:
            pass
        if str(market).lower() == "futures":
            try:
                return await binance_client.bitget_price(symbol)
            except Exception:
                pass
        return {}

    async def order_book(symbol: str, market: str = "futures", limit: int = 100) -> Any:
        try:
            result = await original_order_book(symbol=symbol, market=market, limit=limit)
            if result:
                return result
        except Exception:
            pass
        if str(market).lower() == "futures":
            try:
                return await binance_client.bitget_order_book(symbol, limit=limit)
            except Exception:
                pass
        return {}

    market_data_service.ticker_24h = ticker_24h  # type: ignore[method-assign]
    market_data_service.klines = klines  # type: ignore[method-assign]
    market_data_service.price = price  # type: ignore[method-assign]
    market_data_service.order_book = order_book  # type: ignore[method-assign]
    _installed = True
