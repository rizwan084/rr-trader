from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from app.core.config import settings


JobCallback = Callable[[], Awaitable[Any]]


class Scheduler:
    """
    RR Trader background scheduler foundation.

    Main responsibilities:
    - Run the automatic scanner on a fixed interval.
    - Prevent overlapping scan jobs.
    - Expose scheduler status.
    - Gracefully start and stop with FastAPI.

    The scheduler itself does not decide LONG/SHORT.
    The scanner and analysis engines remain responsible
    for market intelligence.
    """

    def __init__(
        self,
        interval_seconds: int | None = None,
    ) -> None:

        self.interval_seconds = max(
            1,
            int(
                interval_seconds
                if interval_seconds is not None
                else settings.auto_scan_interval
            ),
        )

        self.running = False

        self._task: Optional[
            asyncio.Task
        ] = None

        self._job: Optional[
            JobCallback
        ] = None

        self._job_lock = asyncio.Lock()

        self.last_run_at: str | None = None
        self.last_success_at: str | None = None
        self.last_error: str | None = None
        self.run_count = 0
        self.success_count = 0
        self.error_count = 0
        self.next_run_in_seconds = (
            self.interval_seconds
        )

    # =====================================================
    # REGISTER JOB
    # =====================================================

    def register(
        self,
        job: JobCallback,
    ) -> None:

        self._job = job

    # =====================================================
    # RUN ONE JOB SAFELY
    # =====================================================

    async def run_once(
        self,
    ) -> Any:

        if self._job is None:

            raise RuntimeError(
                "No scheduler job has been registered."
            )

        async with self._job_lock:

            self.run_count += 1

            self.last_run_at = (
                datetime.now(
                    timezone.utc
                ).isoformat()
            )

            try:

                result = await self._job()

                self.success_count += 1

                self.last_success_at = (
                    datetime.now(
                        timezone.utc
                    ).isoformat()
                )

                self.last_error = None

                return result

            except Exception as exc:

                self.error_count += 1

                self.last_error = str(
                    exc
                )

                raise

    # =====================================================
    # BACKGROUND LOOP
    # =====================================================

    async def _loop(
        self,
    ) -> None:

        while self.running:

            self.next_run_in_seconds = (
                self.interval_seconds
            )

            for remaining in range(
                self.interval_seconds,
                0,
                -1,
            ):

                if not self.running:
                    break

                self.next_run_in_seconds = (
                    remaining
                )

                await asyncio.sleep(
                    1
                )

            if not self.running:
                break

            try:
                await self.run_once()

            except asyncio.CancelledError:
                raise

            except Exception:
                # The scheduler remains alive even
                # when an individual job fails.
                continue

    # =====================================================
    # START
    # =====================================================

    async def start(
        self,
        job: JobCallback | None = None,
    ) -> dict[str, Any]:

        if job is not None:
            self.register(job)

        if self.running:

            return self.status()

        if self._job is None:

            raise RuntimeError(
                "Cannot start scheduler without a job."
            )

        self.running = True

        self._task = asyncio.create_task(
            self._loop()
        )

        return self.status()

    # =====================================================
    # STOP
    # =====================================================

    async def stop(
        self,
    ) -> dict[str, Any]:

        self.running = False

        task = self._task

        self._task = None

        if task is not None:

            task.cancel()

            try:
                await task

            except asyncio.CancelledError:
                pass

        self.next_run_in_seconds = (
            self.interval_seconds
        )

        return self.status()

    # =====================================================
    # STATUS
    # =====================================================

    def status(
        self,
    ) -> dict[str, Any]:

        return {
            "running": self.running,
            "interval_seconds": (
                self.interval_seconds
            ),
            "next_run_in_seconds": (
                self.next_run_in_seconds
                if self.running
                else self.interval_seconds
            ),
            "last_run_at": (
                self.last_run_at
            ),
            "last_success_at": (
                self.last_success_at
            ),
            "last_error": (
                self.last_error
            ),
            "run_count": self.run_count,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "job_registered": (
                self._job is not None
            ),
        }


scheduler = Scheduler()


__all__ = [
    "Scheduler",
    "scheduler",
]
