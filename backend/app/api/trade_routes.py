from __future__ import annotations

from typing import Any

from fastapi import APIRouter


router = APIRouter()


# =========================================================
# TRADE ENGINE STATUS
# =========================================================

@router.get("/trade/status")
async def trade_status() -> dict[str, Any]:
    return {
        "success": True,
        "mode": "paper",
        "live_trading": False,
        "status": "trade_engine_pending_phase_4",
    }


# =========================================================
# OPEN POSITIONS
# =========================================================

@router.get("/trade/positions")
async def trade_positions() -> dict[str, Any]:
    return {
        "success": True,
        "count": 0,
        "positions": [],
    }


# =========================================================
# TRADE HISTORY
# =========================================================

@router.get("/trade/history")
async def trade_history() -> dict[str, Any]:
    return {
        "success": True,
        "count": 0,
        "trades": [],
    }


# =========================================================
# TRADE EVALUATION
# =========================================================

@router.post("/trade/evaluate")
async def evaluate_trade(
    signal: dict[str, Any],
) -> dict[str, Any]:
    return {
        "success": True,
        "decision": "NO_TRADE",
        "mode": "paper",
        "status": "trade_engine_pending_phase_4",
        "signal": signal,
    }


# =========================================================
# PAPER TRADE OPEN
# =========================================================

@router.post("/trade/paper/open")
async def open_paper_trade(
    signal: dict[str, Any],
) -> dict[str, Any]:
    return {
        "success": False,
        "mode": "paper",
        "status": "paper_trade_engine_pending_phase_4",
        "signal": signal,
    }


# =========================================================
# DAILY RISK RESET
# =========================================================

@router.post("/trade/reset-daily")
async def reset_daily() -> dict[str, Any]:
    return {
        "success": True,
        "status": "daily_risk_reset_pending_phase_4",
    }
