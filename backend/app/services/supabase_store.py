from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx


class SupabaseStore:
    """Small server-side persistence adapter using Supabase REST.

    It never exposes the service-role key to the browser. If the credentials
    are missing, the scanner continues to work and persistence is reported as
    unavailable instead of breaking market scanning.
    """

    def __init__(self) -> None:
        self.url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
        self.key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

    def status(self) -> dict[str, Any]:
        return {
            "configured": bool(self.url and self.key),
            "mode": "server_rest" if self.url and self.key else "not_configured",
        }

    async def _request(self, method: str, path: str, *, params: dict[str, str] | None = None, payload: Any = None) -> Any:
        if not (self.url and self.key):
            return None
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.request(
                method,
                f"{self.url}/rest/v1/{path}",
                headers=headers,
                params=params,
                json=payload,
            )
            if response.status_code >= 400:
                raise RuntimeError(f"Supabase {response.status_code}: {response.text[:300]}")
            if not response.text:
                return None
            try:
                return response.json()
            except Exception:
                return None

    async def persist_scan(self, result: dict[str, Any]) -> dict[str, Any]:
        if not (self.url and self.key):
            return {"configured": False, "signals_inserted": 0}

        analyses = result.get("publishable_signals") or []
        if not isinstance(analyses, list):
            analyses = []

        inserted = 0
        now = datetime.now(timezone.utc)
        recent_cutoff = (now - timedelta(minutes=15)).isoformat()

        for item in analyses:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or "").upper()
            direction = str(item.get("direction") or item.get("signal") or "").upper()
            confidence = float(item.get("confidence") or 0)
            if not symbol or direction not in {"LONG", "SHORT"} or confidence < 85:
                continue

            # Avoid flooding the history with the same setup every minute.
            existing = await self._request(
                "GET",
                "signals",
                params={
                    "select": "id",
                    "symbol": f"eq.{symbol}",
                    "direction": f"eq.{direction}",
                    "scanned_at": f"gte.{recent_cutoff}",
                    "limit": "1",
                },
            )
            if isinstance(existing, list) and existing:
                continue

            entry = item.get("entry_price", item.get("entry"))
            tp = item.get("target_price", item.get("tp1", item.get("take_profit")))
            sl = item.get("stop_loss", item.get("sl"))
            reason = item.get("signal_reason") or item.get("reason") or item.get("explanation") or "RR Trader qualified setup"

            payload = {
                "symbol": symbol,
                "market_type": str(result.get("market") or "futures").lower(),
                "direction": direction,
                "confidence": confidence,
                "entry_price": entry,
                "target_price": tp,
                "stop_loss": sl,
                "signal_reason": str(reason)[:2000],
                "status": "new",
                "scanned_at": item.get("scanned_at") or result.get("timestamp") or now.isoformat(),
            }
            await self._request("POST", "signals", payload=payload)
            inserted += 1

        try:
            await self._request(
                "POST",
                "scan_logs",
                payload={
                    "scan_type": "auto",
                    "symbols_scanned": int(result.get("scanned_universe") or 0),
                    "candidates_found": int(result.get("publishable_count") or 0),
                    "best_symbol": (result.get("best") or {}).get("symbol") if isinstance(result.get("best"), dict) else None,
                    "best_direction": (result.get("best") or {}).get("direction") if isinstance(result.get("best"), dict) else None,
                    "best_confidence": (result.get("best") or {}).get("confidence") if isinstance(result.get("best"), dict) else None,
                    "status": "completed",
                },
            )
        except Exception:
            pass

        return {"configured": True, "signals_inserted": inserted}

    async def persist(self, result: dict[str, Any]) -> dict[str, Any]:
        try:
            return await self.persist_scan(result)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return {"configured": bool(self.url and self.key), "signals_inserted": 0, "error": str(exc)}


supabase_store = SupabaseStore()


async def persist_scan_result(result: dict[str, Any]) -> dict[str, Any]:
    return await supabase_store.persist(result)
