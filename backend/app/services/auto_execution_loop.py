from __future__ import annotations

import asyncio
from typing import Any

from app.core.config import settings
from app.services.auto_scanner import auto_scanner
from app.services.trade_orchestrator import trade_orchestrator


class AutoExecutionLoop:
    """Watches the existing scanner without changing its analysis pipeline.

    This is intentionally a separate loop so the existing RR Trader scanner
    remains untouched. When live trading is disabled, this loop is inert.
    """

    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self.interval = max(10, int(settings.auto_scan_interval))
        self.last_result: dict[str, Any] = {"status": "IDLE"}

    async def _run_once(self) -> None:
        if not (settings.live_trading_enabled and settings.trading_mode == "live"):
            self.last_result = {
                "status": "ARMED_BUT_DISABLED",
                "message": "Automatic execution is installed but live trading is disabled.",
            }
            return

        snapshot = auto_scanner.snapshot()
        if not isinstance(snapshot, dict) or not snapshot.get("success", False):
            self.last_result = {"status": "NO_SCAN_DATA"}
            return

        candidates = snapshot.get("publishable_signals") or []
        if not isinstance(candidates, list) or not candidates:
            self.last_result = {"status": "NO_APPROVED_SIGNAL"}
            return

        # The scanner already ranks publishable candidates. The orchestrator
        # applies the second, stricter pro-risk gate before any order is sent.
        best = candidates[0]
        if not isinstance(best, dict):
            self.last_result = {"status": "INVALID_SIGNAL"}
            return

        result = await trade_orchestrator.execute(best)
        self.last_result = result

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_result = {"status": "ERROR", "error": str(exc)}
            await asyncio.sleep(self.interval)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            finally:
                self._task = None

    def status(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "interval_seconds": self.interval,
            "last_result": self.last_result,
            "live_enabled": settings.live_trading_enabled and settings.trading_mode == "live",
        }


auto_execution_loop = AutoExecutionLoop()
