from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings
from app.services.auto_scanner import auto_scanner

router = APIRouter()
MIN_RISK_REWARD = 0.0
MIN_CONFIDENCE = 85.0


def _bridge_url() -> str:
    return os.getenv("MT5_BRIDGE_URL", "").strip().rstrip("/")


def _qualified(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            confidence = float(item.get("confidence", 0) or 0)
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence < MIN_CONFIDENCE:
            continue
        direction = str(item.get("direction", "NEUTRAL")).upper()
        if direction not in {"LONG", "SHORT"}:
            continue
        if item.get("publishable") is not True:
            continue
        out.append(item)
    out.sort(key=lambda x: float(x.get("confidence", 0) or 0), reverse=True)
    return out


@router.get("/dashboard/overview")
async def dashboard_overview() -> dict[str, Any]:
    snapshot = auto_scanner.snapshot()
    latest = snapshot.get("latest", {}) if isinstance(snapshot, dict) else {}
    qualified = _qualified(latest.get("analyses", []) if isinstance(latest, dict) else [])
    return {
        "success": True,
        "section": "overview",
        "markets": ["crypto", "forex"],
        "crypto": {"spot": True, "futures": True, "timeframes": ["15m", "1h", "4h"]},
        "forex": {"primary": "XAUUSD", "timeframes": ["1m", "3m", "5m", "15m"]},
        "risk": {"minimum_confidence": MIN_CONFIDENCE, "live_execution": False},
        "confidence": {"engine_version": "core-7", "rules": ["EMA trend", "RSI", "Momentum", "Volume", "Market Structure", "MTF 15m/1h/4h", "Support/Resistance"]},
        "scanner": {"running": bool(snapshot.get("running", False)), "market": snapshot.get("market", "futures"), "last_scan_at": snapshot.get("last_scan_at"), "next_scan_in_seconds": snapshot.get("next_scan_in_seconds"), "scanned_universe": latest.get("scanned_universe", 0) if isinstance(latest, dict) else 0, "deep_analyzed": latest.get("deep_analyzed", 0) if isinstance(latest, dict) else 0, "qualified_85_plus": len(qualified)},
        "opportunities": qualified,
    }


@router.get("/dashboard/opportunities")
async def dashboard_opportunities(limit: int = Query(default=50, ge=1, le=100)) -> dict[str, Any]:
    snapshot = auto_scanner.snapshot()
    latest = snapshot.get("latest", {}) if isinstance(snapshot, dict) else {}
    qualified = _qualified(latest.get("analyses", []) if isinstance(latest, dict) else [])
    return {"success": True, "section": "trade_opportunities", "status": "live_scanner", "minimum_confidence": MIN_CONFIDENCE, "scanned_universe": latest.get("scanned_universe", 0) if isinstance(latest, dict) else 0, "deep_analyzed": latest.get("deep_analyzed", 0) if isinstance(latest, dict) else 0, "count": len(qualified[:limit]), "opportunities": qualified[:limit]}


@router.get("/dashboard/signals")
async def dashboard_signals(limit: int = Query(default=50, ge=1, le=100)) -> dict[str, Any]:
    snapshot = auto_scanner.snapshot()
    latest = snapshot.get("latest", {}) if isinstance(snapshot, dict) else {}
    qualified = _qualified(latest.get("analyses", []) if isinstance(latest, dict) else [])
    return {"success": True, "section": "signals", "status": "live_scanner", "confidence_engine": "core-7", "rules": ["EMA trend", "RSI", "Momentum", "Volume", "Market Structure", "MTF 15m/1h/4h", "Support/Resistance"], "minimum_confidence": MIN_CONFIDENCE, "minimum_rr": MIN_RISK_REWARD, "signals": qualified[:limit]}


@router.get("/dashboard/ai")
async def dashboard_ai() -> dict[str, Any]:
    return {"success": True, "section": "ai_assistant", "status": "ai_dashboard_ready"}


@router.get("/dashboard/charts")
async def dashboard_charts() -> dict[str, Any]:
    return {"success": True, "section": "charts", "crypto_timeframes": ["15m", "1h", "4h"], "forex_timeframes": ["1m", "3m", "5m", "15m"]}


@router.get("/dashboard/paper-trading")
async def dashboard_paper_trading() -> dict[str, Any]:
    return {"success": True, "section": "paper_trading", "mode": "paper", "live_trading": False}


@router.get("/dashboard/analytics")
async def dashboard_analytics() -> dict[str, Any]:
    return {"success": True, "section": "history_analytics", "statistics": {"total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "total_pnl_percent": 0.0}}


@router.get("/dashboard/settings")
async def dashboard_settings() -> dict[str, Any]:
    return {"success": True, "section": "settings", "minimum_rr": MIN_RISK_REWARD, "minimum_confidence": MIN_CONFIDENCE, "risk_per_trade_percent": 1.0, "confidence_engine": "5.0.0", "advanced_rules": "25-50", "deep_analysis_limit": settings.deep_analysis_limit}


@router.get("/dashboard/forex/status")
async def forex_status() -> dict[str, Any]:
    bridge = _bridge_url(); connected = False; message = "Configure MT5_BRIDGE_URL on a secure Windows VPS/MT5 bridge."
    if bridge:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{bridge}/health")
                connected = response.is_success; message = "MT5 bridge online." if connected else f"MT5 bridge returned HTTP {response.status_code}."
        except Exception as exc:
            message = f"MT5 bridge unavailable: {type(exc).__name__}."
    return {"success": True, "mt5_bridge": {"configured": bool(bridge), "connected": connected, "message": message}, "binance": {"configured": bool(os.getenv("BINANCE_API_KEY") and os.getenv("BINANCE_API_SECRET"))}, "gold": {"symbol": "XAUUSD", "priority": True, "timeframes": {"1m": "priority", "3m": "priority", "5m": "priority", "15m": "priority"}}}


@router.get("/dashboard/forex/quote")
async def forex_quote(symbol: str = Query("XAUUSD")) -> dict[str, Any]:
    bridge = _bridge_url()
    if not bridge: return {"success": False, "connected": False, "symbol": symbol.upper(), "error": "MT5_BRIDGE_URL is not configured."}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(f"{bridge}/quote", params={"symbol": symbol.upper()}); response.raise_for_status(); return {"success": True, "connected": True, "data": response.json()}
    except Exception as exc: raise HTTPException(status_code=503, detail=f"MT5 quote unavailable: {type(exc).__name__}") from exc


@router.get("/dashboard/forex/candles")
async def forex_candles(symbol: str = Query("XAUUSD"), timeframe: str = Query("1m"), limit: int = Query(200, ge=20, le=1000)) -> dict[str, Any]:
    if timeframe not in {"1m", "3m", "5m", "15m"}: raise HTTPException(status_code=400, detail="Forex timeframe must be 1m, 3m, 5m or 15m.")
    bridge = _bridge_url()
    if not bridge: return {"success": False, "connected": False, "symbol": symbol.upper(), "timeframe": timeframe, "candles": [], "error": "MT5_BRIDGE_URL is not configured."}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{bridge}/candles", params={"symbol": symbol.upper(), "timeframe": timeframe, "limit": limit}); response.raise_for_status(); data = response.json(); return {"success": True, "connected": True, "symbol": symbol.upper(), "timeframe": timeframe, "candles": data.get("candles", data) if isinstance(data, dict) else data}
    except Exception as exc: raise HTTPException(status_code=503, detail=f"MT5 candles unavailable: {type(exc).__name__}") from exc


@router.get("/dashboard/forex/analyze")
async def forex_analyze(symbol: str = Query("XAUUSD")) -> dict[str, Any]:
    bridge = _bridge_url()
    if not bridge: return {"success": False, "connected": False, "symbol": symbol.upper(), "analysis": {"trend": "WAITING FOR MT5", "momentum": "WAITING FOR MT5", "liquidity": "WAITING FOR MT5", "confidence": 0.0}, "error": "MT5_BRIDGE_URL is not configured."}
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.get(f"{bridge}/analysis", params={"symbol": symbol.upper(), "timeframes": "1m,3m,5m,15m"}); response.raise_for_status(); data = response.json(); return {"success": True, "connected": True, "symbol": symbol.upper(), "analysis": data.get("analysis", data)}
    except Exception as exc: raise HTTPException(status_code=503, detail=f"MT5 analysis unavailable: {type(exc).__name__}") from exc
