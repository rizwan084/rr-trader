from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.core.config import settings
from app.services.execution_repository import execution_repository
from app.services.pro_risk_engine import pro_risk_engine
from app.services.trade_orchestrator import trade_orchestrator

router = APIRouter()


@router.get("/live/status")
async def live_status() -> dict[str, Any]:
    return await trade_orchestrator.account_status()


@router.get("/live/risk-policy")
async def live_risk_policy() -> dict[str, Any]:
    return {"success": True, "policy": pro_risk_engine.status()}


@router.get("/live/executions")
async def live_executions(limit: int = 100) -> dict[str, Any]:
    if not execution_repository.configured:
        return {"success": True, "configured": False, "records": []}
    records = await execution_repository.open_trades(limit=max(1, min(limit, 500)))
    return {"success": True, "configured": True, "records": records}


@router.post("/live/preview")
async def live_preview(signal: dict[str, Any]) -> dict[str, Any]:
    return trade_orchestrator.preview(signal)


@router.post("/live/execute")
async def live_execute(signal: dict[str, Any]) -> dict[str, Any]:
    # This endpoint cannot override deployment safety flags. Live execution
    # requires explicit server-side configuration and the pro risk gate.
    return await trade_orchestrator.execute(signal)


@router.get("/live/safety")
async def live_safety() -> dict[str, Any]:
    return {
        "success": True,
        "trading_mode": settings.trading_mode,
        "live_trading_enabled": settings.live_trading_enabled,
        "pro_risk_gate_required": settings.require_pro_risk_gate,
        "binance_key_configured": bool(settings.binance_api_key and settings.binance_api_secret),
        "supabase_execution_store": execution_repository.configured,
        "warning": "Live execution remains OFF until TRADING_MODE=live and LIVE_TRADING_ENABLED=true are configured on the server.",
    }
