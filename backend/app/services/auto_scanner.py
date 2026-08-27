from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.services.market_data import (
    market_data_service,
)
from app.services.market_scanner import (
    MarketScanner,
)
from app.services.master_analysis import (
    master_analysis_engine,
)
from app.services.supabase_store import persist_scan_result

# New multi-exchange client
from app.clients.binance import (
    BinanceClient,
    SUPPORTED_TIMEFRAMES,
)


# =========================================================
# RR TRADER MULTI-EXCHANGE AUTO SCANNER
#
# Exchanges:
#   Binance
#   Bitget
#   MEXC
#   OKX
#
# Timeframes:
#   5m
#   15m
#   30m
#   45m
#   1h
#   4h
#   1d
#
# Scan interval:
#   60 seconds
#
# IMPORTANT:
# The existing 24-point master analysis remains the
# decision engine. This scanner now builds the multi-
# exchange / multi-timeframe market context around it.
# =========================================================


EXCHANGES = (
    "binance",
    "bitget",
    "mexc",
    "okx",
)


TIMEFRAMES = (
    "5m",
    "15m",
    "30m",
    "45m",
    "1h",
    "4h",
    "1d",
)


MIN_SCAN_SECONDS = 60
MAX_DEEP_ANALYSIS_CANDIDATES = 8
MAX_MULTI_EXCHANGE_ENRICH_CANDIDATES = 0


# =========================================================
# SAFE NUMBER
# =========================================================


def safe_float(
    value: Any,
    default: float = 0.0,
) -> float:

    try:
        if value is None:
            return default

        return float(value)

    except (
        TypeError,
        ValueError,
    ):

        return default


# =========================================================
# SYMBOL NORMALIZER
# =========================================================


def clean_symbol(
    symbol: Any,
) -> str:

    return (
        str(symbol or "")
        .upper()
        .replace(
            "/",
            "",
        )
        .replace(
            "-PERP",
            "",
        )
        .replace(
            "_PERP",
            "",
        )
        .replace(
            "-USDT-SWAP",
            "USDT",
        )
        .replace(
            "_USDT",
            "USDT",
        )
        .strip()
    )


# =========================================================
# AUTO SCANNER
# =========================================================


