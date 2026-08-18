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


class AutoScanner:
    """
    Continuous RR Trader scanner.

    - Full Binance market screening
    - Top candidates
    - Deep 15m / 1H / 4H analysis
    - Automatic refresh
    - One failed symbol does not break the scan
    - Latest successful results remain available
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
            ).lower().strip()
        )

        # Always analyze at least 6 candidates.
        self.scan_limit = max(
            1,
            int(
                scan_limit
                if scan_limit is not None
                else settings.deep_analysis_limit
            ),
        )

        # Minimum automatic scan interval = 60 seconds.
        self.refresh_seconds = max(
            60,
            int(
                refresh_seconds
                if refresh_seconds is not None
                else settings.auto_scan_interval
            ),
        )

        self.scanner = MarketScanner(
            market_data_service
        )

        self._task: (
            asyncio.Task[None]
            | None
        ) = None

        self._running = False

        self._scan_lock = asyncio.Lock()

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

    # =====================================================
    # SINGLE SCAN
    # =====================================================

    async def scan_once(
        self,
    ) -> dict[str, Any]:

        async with self._scan_lock:

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

                # -------------------------------------------------
                # Stage 1
                # -------------------------------------------------

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
                        "Scanner returned invalid universe data."
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

                # -------------------------------------------------
                # Stage 2
                # -------------------------------------------------

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

                    symbol = str(
                        candidate.get(
                            "symbol",
                            "",
                        )
                    ).upper().strip()

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

                        return {
                            "success": True,
                            "symbol":
                                symbol,
                            "candidate":
                                candidate,
                            "analysis":
                                analysis,
                        }

                    except Exception as exc:

                        # One symbol failure must not
                        # terminate the complete scan.
                        return {
                            "success": False,
                            "symbol":
                                symbol,
                            "candidate":
                                candidate,
                            "error":
                                str(exc),
                        }

                # -------------------------------------------------
                # Concurrent analysis
                # -------------------------------------------------

                results = await asyncio.gather(
                    *[
                        analyze_candidate(
                            candidate
                        )
                        for candidate
                        in candidates
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

                # -------------------------------------------------
                # Ranking
                # -------------------------------------------------

                analyses.sort(
                    key=lambda item: (
                        float(
                            item.get(
                                "confidence",
                                0,
                            )
                            or 0
                        ),
                        float(
                            item.get(
                                "risk_reward",
                                0,
                            )
                            or 0
                        ),
                    ),
                    reverse=True,
                )

                publishable = [
                    item
                    for item
                    in analyses
                    if item.get(
                        "publishable",
                        False,
                    )
                ]

                publishable.sort(
                    key=lambda item: (
                        float(
                            item.get(
                                "confidence",
                                0,
                            )
                            or 0
                        ),
                        float(
                            item.get(
                                "risk_reward",
                                0,
                            )
                            or 0
                        ),
                    ),
                    reverse=True,
                )

                elapsed = (
                    time.monotonic()
                    - started_at
                )

                result = {
                    "success":
                        True,

                    "market":
                        self.market,

                    "universe_mode":
                        "FULL_MARKET",

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
                            candidates
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

                    "core_timeframes":
                        [
                            "15m",
                            "1h",
                            "4h",
                        ],

                    "candidates":
                        candidates,

                    "analyses":
                        analyses,

                    "publishable_signals":
                        publishable,

                    "errors":
                        failures,
                }

                self._last_scan = result

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

                    # Preserve last good results.
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
    # BACKGROUND LOOP
    # =====================================================

    async def _loop(
        self,
    ) -> None:

        while self._running:

            started = (
                time.monotonic()
            )

            try:

                await self.scan_once()

            except (
                asyncio.CancelledError,
            ):

                raise

            except Exception as exc:

                self._error_count += 1

                self._last_scan = {
                    "success":
                        False,

                    "market":
                        self.market,

                    "timestamp":
                        datetime.now(
                            timezone.utc
                        ).isoformat(),

                    "error":
                        str(exc),

                    "last_successful":
                        dict(
                            self._last_successful_scan
                        ),
                }

            elapsed = (
                time.monotonic()
                - started
            )

            sleep_for = max(
                0.0,
                float(
                    self.refresh_seconds
                )
                - elapsed,
            )

            self._next_scan_at = (
                time.monotonic()
                + sleep_for
            )

            if sleep_for > 0:

                try:

                    await asyncio.sleep(
                        sleep_for
                    )

                except (
                    asyncio.CancelledError,
                ):

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

        # First scan immediately.
        await self.scan_once()

        # Then every 60 seconds.
        self._task = asyncio.create_task(
            self._loop()
        )

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


__all__ = [
    "AutoScanner",
    "auto_scanner",
]
