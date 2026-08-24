from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import settings


class ExecutionRepository:
    def __init__(self) -> None:
        self.base = f"{settings.supabase_url}/rest/v1/rr_trade_executions"

    @property
    def configured(self) -> bool:
        return bool(settings.supabase_service_role_key and settings.supabase_url)

    def _headers(self) -> dict[str, str]:
        key = settings.supabase_service_role_key
        return {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Prefer": "return=representation",
        }

    async def create_open_trade(self, signal: dict[str, Any], execution: dict[str, Any]) -> dict[str, Any] | None:
        if not self.configured:
            return None
        plan = execution.get("risk", {})
        entry_order = execution.get("entry_order") or {}
        protective = execution.get("protective_orders") or []
        opened_at = datetime.now(timezone.utc).isoformat()
        payload = {
            "signal_id": execution.get("signal_id"),
            "symbol": str(execution.get("symbol", "")).upper(),
            "side": str(execution.get("side", "")).upper(),
            "market": str(signal.get("market", "futures")).lower(),
            "status": "OPEN",
            "entry": signal.get("entry"),
            "stop_loss": signal.get("stop_loss"),
            "tp1": signal.get("tp1"),
            "tp2": signal.get("tp2"),
            "tp3": signal.get("tp3"),
            "entry_price": entry_order.get("avgPrice") or entry_order.get("price") or signal.get("entry"),
            "position_size": plan.get("position_size"),
            "risk_percent": plan.get("risk_percent"),
            "risk_amount": plan.get("risk_amount"),
            "leverage": signal.get("leverage") or settings.default_leverage,
            "confidence": signal.get("confidence"),
            "risk_reward": signal.get("risk_reward"),
            "entry_order_id": str(entry_order.get("orderId")) if entry_order.get("orderId") is not None else None,
            "tp1_order_id": str(protective[0].get("orderId")) if len(protective) > 0 else None,
            "tp2_order_id": str(protective[1].get("orderId")) if len(protective) > 1 else None,
            "tp3_order_id": str(protective[2].get("orderId")) if len(protective) > 2 else None,
            "sl_order_id": str(protective[-1].get("orderId")) if protective else None,
            "opened_at": opened_at,
            "raw_entry": entry_order,
            "raw_orders": protective,
        }
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.post(self.base, json=payload, headers=self._headers())
        if response.status_code >= 400:
            raise RuntimeError(f"Supabase execution insert failed: {response.text[:500]}")
        rows = response.json()
        return rows[0] if isinstance(rows, list) and rows else None

    async def open_trades(self, limit: int = 100) -> list[dict[str, Any]]:
        if not self.configured:
            return []
        params = {"select": "*", "status": "eq.OPEN", "order": "opened_at.desc", "limit": str(limit)}
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.get(self.base, params=params, headers=self._headers())
        if response.status_code >= 400:
            raise RuntimeError(f"Supabase execution read failed: {response.text[:500]}")
        data = response.json()
        return data if isinstance(data, list) else []

    async def close_trade(self, signal_id: str, *, status: str, result: str, exit_price: float | None, pnl_r: float | None, raw_close: dict[str, Any]) -> None:
        if not self.configured:
            return
        payload = {
            "status": status,
            "result": result,
            "exit_price": exit_price,
            "pnl_r": pnl_r,
            "closed_at": raw_close.get("closed_at"),
            "raw_close": raw_close,
            "updated_at": raw_close.get("closed_at"),
        }
        params = {"signal_id": f"eq.{signal_id}"}
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.patch(self.base, params=params, json=payload, headers=self._headers())
        if response.status_code >= 400:
            raise RuntimeError(f"Supabase execution close failed: {response.text[:500]}")


execution_repository = ExecutionRepository()
