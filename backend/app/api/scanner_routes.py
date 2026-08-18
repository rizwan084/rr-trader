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

    return {
        "success": True,
        **auto_scanner.snapshot(),
    }


# =========================================================
# CURRENT RESULTS
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

    analyses = latest.get(
        "analyses",
        [],
    )

    if not isinstance(
        analyses,
        list,
    ):
        analyses = []

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
        "running": snapshot.get(
            "running",
            False,
        ),
        "market": snapshot.get(
            "market",
            "futures",
        ),
        "last_scan_at": snapshot.get(
            "last_scan_at"
        ),
        "next_scan_in_seconds": (
            snapshot.get(
                "next_scan_in_seconds"
            )
        ),
        "scanned_universe": (
            latest.get(
                "scanned_universe",
                0,
            )
        ),
        "candidate_count": (
            latest.get(
                "candidate_count",
                0,
            )
        ),
        "deep_analyzed": (
            latest.get(
                "deep_analyzed",
                0,
            )
        ),
        "publishable_count": (
            latest.get(
                "publishable_count",
                0,
            )
        ),
        "results": analyses[:limit],
    }


# =========================================================
# TOP OPPORTUNITIES
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
        if isinstance(
            item,
            dict,
        )
        and item.get(
            "publishable",
            False,
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
        "count": min(
            len(qualified),
            limit,
        ),
        "opportunities": (
            qualified[:limit]
        ),
    }


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
        if isinstance(
            item,
            dict,
        )
        and item.get(
            "publishable",
            False,
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

    best = (
        qualified[0]
        if qualified
        else None
    )

    return {
        "success": True,
        "found": best is not None,
        "best": best,
        "market": snapshot.get(
            "market",
            "futures",
        ),
        "last_scan_at": snapshot.get(
            "last_scan_at"
        ),
        "next_scan_in_seconds": (
            snapshot.get(
                "next_scan_in_seconds"
            )
        ),
    }


# =========================================================
# ALL RESULTS INCLUDING REJECTED
# =========================================================

@router.get("/scanner/all")
async def scanner_all(
    limit: int = Query(
        default=20,
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

    analyses = latest.get(
        "analyses",
        [],
    )

    if not isinstance(
        analyses,
        list,
    ):
        analyses = []

    ranked = sorted(
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
        "market": snapshot.get(
            "market",
            "futures",
        ),
        "running": snapshot.get(
            "running",
            False,
        ),
        "last_scan_at": snapshot.get(
            "last_scan_at"
        ),
        "next_scan_in_seconds": (
            snapshot.get(
                "next_scan_in_seconds"
            )
        ),
        "count": min(
            len(ranked),
            limit,
        ),
        "results": (
            ranked[:limit]
        ),
    }


# =========================================================
# MANUAL SCAN
# =========================================================

@router.post("/scanner/scan-now")
async def scanner_scan_now() -> dict[str, Any]:

    result = await (
        auto_scanner.scan_once()
    )

    return result


__all__ = [
    "router",
]