class AutoScanner:

    """
    RR Trader continuous scanner.

    Existing behavior:
        Full Binance market screening
        Top candidates
        24-point master analysis
        Automatic refresh

    New behavior:
        Binance
        Bitget
        MEXC
        OKX

        5m
        15m
        30m
        45m
        1h
        4h
        1d

    The scanner never lets one exchange or one symbol
    failure stop the complete cycle.
    """

    def __init__(
        self,
        market: str = "futures",
        scan_limit: int | None = None,
        refresh_seconds: int | None = None,
    ) -> None:

        self.market = (
            str(
                market
            )
            .lower()
            .strip()
        )

        # -------------------------------------------------
        # Candidate depth
        # -------------------------------------------------

        self.scan_limit = max(
            1,
            min(
                MAX_DEEP_ANALYSIS_CANDIDATES,
                int(
                    scan_limit
                    if scan_limit is not None
                    else settings.deep_analysis_limit
                ),
            ),
        )

        # -------------------------------------------------
        # Minimum interval = 60 seconds
        # -------------------------------------------------

        self.refresh_seconds = max(
            MIN_SCAN_SECONDS,
            int(
                refresh_seconds
                if refresh_seconds is not None
                else settings.auto_scan_interval
            ),
        )

        # -------------------------------------------------
        # Existing Binance scanner
        # -------------------------------------------------

        self.scanner = MarketScanner(
            market_data_service
        )

        # -------------------------------------------------
        # Multi-exchange client
        # -------------------------------------------------

        self.exchange_client = (
            BinanceClient()
        )

        # -------------------------------------------------
        # Background task
        # -------------------------------------------------

        self._task: (
            asyncio.Task[None]
            | None
        ) = None

        self._running = False

        self._scan_lock = (
            asyncio.Lock()
        )

        # -------------------------------------------------
        # State
        # -------------------------------------------------

        self._last_scan: dict[
            str,
            Any,
        ] = {}

        self._last_successful_scan: dict[
            str,
            Any,
        ] = {}

        self._last_scan_at: (
            datetime
            | None
        ) = None

        self._last_successful_scan_at: (
            datetime
            | None
        ) = None

        self._next_scan_at: (
            float
            | None
        ) = None

        self._scan_count = 0

        self._error_count = 0

        # -------------------------------------------------
        # Exchange status
        # -------------------------------------------------

        self._exchange_status: dict[
            str,
            dict[str, Any],
        ] = {
            exchange: {
                "available": False,
                "symbols": 0,
                "error": None,
            }
            for exchange in EXCHANGES
        }

    # =====================================================
    # MULTI-EXCHANGE MARKET CONTEXT
    # =====================================================

    async def _load_exchange_context(
        self,
        symbol: str,
    ) -> dict[str, Any]:

        """
        Load the same symbol from all exchanges
        and all requested timeframes.

        This is intentionally fault tolerant.
        If one exchange fails, the others continue.
        """

        symbol = clean_symbol(
            symbol
        )

        result: dict[
            str,
            Any,
        ] = {
            "symbol": symbol,
            "exchanges": {},
        }

        # -------------------------------------------------
        # Exchange/timeframe worker
        # -------------------------------------------------

        async def load_one(
            exchange: str,
            timeframe: str,
        ) -> tuple[
            str,
            str,
            Any,
        ]:

            try:

                candles = (
                    await self.exchange_client.exchange_klines(
                        exchange=exchange,
                        symbol=symbol,
                        interval=timeframe,
                        market=self.market,
                        limit=120,
                    )
                )

                return (
                    exchange,
                    timeframe,
                    {
                        "success": True,
                        "candle_count": (
                            len(candles)
                            if isinstance(
                                candles,
                                list,
                            )
                            else 0
                        ),
                        "candles": candles,
                    },
                )

            except Exception as exc:

                return (
                    exchange,
                    timeframe,
                    {
                        "success": False,
                        "candle_count": 0,
                        "candles": [],
                        "error": str(exc),
                    },
                )

        jobs = [
            load_one(
                exchange,
                timeframe,
            )
            for exchange in EXCHANGES
            for timeframe in TIMEFRAMES
        ]

        responses = await asyncio.gather(
            *jobs,
            return_exceptions=False,
        )

        # -------------------------------------------------
        # Build nested structure
        # -------------------------------------------------

        for (
            exchange,
            timeframe,
            payload,
        ) in responses:

            if exchange not in result[
                "exchanges"
            ]:

                result[
                    "exchanges"
                ][exchange] = {}

            result[
                "exchanges"
            ][exchange][
                timeframe
            ] = payload

        # -------------------------------------------------
        # Summary
        # -------------------------------------------------

        exchange_summary = {}

        for exchange in EXCHANGES:

            timeframes = result[
                "exchanges"
            ].get(
                exchange,
                {},
            )

            successful = sum(
                1
                for item in timeframes.values()
                if item.get(
                    "success",
                    False,
                )
            )

            exchange_summary[
                exchange
            ] = {
                "success": (
                    successful > 0
                ),
                "timeframes_loaded":
                    successful,
                "total_timeframes":
                    len(TIMEFRAMES),
            }

        result[
            "exchange_summary"
        ] = exchange_summary

        return result

    # =====================================================
    # BUILD MULTI-EXCHANGE CANDIDATE
    # =====================================================

    async def _enrich_candidate(
        self,
        candidate: dict[str, Any],
    ) -> dict[str, Any]:

        if not isinstance(
            candidate,
            dict,
        ):

            return candidate

        symbol = clean_symbol(
            candidate.get(
                "symbol"
            )
        )

        if not symbol:

            return candidate

        context = (
            await self._load_exchange_context(
                symbol
            )
        )

        enriched = dict(
            candidate
        )

        enriched[
            "multi_exchange"
        ] = context

        enriched[
            "supported_exchanges"
        ] = list(
            EXCHANGES
        )

        enriched[
            "analysis_timeframes"
        ] = list(
            TIMEFRAMES
        )

        return enriched

    # =====================================================
    # SINGLE SCAN
    # =====================================================

    async def scan_once(
        self,
    ) -> dict[str, Any]:

        async with (
            self._scan_lock
        ):

            started_at = (
                time.monotonic()
            )

            scan_timestamp = (
                datetime.now(
                    timezone.utc
                )
            )

            self._scan_count += 1

            try:

                # =========================================
                # STAGE 1
                # Binance full-market candidate discovery
                # =========================================

                universe = (
                    await self.scanner.top_candidates(
                        market=self.market,
                        limit=self.scan_limit,
                    )
                )

                if not isinstance(
                    universe,
                    dict,
                ):

                    raise RuntimeError(
                        "Scanner returned invalid "
                        "universe data."
                    )

                candidates = universe.get(
                    "candidates",
                    [],
                )

                if not isinstance(
                    candidates,
                    list,
                ):

                    candidates = []

                # =========================================
                # STAGE 2
                # Multi-exchange enrichment is disabled for the live scanner.
                # Production scanning uses Binance market data only so the
                # 60-second scanner stays responsive on Render.
                enriched_candidates = [dict(candidate) for candidate in candidates]

                # =========================================
                # STAGE 3
                # Existing 24-point analysis
                # =========================================

                async def analyze_candidate(
                    candidate: dict[str, Any],
                ) -> dict[str, Any]:

                    if not isinstance(
                        candidate,
                        dict,
                    ):

                        return {
                            "success": False,
                            "error":
                                "Invalid candidate.",
                        }

                    symbol = clean_symbol(
                        candidate.get(
                            "symbol",
                            "",
                        )
                    )

                    if not symbol:

                        return {
                            "success": False,
                            "error":
                                "Missing symbol.",
                        }

                    try:

                        analysis = (
                            await master_analysis_engine.analyze(
                                symbol=symbol,
                                market=self.market,
                                candle_limit=120,
                            )
                        )

                        # ---------------------------------
                        # Attach multi-exchange context
                        # ---------------------------------

                        if not isinstance(
                            analysis,
                            dict,
                        ):

                            analysis = {}

                        result = dict(
                            analysis
                        )

                        result[
                            "symbol"
                        ] = symbol

                        result[
                            "exchange_mode"
                        ] = (
                            "MULTI_EXCHANGE"
                        )

                        result[
                            "exchanges"
                        ] = list(
                            EXCHANGES
                        )

                        result[
                            "timeframes"
                        ] = list(
                            TIMEFRAMES
                        )

                        result[
                            "multi_exchange_data"
                        ] = candidate.get(
                            "multi_exchange",
                            {},
                        )

                        result[
                            "candidate"
                        ] = candidate

                        return {
                            "success": True,
                            "symbol": symbol,
                            "candidate":
                                candidate,
                            "analysis":
                                result,
                        }

                    except Exception as exc:

                        return {
                            "success": False,
                            "symbol": symbol,
                            "candidate":
                                candidate,
                            "error": str(exc),
                        }

                # -----------------------------------------
                # Deep analysis
                # -----------------------------------------

                results = await asyncio.gather(
                    *[
                        analyze_candidate(
                            candidate
                        )
                        for candidate
                        in enriched_candidates
                    ],
                    return_exceptions=False,
                )

                analyses: list[
                    dict[str, Any]
                ] = []

                failures: list[
                    dict[str, Any]
                ] = []

                for result in results:

                    if not isinstance(
                        result,
                        dict,
                    ):

                        continue

                    if not result.get(
                        "success",
                        False,
                    ):

                        failures.append(
                            result
                        )

                        continue

                    analysis = result.get(
                        "analysis"
                    )

                    if not isinstance(
                        analysis,
                        dict,
                    ):

                        failures.append(
                            {
                                "success":
                                    False,
                                "symbol":
                                    result.get(
                                        "symbol"
                                    ),
                                "error":
                                    "Invalid analysis result.",
                            }
                        )

                        continue

                    analyses.append(
                        analysis
                    )

                # =========================================
                # STAGE 4
                # Ranking
                # =========================================

                analyses.sort(
                    key=lambda item: (
                        safe_float(
                            item.get(
                                "confidence",
                                0,
                            )
                        ),
                        safe_float(
                            item.get(
                                "risk_reward",
                                0,
                            )
                        ),
                    ),
                    reverse=True,
                )

                publishable = [
                    item
                    for item in analyses
                    if item.get(
                        "publishable",
                        False,
                    )
                ]

                publishable.sort(
                    key=lambda item: (
                        safe_float(
                            item.get(
                                "confidence",
                                0,
                            )
                        ),
                        safe_float(
                            item.get(
                                "risk_reward",
                                0,
                            )
                        ),
                    ),
                    reverse=True,
                )

                # =========================================
                # STAGE 5
                # Best opportunity
                # =========================================

                best = (
                    publishable[0]
                    if publishable
                    else (
                        analyses[0]
                        if analyses
                        else None
                    )
                )

                # =========================================
                # EXCHANGE STATUS
                # =========================================

                exchange_status = (
                    self._calculate_exchange_status(
                        enriched_candidates
                    )
                )

                # =========================================
                # FINAL RESULT
                # =========================================

                elapsed = (
                    time.monotonic()
                    - started_at
                )

                result = {
                    "success": True,

                    "market":
                        self.market,

                    "universe_mode":
                        "FULL_MARKET_MULTI_EXCHANGE",

                    "timestamp":
                        scan_timestamp.isoformat(),

                    "scan_number":
                        self._scan_count,

                    "elapsed_seconds":
                        round(
                            elapsed,
                            3,
                        ),

                    "scanned_universe":
                        int(
                            universe.get(
                                "eligible_markets",
                                universe.get(
                                    "scanned_universe",
                                    0,
                                ),
                            )
                            or 0
                        ),

                    "candidate_count":
                        len(
                            enriched_candidates
                        ),

                    "deep_analyzed":
                        len(
                            analyses
                        ),

                    "failed_analysis":
                        len(
                            failures
                        ),

                    "publishable_count":
                        len(
                            publishable
                        ),

                    "best":
                        best,

                    "exchanges":
                        list(
                            EXCHANGES
                        ),

                    "timeframes":
                        list(
                            TIMEFRAMES
                        ),

                    "exchange_status":
                        exchange_status,

                    "core_timeframes":
                        list(
                            TIMEFRAMES
                        ),

                    "candidates":
                        enriched_candidates,

                    "analyses":
                        analyses,

                    "publishable_signals":
                        publishable,

                    "errors":
                        failures,
                }

                self._last_scan = (
                    result
                )

                self._last_successful_scan = (
                    dict(result)
                )

                self._last_scan_at = (
                    scan_timestamp
                )

                self._last_successful_scan_at = (
                    scan_timestamp
                )

                self._error_count = 0

                return dict(
                    result
                )

            except Exception as exc:

                self._error_count += 1

                failed_result = {
                    "success":
                        False,

                    "market":
                        self.market,

                    "timestamp":
                        scan_timestamp.isoformat(),

                    "scan_number":
                        self._scan_count,

                    "error":
                        str(exc),

                    "exchanges":
                        list(
                            EXCHANGES
                        ),

                    "timeframes":
                        list(
                            TIMEFRAMES
                        ),

                    "last_successful":
                        dict(
                            self._last_successful_scan
                        ),
                }

                self._last_scan = (
                    failed_result
                )

                self._last_scan_at = (
                    scan_timestamp
                )

                return dict(
                    failed_result
                )

    # =====================================================
    # EXCHANGE STATUS
    # =====================================================

    def _calculate_exchange_status(
        self,
        candidates: list[
            dict[str, Any]
        ],
    ) -> dict[
        str,
        Any,
    ]:

        status = {
            exchange: {
                "available": False,
                "symbols": 0,
                "timeframes_loaded": 0,
                "errors": 0,
            }
            for exchange in EXCHANGES
        }

        for candidate in candidates:

            context = candidate.get(
                "multi_exchange",
                {},
            )

            exchanges = context.get(
                "exchanges",
                {},
            )

            if not isinstance(
                exchanges,
                dict,
            ):

                continue

            for exchange in EXCHANGES:

                timeframe_data = (
                    exchanges.get(
                        exchange,
                        {},
                    )
                )

                if not isinstance(
                    timeframe_data,
                    dict,
                ):

                    continue

                for payload in (
                    timeframe_data.values()
                ):

                    if not isinstance(
                        payload,
                        dict,
                    ):

                        continue

                    if payload.get(
                        "success",
                        False,
                    ):

                        status[
                            exchange
                        ][
                            "available"
                        ] = True

                        status[
                            exchange
                        ][
                            "timeframes_loaded"
                        ] += 1

                    else:

                        status[
                            exchange
                        ][
                            "errors"
                        ] += 1

                if status[
                    exchange
                ][
                    "available"
                ]:

                    status[
                        exchange
                    ][
                        "symbols"
                    ] += 1

        return status

    # =====================================================
    # BACKGROUND LOOP
    # =====================================================

    async def _loop(
        self,
    ) -> None:
        """Run scans in the background without blocking FastAPI startup."""
        while self._running:
            started = time.monotonic()
            try:
                result = await self.scan_once()
                if isinstance(result, dict) and result.get("success"):
                    asyncio.create_task(persist_scan_result(result))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._error_count += 1
                self._last_scan = {
                    "success": False,
                    "market": self.market,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "error": str(exc),
                    "last_successful": dict(self._last_successful_scan),
                }
            elapsed = time.monotonic() - started
            sleep_for = max(0.0, float(self.refresh_seconds) - elapsed)
            self._next_scan_at = time.monotonic() + sleep_for
            if sleep_for > 0:
                try:
                    await asyncio.sleep(sleep_for)
                except asyncio.CancelledError:
                    raise

    # =====================================================
    # START
    # =====================================================

    async def start(
        self,
    ) -> None:

        if self._running:

            return

        self._running = True

        # Do not block application startup on the first market scan.
        # The background loop performs the first scan immediately.
        self._task = asyncio.create_task(self._loop())

    # =====================================================
    # STOP
    # =====================================================

    async def stop(
        self,
    ) -> None:

        self._running = False

        self._next_scan_at = None

        task = self._task

        self._task = None

        if task is not None:

            task.cancel()

            try:

                await task

            except asyncio.CancelledError:

                pass

        try:

            await self.exchange_client.close()

        except Exception:

            pass

    # =====================================================
    # SNAPSHOT
    # =====================================================

    def snapshot(
        self,
    ) -> dict[str, Any]:

        next_scan_in_seconds = None

        if (
            self._next_scan_at
            is not None
            and self._running
        ):

            next_scan_in_seconds = max(
                0,
                int(
                    self._next_scan_at
                    - time.monotonic()
                ),
            )

        latest = (
            self._last_successful_scan
            if self._last_successful_scan
            else self._last_scan
        )

        return {
            "running":
                self._running,

            "market":
                self.market,

            "refresh_seconds":
                self.refresh_seconds,

            "auto_scan_interval":
                self.refresh_seconds,

            "scan_limit":
                self.scan_limit,

            "scan_count":
                self._scan_count,

            "error_count":
                self._error_count,

            "exchanges":
                list(
                    EXCHANGES
                ),

            "timeframes":
                list(
                    TIMEFRAMES
                ),

            "last_scan_at": (
                self._last_scan_at.isoformat()
                if self._last_scan_at
                else None
            ),

            "last_successful_scan_at": (
                self._last_successful_scan_at.isoformat()
                if self._last_successful_scan_at
                else None
            ),

            "next_scan_in_seconds":
                next_scan_in_seconds,

            "latest":
                dict(
                    latest
                ),
        }


# =========================================================
# SHARED INSTANCE
# =========================================================

auto_scanner = AutoScanner(
    market="futures",
    refresh_seconds=60,
)


# =========================================================
# EXPORTS
# =========================================================

__all__ = [
    "AutoScanner",
    "auto_scanner",
    "EXCHANGES",
    "TIMEFRAMES",
]
