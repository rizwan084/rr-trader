from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query

from app.app.services.trade_engine import (
    default_trade_engine,
)


router = APIRouter()


# =========================================================
# TRADE ENGINE STATUS
# =========================================================

@router.get("/trade/status")
async def trade_status() -> Dict[str, Any]:

    return {
        "success": True,
        "engine": (
            default_trade_engine.get_status()
        ),
        "config": (
            default_trade_engine.get_config()
        ),
    }


# =========================================================
# TRADE ENGINE CONFIG
# =========================================================

@router.get("/trade/config")
async def trade_config() -> Dict[str, Any]:

    return {
        "success": True,
        "config": (
            default_trade_engine.get_config()
        ),
    }


# =========================================================
# EVALUATE SIGNAL
# =========================================================

@router.post("/trade/evaluate")
async def evaluate_trade(
    signal: Dict[str, Any],
) -> Dict[str, Any]:

    try:

        result = (
            default_trade_engine
            .evaluate_trade(
                signal
            )
        )

        return {
            "success": True,
            "result": result,
        }

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=(
                f"Trade evaluation error: "
                f"{str(exc)}"
            ),
        ) from exc


# =========================================================
# OPEN PAPER TRADE
# =========================================================

@router.post("/trade/paper/open")
async def open_paper_trade(
    signal: Dict[str, Any],
) -> Dict[str, Any]:

    try:

        result = (
            default_trade_engine
            .open_paper_trade(
                signal
            )
        )

        return result

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=(
                f"Paper trade error: "
                f"{str(exc)}"
            ),
        ) from exc


# =========================================================
# OPEN POSITIONS
# =========================================================

@router.get("/trade/positions")
async def trade_positions() -> Dict[str, Any]:

    positions = (
        default_trade_engine
        .get_open_positions()
    )

    return {
        "success": True,
        "count": len(
            positions
        ),
        "positions": positions,
    }


# =========================================================
# CLOSED TRADE HISTORY
# =========================================================

@router.get("/trade/history")
async def trade_history(
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
    ),
) -> Dict[str, Any]:

    history = (
        default_trade_engine
        .get_closed_trades()
    )

    return {
        "success": True,
        "count": len(
            history
        ),
        "trades": history[
            -limit:
        ],
    }


# =========================================================
# UPDATE PAPER POSITION
# =========================================================

@router.post("/trade/positions/update")
async def update_position(
    position_id: str,
    current_price: float,
) -> Dict[str, Any]:

    try:

        result = (
            default_trade_engine
            .update_position(
                position_id=position_id,
                current_price=current_price,
            )
        )

        return result

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=(
                f"Position update error: "
                f"{str(exc)}"
            ),
        ) from exc


# =========================================================
# CLOSE PAPER POSITION
# =========================================================

@router.post("/trade/positions/close")
async def close_position(
    position_id: str,
    exit_price: float,
    reason: str = "MANUAL",
) -> Dict[str, Any]:

    try:

        result = (
            default_trade_engine
            .close_position(
                position_id=position_id,
                exit_price=exit_price,
                reason=reason,
            )
        )

        return result

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=(
                f"Position close error: "
                f"{str(exc)}"
            ),
        ) from exc


# =========================================================
# RESET DAILY RISK
# =========================================================

@router.post("/trade/reset-daily")
async def reset_daily() -> Dict[str, Any]:

    return (
        default_trade_engine
        .reset_daily_stats()
    )


# =========================================================
# EXPORT
# =========================================================

__all__ = [
    "router",
]
