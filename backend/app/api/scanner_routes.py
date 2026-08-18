from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.services.auto_scanner import auto_scanner


router = APIRouter()


# =========================================================
# SCANNER STATUS
# =========================================================

@router.get("/scanner/status")
async def scanner_status() -> dict[str, Any]:

    snapshot = (
        auto_scanner.snapshot()
    )

    latest = snapshot.get(
        "latest",
        {},
    )

    if not isinstance(
        latest,
        dict,
    ):
        latest = {}

    return {
        "success": True,

        "running":
            bool(
                snapshot.get(
                    "running",
                    False,
                )
            ),

        "market":
            snapshot.get(
                "market",
                "futures",
            ),

        "refresh_seconds":
            snapshot.get(
                "refresh_seconds",
                60,
            ),

        "scan_count":
            snapshot.get(
                "scan_count",
                0,
            ),

        "error_count":
            snapshot.get(
                "error_count",
                0,
            ),

        "last_scan_at":
            snapshot.get(
                "last_scan_at"
            ),

        "next_scan_in_seconds":
            snapshot.get(
                "next_scan_in_seconds"
            ),

        "latest":
            latest,
    }


# =========================================================
# SCANNER RESULTS
# =========================================================

@router.get("/scanner/results")
async def scanner_results(
    limit: int = Query(
        default=10,
        ge=1,
        le=50,
    ),
) -> dict[str, Any]:

    snapshot = (
        auto_scanner.snapshot()
    )

    latest = snapshot.get(
        "latest",
        {},
    )

    if not isinstance(
        latest,
        dict,
    ):
        latest = {}

    analyses = latest.get(
        "analyses",
        [],
    )

    if not isinstance(
        analyses,
        list,
    ):
        analyses = []

    # -----------------------------------------------------
    # Sort by confidence
    # -----------------------------------------------------

    analyses = sorted(
        analyses,
        key=lambda item: float(
            item.get(
                "confidence",
                0,
            )
            or 0
        ),
        reverse=True,
    )

    return {
        "success": True,

        "running":
            snapshot.get(
                "running",
                False,
            ),

        "market":
            snapshot.get(
                "market",
                "futures",
            ),

        "last_scan_at":
            snapshot.get(
                "last_scan_at"
            ),

        "next_scan_in_seconds":
            snapshot.get(
                "next_scan_in_seconds"
            ),

        "scanned_universe":
            latest.get(
                "scanned_universe",
                0,
            ),

        "candidate_count":
            latest.get(
                "candidate_count",
                0,
            ),

        "deep_analyzed":
            latest.get(
                "deep_analyzed",
                0,
            ),

        "publishable_count":
            latest.get(
                "publishable_count",
                0,
            ),

        "failed_analysis":
            latest.get(
                "failed_analysis",
                0,
            ),

        "core_timeframes":
            latest.get(
                "core_timeframes",
                [
                    "15m",
                    "1h",
                    "4h",
                ],
            ),

        "results":
            analyses[:limit],
    }


# =========================================================
# TOP QUALIFIED
# =========================================================

@router.get("/scanner/top")
async def scanner_top(
    limit: int = Query(
        default=5,
        ge=1,
        le=20,
    ),
) -> dict[str, Any]:

    snapshot = (
        auto_scanner.snapshot()
    )

    latest = snapshot.get(
        "latest",
        {},
    )

    if not isinstance(
        latest,
        dict,
    ):
        latest = {}

    analyses = latest.get(
        "analyses",
        [],
    )

    if not isinstance(
        analyses,
        list,
    ):
        analyses = []

    qualified = [
        item
        for item in analyses
        if bool(
            item.get(
                "publishable",
                False,
            )
        )
    ]

    qualified.sort(
        key=lambda item: float(
            item.get(
                "confidence",
                0,
            )
            or 0
        ),
        reverse=True,
    )

    return {
        "success": True,

        "market":
            snapshot.get(
                "market",
                "futures",
            ),

        "count":
            len(
                qualified[:limit]
            ),

        "opportunities":
            qualified[:limit],
    }


# =========================================================
# SCAN NOW
# =========================================================

@router.post("/scanner/scan-now")
async def scanner_scan_now() -> dict[str, Any]:

    return await auto_scanner.scan_once()


# =========================================================
# BEST CURRENT SETUP
# =========================================================

@router.get("/scanner/best")
async def scanner_best() -> dict[str, Any]:

    snapshot = (
        auto_scanner.snapshot()
    )

    latest = snapshot.get(
        "latest",
        {},
    )

    if not isinstance(
        latest,
        dict,
    ):
        latest = {}

    analyses = latest.get(
        "analyses",
        [],
    )

    if not isinstance(
        analyses,
        list,
    ):
        analyses = []

    if not analyses:

        return {
            "success": True,
            "found": False,
            "best": None,
            "market":
                snapshot.get(
                    "market",
                    "futures",
                ),
            "last_scan_at":
                snapshot.get(
                    "last_scan_at"
                ),
            "next_scan_in_seconds":
                snapshot.get(
                    "next_scan_in_seconds"
                ),
        }

    analyses = sorted(
        analyses,
        key=lambda item: float(
            item.get(
                "confidence",
                0,
            )
            or 0
        ),
        reverse=True,
    )

    best = analyses[0]

    return {
        "success": True,
        "found": True,
        "best": best,

        "market":
            snapshot.get(
                "market",
                "futures",
            ),

        "last_scan_at":
            snapshot.get(
                "last_scan_at"
            ),

        "next_scan_in_seconds":
            snapshot.get(
                "next_scan_in_seconds"
            ),
    }


__all__ = [
    "router",
]
