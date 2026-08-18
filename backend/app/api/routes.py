from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.core.config import settings


router = APIRouter()


# =========================================================
# HEALTH
# =========================================================

@router.get("/health")
async def health() -> dict[str, Any]:
    return {
        "success": True,
        "status": "healthy",
        "service": "rr-trader",
        "version": settings.app_version,
    }


# =========================================================
# MARKETS
# =========================================================

@router.get("/markets")
async def markets() -> dict[str, Any]:
    return {
        "success": True,
        "markets": [
            {
                "id": "futures",
                "name": "Binance Futures",
                "enabled": True,
            },
            {
                "id": "spot",
                "name": "Binance Spot",
                "enabled": True,
            },
        ],
    }


# =========================================================
# SEARCH
# =========================================================

@router.get("/search")
async def search(
    q: str = Query(
        default="",
        max_length=30,
    ),
    market: str = Query(
        default="futures",
    ),
) -> dict[str, Any]:

    clean = (
        str(q)
        .upper()
        .replace(
            "USDT",
            "",
        )
        .strip()
    )

    if not clean:
        return {
            "success": True,
            "market": market.lower(),
            "coins": [],
        }

    symbol = f"{clean}USDT"

    return {
        "success": True,
        "market": market.lower(),
        "coins": [
            {
                "symbol": symbol,
                "coin": clean,
            }
        ],
    }


# =========================================================
# ANALYZE
# =========================================================

@router.get("/analyze")
async def analyze(
    symbol: str,
    market: str = Query(
        default="futures",
    ),
) -> dict[str, Any]:

    return {
        "success": True,
        "symbol": symbol.upper(),
        "market": market.lower(),
        "status": (
            "analysis_engine_pending_phase_2"
        ),
        "core_timeframes": list(
            settings.core_timeframes
        ),
    }


# =========================================================
# SCAN
# =========================================================

@router.get("/scan")
async def scan(
    market: str = Query(
        default="futures",
    ),
) -> dict[str, Any]:

    return {
        "success": True,
        "market": market.lower(),
        "status": (
            "scanner_pending_phase_2"
        ),
        "core_timeframes": list(
            settings.core_timeframes
        ),
        "deep_analysis_limit": (
            settings.deep_analysis_limit
        ),
    }


# =========================================================
# SIGNALS
# =========================================================

@router.get("/signals")
async def signals() -> dict[str, Any]:

    return {
        "success": True,
        "signals": [],
        "status": (
            "signal_engine_pending_phase_3"
        ),
    }
