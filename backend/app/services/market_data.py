from __future__ import annotations

import asyncio
from typing import Any

from app.clients.binance import binance_client


class MarketDataService:
    """
    RR Trader centralized market-data service.

    Responsibilities:
    - Collect raw market data.
    - Support Binance Spot and Futures.
    - Collect multiple analysis timeframes.
    - Provide enough historical candles for:
        * repeated support tests
        * repeated resistance tests
        * rejection detection
        * structure analysis
        * breakout detection
        * momentum analysis
        * volume analysis
        * MTF confirmation
    - Collect order-book liquidity data.
    - Collect Futures derivatives data.

    IMPORTANT:
    This service does NOT decide LONG or SHORT.

    Signal decisions belong to:
        market_structure
        indicators
        mtf_engine
        liquidity_engine
        liquidation_engine
        confidence_engine
        analysis_engine
        signal_engine
        trade_engine
    """

    # =====================================================
    # TIMEFRAMES
    # =====================================================

    # Main confirmation timeframes.
    CORE_TIMEFRAMES = (
        "15m",
        "1h",
        "4h",
    )

    # Extra timeframes used for setup discovery.
    DISCOVERY_TIMEFRAMES = (
        "5m",
        "15m",
        "30m",
        "45m",
        "1h",
        "4h",
    )

    # Number of candles requested for each timeframe.
    #
    # Larger history is intentional because the new setup
    # engine must be able to determine whether price has
    # tested the same support/resistance multiple times.
    DEFAULT_CANDLE_LIMIT = 250

    MIN_CANDLE_LIMIT = 100
    MAX_CANDLE_LIMIT = 1000

    DEFAULT_ORDER_BOOK_LIMIT = 100

    # Derivatives history.
    DEFAULT_DERIVATIVES_LIMIT = 30

    # =====================================================
    # NORMALIZATION HELPERS
    # =====================================================

    @staticmethod
    def _normalize_symbol(
        symbol: str,
    ) -> str:

        return (
            str(symbol or "")
            .upper()
            .replace("/", "")
            .replace("-PERP", "")
            .replace("_PERP", "")
            .strip()
        )

    @staticmethod
    def _normalize_market(
        market: str,
    ) -> str:

        value = (
            str(market or "futures")
            .lower()
            .strip()
        )

        aliases = {
            "future": "futures",
            "futures": "futures",
            "future_usdt": "futures",
            "spot": "spot",
        }

        return aliases.get(
            value,
            value,
        )

    @classmethod
    def _safe_limit(
        cls,
        limit: int,
    ) -> int:

        try:
            value = int(limit)
        except (
            TypeError,
            ValueError,
        ):
            value = cls.DEFAULT_CANDLE_LIMIT

        return max(
            cls.MIN_CANDLE_LIMIT,
            min(
                cls.MAX_CANDLE_LIMIT,
                value,
            ),
        )

    # =====================================================
    # GENERIC SAFE CLIENT CALL
    # =====================================================

    async def _call_client(
        self,
        method_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:

        method = getattr(
            binance_client,
            method_name,
            None,
        )

        if not callable(method):

            return {
                "success": False,
                "available": False,
                "error": (
                    f"BinanceClient method "
                    f"'{method_name}' is not available."
                ),
            }

        try:

            result = await method(
                *args,
                **kwargs,
            )

            return result

        except Exception as exc:

            return {
                "success": False,
                "available": False,
                "error": str(exc),
            }

    # =====================================================
    # BASIC MARKET DATA
    # =====================================================

    async def ticker_24h(
        self,
        market: str = "futures",
    ) -> Any:

        market = self._normalize_market(
            market
        )

        return await self._call_client(
            "ticker_24h",
            market=market,
        )

    async def exchange_info(
        self,
        market: str = "futures",
    ) -> dict[str, Any]:

        market = self._normalize_market(
            market
        )

        result = await self._call_client(
            "exchange_info",
            market=market,
        )

        if isinstance(
            result,
            dict,
        ):
            return result

        return {
            "success": False,
            "available": False,
            "symbols": [],
            "error": "Invalid exchange info response.",
        }

    async def price(
        self,
        symbol: str,
        market: str = "futures",
    ) -> Any:

        symbol = self._normalize_symbol(
            symbol
        )

        market = self._normalize_market(
            market
        )

        return await self._call_client(
            "price",
            symbol=symbol,
            market=market,
        )

    # =====================================================
    # CANDLES
    # =====================================================

    async def klines(
        self,
        symbol: str,
        interval: str,
        market: str = "futures",
        limit: int = DEFAULT_CANDLE_LIMIT,
    ) -> Any:

        symbol = self._normalize_symbol(
            symbol
        )

        market = self._normalize_market(
            market
        )

        limit = self._safe_limit(
            limit
        )

        return await self._call_client(
            "klines",
            symbol=symbol,
            interval=interval,
            market=market,
            limit=limit,
        )

    # =====================================================
    # MULTI-TIMEFRAME CANDLES
    # =====================================================

    async def core_timeframes(
        self,
        symbol: str,
        market: str = "futures",
        limit: int = DEFAULT_CANDLE_LIMIT,
    ) -> dict[str, Any]:

        symbol = self._normalize_symbol(
            symbol
        )

        market = self._normalize_market(
            market
        )

        limit = self._safe_limit(
            limit
        )

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
                    "available": False,
                    "error": str(result),
                    "candles": [],
                    "count": 0,
                }

                continue

            if not isinstance(
                result,
                list,
            ):

                output[timeframe] = {
                    "success": False,
                    "available": False,
                    "error": (
                        "Invalid candle response."
                    ),
                    "candles": [],
                    "count": 0,
                }

                continue

            output[timeframe] = {
                "success": True,
                "available": True,
                "candles": result,
                "count": len(result),
            }

        return output

    # =====================================================
    # FULL DISCOVERY TIMEFRAMES
    # =====================================================

    async def discovery_timeframes(
        self,
        symbol: str,
        market: str = "futures",
        limit: int = DEFAULT_CANDLE_LIMIT,
    ) -> dict[str, Any]:

        """
        Fetch all timeframes needed for setup discovery.

        These candles are deliberately collected before
        signal generation.

        The purpose is to allow later engines to detect:

        - repeated support tests
        - repeated resistance tests
        - rejection
        - local consolidation
        - breakout
        - retest
        - momentum
        - volume confirmation
        - MTF alignment
        """

        symbol = self._normalize_symbol(
            symbol
        )

        market = self._normalize_market(
            market
        )

        limit = self._safe_limit(
            limit
        )

        tasks = [
            self.klines(
                symbol=symbol,
                interval=timeframe,
                market=market,
                limit=limit,
            )
            for timeframe
            in self.DISCOVERY_TIMEFRAMES
        ]

        results = await asyncio.gather(
            *tasks,
            return_exceptions=True,
        )

        output: dict[str, Any] = {}

        for timeframe, result in zip(
            self.DISCOVERY_TIMEFRAMES,
            results,
        ):

            if isinstance(
                result,
                Exception,
            ):

                output[timeframe] = {
                    "success": False,
                    "available": False,
                    "error": str(result),
                    "candles": [],
                    "count": 0,
                }

                continue

            if not isinstance(
                result,
                list,
            ):

                output[timeframe] = {
                    "success": False,
                    "available": False,
                    "error": (
                        "Invalid candle response."
                    ),
                    "candles": [],
                    "count": 0,
                }

                continue

            output[timeframe] = {
                "success": True,
                "available": True,
                "candles": result,
                "count": len(result),
            }

        return output

    # =====================================================
    # ORDER BOOK
    # =====================================================

    async def order_book(
        self,
        symbol: str,
        market: str = "futures",
        limit: int = DEFAULT_ORDER_BOOK_LIMIT,
    ) -> Any:

        symbol = self._normalize_symbol(
            symbol
        )

        market = self._normalize_market(
            market
        )

        try:
            safe_limit = int(limit)
        except (
            TypeError,
            ValueError,
        ):
            safe_limit = (
                self.DEFAULT_ORDER_BOOK_LIMIT
            )

        safe_limit = max(
            5,
            min(
                1000,
                safe_limit,
            ),
        )

        return await self._call_client(
            "order_book",
            symbol=symbol,
            market=market,
            limit=safe_limit,
        )

    # =====================================================
    # FUTURES DERIVATIVES
    # =====================================================

    async def mark_price(
        self,
        symbol: str,
    ) -> Any:

        symbol = self._normalize_symbol(
            symbol
        )

        return await self._call_client(
            "mark_price",
            symbol,
        )

    async def open_interest(
        self,
        symbol: str,
    ) -> Any:

        symbol = self._normalize_symbol(
            symbol
        )

        return await self._call_client(
            "open_interest",
            symbol,
        )

    async def open_interest_history(
        self,
        symbol: str,
        period: str = "5m",
        limit: int = DEFAULT_DERIVATIVES_LIMIT,
    ) -> Any:

        symbol = self._normalize_symbol(
            symbol
        )

        return await self._call_client(
            "open_interest_history",
            symbol=symbol,
            period=period,
            limit=max(
                1,
                min(
                    500,
                    int(limit),
                ),
            ),
        )

    async def funding_rate(
        self,
        symbol: str,
        limit: int = DEFAULT_DERIVATIVES_LIMIT,
    ) -> Any:

        symbol = self._normalize_symbol(
            symbol
        )

        return await self._call_client(
            "funding_rate",
            symbol=symbol,
            limit=max(
                1,
                min(
                    100,
                    int(limit),
                ),
            ),
        )

    async def global_long_short_ratio(
        self,
        symbol: str,
        period: str = "5m",
        limit: int = DEFAULT_DERIVATIVES_LIMIT,
    ) -> Any:

        symbol = self._normalize_symbol(
            symbol
        )

        return await self._call_client(
            "global_long_short_ratio",
            symbol=symbol,
            period=period,
            limit=max(
                1,
                min(
                    500,
                    int(limit),
                ),
            ),
        )

    async def top_trader_long_short_ratio(
        self,
        symbol: str,
        period: str = "5m",
        limit: int = DEFAULT_DERIVATIVES_LIMIT,
    ) -> Any:

        symbol = self._normalize_symbol(
            symbol
        )

        return await self._call_client(
            "top_trader_long_short_ratio",
            symbol=symbol,
            period=period,
            limit=max(
                1,
                min(
                    500,
                    int(limit),
                ),
            ),
        )

    async def top_trader_position_ratio(
        self,
        symbol: str,
        period: str = "5m",
        limit: int = DEFAULT_DERIVATIVES_LIMIT,
    ) -> Any:

        symbol = self._normalize_symbol(
            symbol
        )

        return await self._call_client(
            "top_trader_position_ratio",
            symbol=symbol,
            period=period,
            limit=max(
                1,
                min(
                    500,
                    int(limit),
                ),
            ),
        )

    async def liquidation_orders(
        self,
        symbol: str | None = None,
        limit: int = 100,
    ) -> Any:

        normalized_symbol = (
            self._normalize_symbol(symbol)
            if symbol
            else None
        )

        return await self._call_client(
            "liquidation_orders",
            symbol=normalized_symbol,
            limit=max(
                1,
                min(
                    1000,
                    int(limit),
                ),
            ),
        )

    # =====================================================
    # FUTURES DERIVATIVES SNAPSHOT
    # =====================================================

    async def derivatives_snapshot(
        self,
        symbol: str,
    ) -> dict[str, Any]:

        symbol = self._normalize_symbol(
            symbol
        )

        tasks = [
            self.mark_price(symbol),
            self.open_interest(symbol),
            self.open_interest_history(
                symbol
            ),
            self.funding_rate(symbol),
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

        results = await asyncio.gather(
            *tasks,
            return_exceptions=True,
        )

        keys = (
            "mark_price",
            "open_interest",
            "open_interest_history",
            "funding_rate",
            "global_long_short_ratio",
            "top_trader_long_short_ratio",
            "top_trader_position_ratio",
            "liquidation_orders",
        )

        output: dict[str, Any] = {}

        for key, result in zip(
            keys,
            results,
        ):

            if isinstance(
                result,
                Exception,
            ):

                output[key] = {
                    "success": False,
                    "available": False,
                    "error": str(result),
                }

            else:

                output[key] = result

        return output

    # =====================================================
    # SETUP DISCOVERY SNAPSHOT
    # =====================================================

    async def setup_discovery_snapshot(
        self,
        symbol: str,
        market: str = "futures",
        candle_limit: int = DEFAULT_CANDLE_LIMIT,
        order_book_limit: int = DEFAULT_ORDER_BOOK_LIMIT,
    ) -> dict[str, Any]:

        """
        Raw-data snapshot specifically designed for the
        new setup-discovery pipeline.

        IMPORTANT:

        This does NOT say:
            LONG
            SHORT
            BUY
            SELL

        It only collects the evidence required by the
        analysis engines.

        The next engines will determine whether the coin
        is actually sitting near a repeated support/
        resistance area and whether rejection/momentum/
        structure confirm the setup.
        """

        symbol = self._normalize_symbol(
            symbol
        )

        market = self._normalize_market(
            market
        )

        if market not in {
            "spot",
            "futures",
        }:

            raise ValueError(
                "market must be "
                "'spot' or 'futures'"
            )

        tasks = [
            self.discovery_timeframes(
                symbol=symbol,
                market=market,
                limit=candle_limit,
            ),
            self.price(
                symbol=symbol,
                market=market,
            ),
            self.ticker_24h(
                market=market,
            ),
            self.order_book(
                symbol=symbol,
                market=market,
                limit=order_book_limit,
            ),
        ]

        if market == "futures":

            tasks.append(
                self.derivatives_snapshot(
                    symbol
                )
            )

        else:

            tasks.append(
                asyncio.sleep(
                    0,
                    result={
                        "available": False,
                        "reason": (
                            "Derivatives are "
                            "not available "
                            "for Spot."
                        ),
                    },
                )
            )

        results = await asyncio.gather(
            *tasks,
            return_exceptions=True,
        )

        timeframes = results[0]
        price_data = results[1]
        ticker_data = results[2]
        order_book_data = results[3]
        derivatives_data = results[4]

        return {
            "success": True,
            "symbol": symbol,
            "market": market,

            # Raw candle evidence.
            "timeframes": timeframes,

            # Current market information.
            "price": price_data,
            "ticker_24h": ticker_data,

            # Liquidity evidence.
            "order_book": order_book_data,

            # Futures evidence.
            "derivatives": derivatives_data,

            # Explicit metadata for downstream engines.
            "setup_discovery": {
                "enabled": True,
                "purpose": (
                    "Find support/resistance "
                    "retests, rejection, "
                    "consolidation, breakout "
                    "and confirmation setups."
                ),
                "signal_decision": False,
                "top_gainer_loser_signal": False,
            },
        }

    # =====================================================
    # COMPLETE SYMBOL SNAPSHOT
    # =====================================================

    async def symbol_snapshot(
        self,
        symbol: str,
        market: str = "futures",
        candle_limit: int = DEFAULT_CANDLE_LIMIT,
    ) -> dict[str, Any]:

        """
        Backward-compatible complete symbol snapshot.

        The snapshot now uses the broader discovery
        timeframe set instead of only the three core
        timeframes.
        """

        return await self.setup_discovery_snapshot(
            symbol=symbol,
            market=market,
            candle_limit=candle_limit,
            order_book_limit=self.DEFAULT_ORDER_BOOK_LIMIT,
        )

    # =====================================================
    # QUICK CORE SNAPSHOT
    # =====================================================

    async def core_snapshot(
        self,
        symbol: str,
        market: str = "futures",
        candle_limit: int = DEFAULT_CANDLE_LIMIT,
    ) -> dict[str, Any]:

        """
        Lightweight snapshot for engines that only need
        15m / 1h / 4h.
        """

        symbol = self._normalize_symbol(
            symbol
        )

        market = self._normalize_market(
            market
        )

        tasks = [
            self.core_timeframes(
                symbol=symbol,
                market=market,
                limit=candle_limit,
            ),
            self.price(
                symbol=symbol,
                market=market,
            ),
            self.order_book(
                symbol=symbol,
                market=market,
                limit=self.DEFAULT_ORDER_BOOK_LIMIT,
            ),
        ]

        results = await asyncio.gather(
            *tasks,
            return_exceptions=True,
        )

        return {
            "success": True,
            "symbol": symbol,
            "market": market,
            "timeframes": results[0],
            "price": results[1],
            "order_book": results[2],
        }


# =========================================================
# SHARED INSTANCE
# =========================================================

market_data_service = (
    MarketDataService()
)


# =========================================================
# EXPORTS
# =========================================================

__all__ = [
    "MarketDataService",
    "market_data_service",
]
