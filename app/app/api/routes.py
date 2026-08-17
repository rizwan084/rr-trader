from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query

from app.services.scanner import MarketScanner
from app.services.signal_engine import SignalEngine


router = APIRouter(prefix="/api", tags=["RR Trader"])

scanner = MarketScanner()
signal_engine = SignalEngine()


@router.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "success": True,
        "app": "RR Trader",
        "status": "online",
    }


@router.get("/scan")
async def scan_market(
    market: str = Query(
        default="futures",
        pattern="^(futures|spot)$",
    ),
    limit: int = Query(
        default=10,
        ge=1,
        le=50,
    ),
) -> Dict[str, Any]:

    try:
        result = await scanner.scan(
            market=market,
            limit=limit,
        )

        return {
            "success": True,
            "market": market,
            "results": result,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Market scan failed: {exc}",
        ) from exc


@router.post("/analyze")
async def analyze_market(
    data: Dict[str, Any],
) -> Dict[str, Any]:

    if not data:
        raise HTTPException(
            status_code=400,
            detail="Market data is required",
        )

    market = str(
        data.get("market", "futures")
    ).lower()

    if market not in {"futures", "spot"}:
        raise HTTPException(
            status_code=400,
            detail="market must be futures or spot",
        )

    timeframe = str(
        data.get("timeframe", "15m")
    )

    try:
        result = signal_engine.analyze(
            data,
            market=market,
            timeframe=timeframe,
        )

        return {
            "success": True,
            "data": result,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Signal analysis failed: {exc}",
        ) from exc
