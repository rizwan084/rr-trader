from __future__ import annotations

import asyncio
import json
import math
import time
from collections import defaultdict, deque
from typing import Any

import httpx
import websockets

BINANCE_WS = "wss://fstream.binance.com/ws/!forceOrder@arr"
BITGET_WS = "wss://ws.bitget.com/v2/ws/public"
OKX_WS = "wss://ws.okx.com:8443/ws/v5/public"

MAX_EVENTS_PER_SYMBOL = 5000
HTTP_TIMEOUT = 12.0


class LiquidationEngine:
    def __init__(self) -> None:
        self._events = defaultdict(lambda: deque(maxlen=MAX_EVENTS_PER_SYMBOL))
        self._tasks: list[asyncio.Task] = []
        self._running = False
        self._lock = asyncio.Lock()

        self._provider_status: dict[str, dict[str, Any]] = {
            "binance": {
                "enabled": True,
                "connected": False,
                "events": 0,
                "error": None,
            },
            "bitget": {
                "enabled": True,
                "connected": False,
                "events": 0,
                "error": None,
            },
            "okx": {
                "enabled": True,
                "connected": False,
                "events": 0,
                "error": None,
            },
            "mexc": {
                "enabled": True,
                "connected": False,
                "events": 0,
                "error": None,
                "mode": "ESTIMATED_ONLY",
            },
        }

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        clean = (
            str(symbol or "")
            .upper()
            .replace("/", "")
            .replace("-", "")
            .replace("_", "")
            .strip()
        )

        if not clean:
            raise ValueError("symbol is required")

        return (
            clean
            if clean.endswith("USDT")
            else f"{clean}USDT"
        )

    @staticmethod
    def _float(
        value: Any,
        default: float = 0.0,
    ) -> float:
        try:
            number = float(value)

            if math.isfinite(number):
                return number

            return default

        except (
            TypeError,
            ValueError,
        ):
            return default

    @staticmethod
    def _liquidation_side(
        provider: str,
        side: Any,
        pos_side: Any = None,
    ) -> str:

        side_text = str(
            side or ""
        ).lower()

        pos_text = str(
            pos_side or ""
        ).lower()

        if provider == "bitget":

            if side_text == "buy":
                return "LONG_LIQUIDATION"

            if side_text == "sell":
                return "SHORT_LIQUIDATION"

        if provider == "okx":

            if pos_text == "long":
                return "LONG_LIQUIDATION"

            if pos_text == "short":
                return "SHORT_LIQUIDATION"

            if side_text == "sell":
                return "LONG_LIQUIDATION"

            if side_text == "buy":
                return "SHORT_LIQUIDATION"

        if side_text == "sell":
            return "LONG_LIQUIDATION"

        if side_text == "buy":
            return "SHORT_LIQUIDATION"

        return "UNKNOWN"

    async def start(self) -> None:

        if self._running:
            return

        self._running = True

        self._tasks = [
            asyncio.create_task(
                self._binance_loop()
            ),
            asyncio.create_task(
                self._bitget_loop()
            ),
            asyncio.create_task(
                self._okx_loop()
            ),
        ]

    async def stop(self) -> None:

        self._running = False

        tasks = list(
            self._tasks
        )

        self._tasks = []

        for task in tasks:
            task.cancel()

        if tasks:
            await asyncio.gather(
                *tasks,
                return_exceptions=True,
            )

    async def _append(
        self,
        event: dict[str, Any],
    ) -> None:

        symbol = self.normalize_symbol(
            event.get(
                "symbol",
                "",
            )
        )

        event["symbol"] = symbol

        event["notional"] = self._float(
            event.get(
                "notional"
            )
        )

        async with self._lock:

            self._events[
                symbol
            ].append(
                event
            )

        provider = str(
            event.get(
                "provider",
                "",
            )
        ).lower()

        if provider in self._provider_status:

            self._provider_status[
                provider
            ]["events"] += 1

    async def _binance_loop(
        self,
    ) -> None:

        while self._running:

            try:

                async with websockets.connect(
                    BINANCE_WS,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=5,
                    max_size=4 * 1024 * 1024,
                ) as ws:

                    self._provider_status[
                        "binance"
                    ]["connected"] = True

                    self._provider_status[
                        "binance"
                    ]["error"] = None

                    async for raw in ws:

                        if not self._running:
                            break

                        message = json.loads(
                            raw
                        )

                        data = message.get(
                            "o",
                            message,
                        )

                        symbol = (
                            data.get("s")
                            or data.get("symbol")
                        )

                        if not symbol:
                            continue

                        quantity = self._float(
                            data.get("q")
                            or data.get("z")
                        )

                        price = self._float(
                            data.get("ap")
                            or data.get("p")
                        )

                        await self._append(
                            {
                                "provider": "binance",
                                "symbol": symbol,
                                "side": self._liquidation_side(
                                    "binance",
                                    data.get("S")
                                    or data.get("side"),
                                ),
                                "price": price,
                                "quantity": quantity,
                                "notional": (
                                    quantity
                                    * price
                                ),
                                "timestamp": int(
                                    self._float(
                                        data.get("T")
                                        or data.get("E"),
                                        time.time()
                                        * 1000,
                                    )
                                ),
                            }
                        )

            except asyncio.CancelledError:
                raise

            except Exception as exc:

                self._provider_status[
                    "binance"
                ]["connected"] = False

                self._provider_status[
                    "binance"
                ]["error"] = str(
                    exc
                )

                await asyncio.sleep(3)

    async def _bitget_loop(
        self,
    ) -> None:

        subscribe = {
            "op": "subscribe",
            "args": [
                {
                    "instType": "usdt-futures",
                    "topic": "liquidation",
                }
            ],
        }

        while self._running:

            try:

                async with websockets.connect(
                    BITGET_WS,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=5,
                    max_size=4 * 1024 * 1024,
                ) as ws:

                    await ws.send(
                        json.dumps(
                            subscribe
                        )
                    )

                    self._provider_status[
                        "bitget"
                    ]["connected"] = True

                    self._provider_status[
                        "bitget"
                    ]["error"] = None

                    async for raw in ws:

                        if not self._running:
                            break

                        if raw == "pong":
                            continue

                        message = json.loads(
                            raw
                        )

                        for item in (
                            message.get(
                                "data",
                                []
                            )
                            or []
                        ):

                            symbol = item.get(
                                "symbol"
                            )

                            if not symbol:
                                continue

                            price = self._float(
                                item.get(
                                    "price"
                                )
                            )

                            amount = self._float(
                                item.get(
                                    "amount"
                                )
                            )

                            await self._append(
                                {
                                    "provider": "bitget",
                                    "symbol": symbol,
                                    "side": self._liquidation_side(
                                        "bitget",
                                        item.get(
                                            "side"
                                        ),
                                    ),
                                    "price": price,
                                    "quantity": amount,
                                    "notional": amount,
                                    "timestamp": int(
                                        self._float(
                                            item.get(
                                                "ts"
                                            ),
                                            time.time()
                                            * 1000,
                                        )
                                    ),
                                }
                            )

            except asyncio.CancelledError:
                raise

            except Exception as exc:

                self._provider_status[
                    "bitget"
                ]["connected"] = False

                self._provider_status[
                    "bitget"
                ]["error"] = str(
                    exc
                )

                await asyncio.sleep(3)

    async def _okx_loop(
        self,
    ) -> None:

        subscribe = {
            "op": "subscribe",
            "args": [
                {
                    "channel": "liquidation-orders",
                    "instType": "SWAP",
                }
            ],
        }

        while self._running:

            try:

                async with websockets.connect(
                    OKX_WS,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=5,
                    max_size=4 * 1024 * 1024,
                ) as ws:

                    await ws.send(
                        json.dumps(
                            subscribe
                        )
                    )

                    self._provider_status[
                        "okx"
                    ]["connected"] = True

                    self._provider_status[
                        "okx"
                    ]["error"] = None

                    async for raw in ws:

                        if not self._running:
                            break

                        message = json.loads(
                            raw
                        )

                        if (
                            message.get(
                                "event"
                            )
                            == "error"
                        ):

                            raise RuntimeError(
                                message.get(
                                    "msg",
                                    "OKX subscription error",
                                )
                            )

                        for item in (
                            message.get(
                                "data",
                                []
                            )
                            or []
                        ):

                            inst_id = str(
                                item.get(
                                    "instId",
                                    "",
                                )
                            )

                            symbol = (
                                inst_id
                                .replace(
                                    "-SWAP",
                                    "",
                                )
                                .replace(
                                    "-",
                                    "",
                                )
                            )

                            if not symbol:
                                continue

                            price = self._float(
                                item.get(
                                    "liqPx"
                                )
                                or item.get(
                                    "bkPx"
                                )
                            )

                            amount = self._float(
                                item.get(
                                    "sz"
                                )
                                or item.get(
                                    "bkSz"
                                )
                            )

                            await self._append(
                                {
                                    "provider": "okx",
                                    "symbol": symbol,
                                    "side": self._liquidation_side(
                                        "okx",
                                        item.get(
                                            "side"
                                        ),
                                        item.get(
                                            "posSide"
                                        ),
                                    ),
                                    "price": price,
                                    "quantity": amount,
                                    "notional": (
                                        amount
                                        * price
                                    ),
                                    "timestamp": int(
                                        self._float(
                                            item.get(
                                                "ts"
                                            ),
                                            time.time()
                                            * 1000,
                                        )
                                    ),
                                }
                            )

            except asyncio.CancelledError:
                raise

            except Exception as exc:

                self._provider_status[
                    "okx"
                ]["connected"] = False

                self._provider_status[
                    "okx"
                ]["error"] = str(
                    exc
                )

                await asyncio.sleep(3)

    async def _bitget_history(
        self,
        symbol: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:

        url = (
            "https://api.bitget.com"
            "/api/v3/market/liquidations"
        )

        params = {
            "category": "USDT-FUTURES",
            "symbol": symbol,
            "limit": max(
                1,
                min(
                    limit,
                    100,
                ),
            ),
        }

        async with httpx.AsyncClient(
            timeout=12
        ) as client:

            response = await client.get(
                url,
                params=params,
            )

            response.raise_for_status()

            payload = response.json()

        items = []

        if isinstance(
            payload,
            dict,
        ):

            data = payload.get(
                "data"
            )

            if isinstance(
                data,
                dict,
            ):

                items = (
                    data.get(
                        "list",
                        []
                    )
                    or []
                )

        normalized = []

        for item in items:

            if not isinstance(
                item,
                dict,
            ):
                continue

            price = self._float(
                item.get(
                    "price"
                )
            )

            amount = self._float(
                item.get(
                    "amount"
                )
            )

            normalized.append(
                {
                    "provider": "bitget",
                    "symbol": self.normalize_symbol(
                        item.get(
                            "symbol",
                            symbol,
                        )
                    ),
                    "side": self._liquidation_side(
                        "bitget",
                        item.get(
                            "side"
                        ),
                    ),
                    "price": price,
                    "quantity": amount,
                    "notional": amount,
                    "timestamp": int(
                        self._float(
                            item.get(
                                "ts"
                            ),
                            time.time()
                            * 1000,
                        )
                    ),
                }
            )

        return normalized

    async def analyze(
        self,
        symbol: str,
        current_price: float,
        hours: int = 24,
        bin_count: int = 80,
    ) -> dict[str, Any]:

        symbol = self.normalize_symbol(
            symbol
        )

        cutoff = (
            int(
                time.time()
                * 1000
            )
            - max(
                1,
                hours,
            )
            * 3600
            * 1000
        )

        try:

            history = (
                await self._bitget_history(
                    symbol,
                    100,
                )
            )

        except Exception as exc:

            history = []

            self._provider_status[
                "bitget"
            ]["history_error"] = str(
                exc
            )

        async with self._lock:

            live = list(
                self._events.get(
                    symbol,
                    []
                )
            )

        merged = [
            event
            for event in (
                history
                + live
            )
            if (
                self._float(
                    event.get(
                        "timestamp"
                    )
                )
                >= cutoff
            )
            and (
                self._float(
                    event.get(
                        "price"
                    )
                )
                > 0
            )
        ]

        unique = {}

        for event in merged:

            key = (
                event.get(
                    "provider"
                ),
                event.get(
                    "timestamp"
                ),
                event.get(
                    "price"
                ),
                event.get(
                    "side"
                ),
                event.get(
                    "quantity"
                ),
            )

            unique[key] = event

        events = list(
            unique.values()
        )

        price = self._float(
            current_price
        )

        if (
            price <= 0
            and events
        ):

            price = self._float(
                events[-1].get(
                    "price"
                )
            )

        def total(
            items: list[
                dict[str, Any]
            ]
        ) -> float:

            return sum(
                self._float(
                    item.get(
                        "notional"
                    )
                )
                for item in items
            )

        upper = [
            event
            for event in events
            if self._float(
                event.get(
                    "price"
                )
            ) >= price
        ]

        lower = [
            event
            for event in events
            if self._float(
                event.get(
                    "price"
                )
            ) < price
        ]

        upper_total = total(
            upper
        )

        lower_total = total(
            lower
        )

        prices = [
            self._float(
                event.get(
                    "price"
                )
            )
            for event in events
            if self._float(
                event.get(
                    "price"
                )
            ) > 0
        ]

        if prices:

            low = min(
                min(prices),
                price,
            )

            high = max(
                max(prices),
                price,
            )

        else:

            low = (
                price
                * 0.97
            )

            high = (
                price
                * 1.03
            )

        span = max(
            high - low,
            price * 0.01,
        )

        count = max(
            10,
            bin_count,
        )

        step = (
            span / count
        )

        heatmap = []

        for index in range(
            count
        ):

            p0 = (
                low
                + index
                * step
            )

            p1 = (
                p0
                + step
            )

            total_value = 0.0
            long_total = 0.0
            short_total = 0.0

            for event in events:

                event_price = (
                    self._float(
                        event.get(
                            "price"
                        )
                    )
                )

                if (
                    p0
                    <= event_price
                    < p1
                ):

                    value = (
                        self._float(
                            event.get(
                                "notional"
                            )
                        )
                    )

                    total_value += (
                        value
                    )

                    if (
                        event.get(
                            "side"
                        )
                        == "LONG_LIQUIDATION"
                    ):

                        long_total += (
                            value
                        )

                    elif (
                        event.get(
                            "side"
                        )
                        == "SHORT_LIQUIDATION"
                    ):

                        short_total += (
                            value
                        )

            heatmap.append(
                {
                    "price_low": p0,
                    "price_high": p1,
                    "price": (
                        p0 + p1
                    ) / 2,
                    "intensity": (
                        total_value
                    ),
                    "long_liquidation": (
                        long_total
                    ),
                    "short_liquidation": (
                        short_total
                    ),
                }
            )

        max_intensity = max(
            (
                self._float(
                    item[
                        "intensity"
                    ]
                )
                for item
                in heatmap
            ),
            default=0.0,
        )

        for item in heatmap:

            item[
                "normalized_intensity"
            ] = (
                round(
                    self._float(
                        item[
                            "intensity"
                        ]
                    )
                    / max_intensity,
                    6,
                )
                if max_intensity > 0
                else 0.0
            )

        clusters = [
            item
            for item
            in sorted(
                heatmap,
                key=lambda x:
                    self._float(
                        x[
                            "intensity"
                        ]
                    ),
                reverse=True,
            )[:12]
            if self._float(
                item[
                    "intensity"
                ]
            ) > 0
        ]

        upper_clusters = [
            item
            for item
            in clusters
            if item[
                "price"
            ] >= price
        ]

        lower_clusters = [
            item
            for item
            in clusters
            if item[
                "price"
            ] < price
        ]

        strongest_upper = (
            upper_clusters[0]
            if upper_clusters
            else None
        )

        strongest_lower = (
            lower_clusters[0]
            if lower_clusters
            else None
        )

        if (
            upper_total
            > lower_total
            * 1.25
        ):

            bias = (
                "UPSIDE_LIQUIDITY"
            )

        elif (
            lower_total
            > upper_total
            * 1.25
        ):

            bias = (
                "DOWNSIDE_LIQUIDITY"
            )

        else:

            bias = "NEUTRAL"

        if (
            strongest_upper
            and strongest_lower
        ):

            if (
                strongest_upper[
                    "intensity"
                ]
                > strongest_lower[
                    "intensity"
                ]
                * 1.25
            ):

                sweep = "UP"

            elif (
                strongest_lower[
                    "intensity"
                ]
                > strongest_upper[
                    "intensity"
                ]
                * 1.25
            ):

                sweep = "DOWN"

            else:

                sweep = "NEUTRAL"

        else:

            sweep = "NEUTRAL"

        return {
            "success": True,
            "symbol": symbol,
            "current_price": price,
            "hours": hours,
            "event_count": len(
                events
            ),
            "providers": (
                self._provider_status
            ),
            "upper_liquidation_total": round(
                upper_total,
                2,
            ),
            "lower_liquidation_total": round(
                lower_total,
                2,
            ),
            "liquidity_bias": bias,
            "sweep_direction": sweep,
            "strongest_upper_cluster": (
                strongest_upper
            ),
            "strongest_lower_cluster": (
                strongest_lower
            ),
            "clusters": clusters,
            "heatmap": heatmap,
            "data_note": (
                "Observed exchange liquidation events only. "
                "This is RR Trader's own heatmap, not CoinGlass "
                "proprietary estimated liquidation levels."
            ),
        }

    def snapshot(
        self,
    ) -> dict[str, Any]:

        return {
            "running": self._running,
            "providers": (
                self._provider_status
            ),
            "symbols_with_live_events": len(
                self._events
            ),
        }


liquidation_engine = LiquidationEngine()
