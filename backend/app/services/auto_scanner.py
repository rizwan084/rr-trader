from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.services.market_data import market_data_service
from app.services.market_scanner import MarketScanner
from app.services.master_analysis import master_analysis_engine


class AutoScanner:
    """
    RR Trader continuous market scanner.

    Responsibilities:
    - Scan Binance market universe
    - Rank candidates
    - Deep-analyze top candidates
    - Keep latest scanner snapshot
    - Refresh continuously

    This service does NOT publish posts.
    """

    def __init__(
        self,
        market: str = "futures",
        scan_limit: int = 10,
        refresh_seconds: int | None = None,
    ) -> None:

        self.market = market

        self.scan_limit = max(
            1,
            int(scan_limit),
        )

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

        self._task: asyncio.Task | None = None

        self._running = False

        self._lock = asyncio.Lock()

        self._last_scan: dict[str, Any] = {}

        self._last_scan_at: datetime | None = None

        self._next_scan_at: float | None = None

    # =====================================================
    # SINGLE SCAN
    # =====================================================

    async def scan_once(
        self,
    ) -> dict[str, Any]:

        async with self._lock:

            universe = await self.scanner.top_candidates(
                market=self.market,
                limit=self.scan_limit,
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

            async def analyze_candidate(
                candidate: dict[str, Any],
            ) -> dict[str, Any]:

                symbol = str(
                    candidate.get(
                        "symbol",
                        "",
                    )
                ).upper().strip()

                if not symbol:
                    return {
                        "success": False,
                        "error": "Missing symbol.",
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
                        "candidate": candidate,
                        "analysis": analysis,
                    }

                except Exception as exc:

                    return {
                        "success": False,
                        "candidate": candidate,
                        "error": str(exc),
                    }

            results = await asyncio.gather(
                *[
                    analyze_candidate(
                        candidate
                    )
                    for candidate in candidates
                ],
                return_exceptions=False,
            )

            analyses: list[
                dict[str, Any]
            ] = []

            for result in results:

                if not result.get(
                    "success",
                    False,
                ):
                    continue

                analysis = result.get(
                    "analysis"
                )

                if not isinstance(
                    analysis,
                    dict,
                ):
                    continue

                analyses.append(
                    analysis
                )

            analyses.sort(
                key=lambda item: float(
                    item.get(
                        "confidence",
                        0,
                    )
                    or 0
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

            self._last_scan_at = datetime.now(
                timezone.utc
            )

            self._last_scan = {
                "success": True,
                "market": self.market,
                "timestamp": (
                    self._last_scan_at.isoformat()
                ),
                "scanned_universe": (
                    universe.get(
                        "eligible_markets",
                        0,
                    )
                ),
                "candidate_count": len(
                    candidates
                ),
                "deep_analyzed": len(
                    analyses
                ),
                "publishable_count": len(
                    publishable
                ),
                "candidates": candidates,
                "analyses": analyses,
                "publishable_signals": publishable,
            }

            return dict(
                self._last_scan
            )

    # =====================================================
    # BACKGROUND LOOP
    # =====================================================

    async def _loop(
        self,
    ) -> None:

        while self._running:

            started = time.monotonic()

            try:

                await self.scan_once()

            except Exception as exc:

                self._last_scan = {
                    "success": False,
                    "market": self.market,
                    "error": str(exc),
                    "timestamp": datetime.now(
                        timezone.utc
                    ).isoformat(),
                }

            elapsed = (
                time.monotonic()
                - started
            )

            sleep_for = max(
                0.0,
                self.refresh_seconds
                - elapsed,
            )

            self._next_scan_at = (
                time.monotonic()
                + sleep_for
            )

            if sleep_for > 0:

                await asyncio.sleep(
                    sleep_for
                )

    # =====================================================
    # START
    # =====================================================

    async def start(
        self,
    ) -> None:

        if self._running:
            return

        self._running = True

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

        if self._task is not None:

            self._task.cancel()

            try:
                await self._task

            except asyncio.CancelledError:
                pass

            self._task = None

    # =====================================================
    # SNAPSHOT
    # =====================================================

    def snapshot(
        self,
    ) -> dict[str, Any]:

        next_scan_seconds = None

        if self._next_scan_at is not None:

            next_scan_seconds = max(
                0,
                int(
                    self._next_scan_at
                    - time.monotonic()
                )
            )

        return {
            "running": self._running,
            "market": self.market,
            "refresh_seconds": self.refresh_seconds,
            "scan_limit": self.scan_limit,
            "last_scan_at": (
                self._last_scan_at.isoformat()
                if self._last_scan_at
                else None
            ),
            "next_scan_in_seconds":
                next_scan_seconds,
            "latest": dict(
                self._last_scan
            ),
        }


auto_scanner = AutoScanner()


__all__ = [
    "AutoScanner",
    "auto_scanner",
]
