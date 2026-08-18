from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MarketSymbol:
    """
    Represents a tradable Binance symbol.
    """

    symbol: str
    market: str
    base_asset: str
    quote_asset: str = "USDT"

    price: float = 0.0
    price_change_24h: float = 0.0
    quote_volume_24h: float = 0.0

    active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "market": self.market,
            "base_asset": self.base_asset,
            "quote_asset": self.quote_asset,
            "price": self.price,
            "price_change_24h": (
                self.price_change_24h
            ),
            "quote_volume_24h": (
                self.quote_volume_24h
            ),
            "active": self.active,
        }


@dataclass(frozen=True)
class MarketSnapshot:
    """
    Compact market snapshot used by scanner
    and analysis layers.
    """

    symbol: str
    market: str

    price: float

    price_change_24h: float = 0.0
    quote_volume_24h: float = 0.0

    bid_price: float = 0.0
    ask_price: float = 0.0

    bid_volume: float = 0.0
    ask_volume: float = 0.0

    timestamp: str | None = None

    def spread_percent(self) -> float:
        if self.price <= 0:
            return 0.0

        if (
            self.bid_price <= 0
            or self.ask_price <= 0
        ):
            return 0.0

        return (
            abs(
                self.ask_price
                - self.bid_price
            )
            / self.price
            * 100.0
        )

    def order_book_imbalance(
        self,
    ) -> float:
        total = (
            self.bid_volume
            + self.ask_volume
        )

        if total <= 0:
            return 0.0

        return (
            self.bid_volume
            - self.ask_volume
        ) / total

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "market": self.market,
            "price": self.price,
            "price_change_24h": (
                self.price_change_24h
            ),
            "quote_volume_24h": (
                self.quote_volume_24h
            ),
            "bid_price": self.bid_price,
            "ask_price": self.ask_price,
            "bid_volume": self.bid_volume,
            "ask_volume": self.ask_volume,
            "spread_percent": round(
                self.spread_percent(),
                6,
            ),
            "order_book_imbalance": round(
                self.order_book_imbalance(),
                6,
            ),
            "timestamp": self.timestamp,
        }


__all__ = [
    "MarketSymbol",
    "MarketSnapshot",
]
