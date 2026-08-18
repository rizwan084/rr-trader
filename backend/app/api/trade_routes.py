from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.services.risk_engine import risk_engine
from app.services.trade_engine import (
    default_trade_engine,
)


router = APIRouter()


# =========================================================
# TRADE ENGINE STATUS
# =========================================================

@router.get("/trade/status")
async def trade_status() -> dict[str, Any]:

    return {
        "success": True,
        "engine": (
            default_trade_engine.get_status()
        ),
        "config": (
            default_trade_engine.get_config()
        ),
        "risk": (
            risk_engine.status()
        ),
    }


# =========================================================
# TRADE CONFIG
# =========================================================

@router.get("/trade/config")
async def trade_config() -> dict[str, Any]:

    return {
        "success": True,
        "trade_engine": (
            default_trade_engine.get_config()
        ),
        "risk_engine": (
            risk_engine.status()
        ),
    }


# =========================================================
# EVALUATE TRADE
# =========================================================

@router.post("/trade/evaluate")
async def evaluate_trade(
    signal: dict[str, Any],
) -> dict[str, Any]:

    if not isinstance(
        signal,
        dict,
    ):

        raise HTTPException(
            status_code=400,
            detail="Signal must be an object.",
        )

    # -----------------------------------------------------
    # Trade-level deterministic gate
    # -----------------------------------------------------

    trade_evaluation = (
        default_trade_engine.evaluate_trade(
            signal
        )
    )

    # -----------------------------------------------------
    # Risk-level gate
    # -----------------------------------------------------

    account_balance = float(
        signal.get(
            "account_balance",
            0,
        )
        or 0
    )

    entry = float(
        signal.get(
            "entry",
            0,
        )
        or 0
    )

    stop_loss = float(
        signal.get(
            "stop_loss",
            0,
        )
        or 0
    )

    current_open_positions = int(
        signal.get(
            "current_open_positions",
            0,
        )
        or 0
    )

    current_exposure = float(
        signal.get(
            "current_exposure",
            0,
        )
        or 0
    )

    new_exposure = float(
        signal.get(
            "new_exposure",
            0,
        )
        or 0
    )

    risk_assessment = (
        risk_engine.evaluate(
            account_balance=account_balance,
            entry=entry,
            stop_loss=stop_loss,
            current_open_positions=(
                current_open_positions
            ),
            portfolio_exposure_percent=(
                current_exposure
            ),
            risk_percent=signal.get(
                "risk_percent"
            ),
        )
    )

    risk_allowed = (
        risk_assessment.allowed
    )

    trade_allowed = (
        trade_evaluation.get(
            "decision"
        )
        == "EXECUTE_CANDIDATE"
    )

    final_allowed = (
        trade_allowed
        and risk_allowed
    )

    if final_allowed:

        final_decision = (
            "EXECUTE_CANDIDATE"
        )

    else:

        final_decision = (
            "NO_TRADE"
        )

    return {
        "success": True,
        "decision": final_decision,
        "mode": "paper",
        "live_trading": False,
        "trade_engine": (
            trade_evaluation
        ),
        "risk_engine": (
            risk_assessment.__dict__
        ),
        "trade_gate": {
            "trade_engine_passed":
                trade_allowed,
            "risk_engine_passed":
                risk_allowed,
            "final_passed":
                final_allowed,
        },
    }


# =========================================================
# OPEN PAPER TRADE
# =========================================================

@router.post("/trade/paper/open")
async def open_paper_trade(
    signal: dict[str, Any],
) -> dict[str, Any]:

    if not isinstance(
        signal,
        dict,
    ):

        raise HTTPException(
            status_code=400,
            detail="Signal must be an object.",
        )

    # -----------------------------------------------------
    # Risk gate first
    # -----------------------------------------------------

    account_balance = float(
        signal.get(
            "account_balance",
            0,
        )
        or 0
    )

    entry = float(
        signal.get(
            "entry",
            0,
        )
        or 0
    )

    stop_loss = float(
        signal.get(
            "stop_loss",
            0,
        )
        or 0
    )

    current_open_positions = int(
        signal.get(
            "current_open_positions",
            len(
                default_trade_engine
                .get_open_positions()
            ),
        )
        or 0
    )

    current_exposure = float(
        signal.get(
            "current_exposure",
            0,
        )
        or 0
    )

    risk_assessment = (
        risk_engine.evaluate(
            account_balance=account_balance,
            entry=entry,
            stop_loss=stop_loss,
            current_open_positions=(
                current_open_positions
            ),
            portfolio_exposure_percent=(
                current_exposure
            ),
            risk_percent=signal.get(
                "risk_percent"
            ),
        )
    )

    if not risk_assessment.allowed:

        return {
            "success": False,
            "opened": False,
            "decision": "NO_TRADE",
            "mode": "paper",
            "risk": (
                risk_assessment.__dict__
            ),
        }

    # -----------------------------------------------------
    # Open paper trade
    # -----------------------------------------------------

    result = (
        default_trade_engine
        .open_paper_trade(
            signal
        )
    )

    return {
        **result,
        "risk": (
            risk_assessment.__dict__
        ),
        "mode": "paper",
        "live_trading": False,
    }


# =========================================================
# OPEN POSITIONS
# =========================================================

@router.get("/trade/positions")
async def trade_positions() -> dict[str, Any]:

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
# TRADE HISTORY
# =========================================================

@router.get("/trade/history")
async def trade_history(
    limit: int = Query(
        default=50,
        ge=1,
        le=500,
    ),
) -> dict[str, Any]:

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
# DAILY RISK RESET
# =========================================================

@router.post("/trade/reset-daily")
async def reset_daily() -> dict[str, Any]:

    return (
        default_trade_engine
        .reset_daily_stats()
    )
