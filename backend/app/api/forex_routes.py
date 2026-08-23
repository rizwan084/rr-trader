from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from ..services.forex_engine import forex_engine

router = APIRouter(prefix="/api/forex", tags=["Forex & Gold"])


@router.get("/status")
async def status() -> dict[str, Any]:
    return {"success": True, "service": "RR Trader Forex & Gold", **forex_engine.status()}


@router.get("/symbols")
async def symbols() -> dict[str, Any]:
    return {
        "success": True,
        "primary": forex_engine.primary_symbol,
        "symbols": list(forex_engine.symbols),
        "timeframes": list(forex_engine.timeframes),
    }


@router.get("/analyze")
async def analyze(
    symbol: str = Query(default="XAUUSD", min_length=3, max_length=20),
    timeframe: str = Query(default="15m", min_length=2, max_length=8),
) -> dict[str, Any]:
    try:
        return {"success": True, "analysis": await forex_engine.analyze(symbol, timeframe)}
    except Exception as exc:
        return {"success": False, "market": "FOREX", "symbol": symbol.upper(), "error": str(exc)}


@router.get("/multi-timeframe")
async def multi_timeframe(
    symbol: str = Query(default="XAUUSD", min_length=3, max_length=20),
) -> dict[str, Any]:
    try:
        return await forex_engine.multi_timeframe(symbol)
    except Exception as exc:
        return {"success": False, "market": "FOREX", "symbol": symbol.upper(), "error": str(exc)}


@router.get("/watchlist")
async def watchlist() -> dict[str, Any]:
    try:
        return await forex_engine.watchlist()
    except Exception as exc:
        return {"success": False, "market": "FOREX", "error": str(exc)}


__all__ = ["router"]
