from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://orarigjdzfrdsehcnkdb.supabase.co").strip().rstrip("/")


def _supabase_key() -> str:
    return (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        or os.getenv("SUPABASE_SECRET_KEY", "").strip()
        or os.getenv("SUPABASE_KEY", "").strip()
    )


async def _fetch_results(limit: int) -> list[dict[str, Any]]:
    key = _supabase_key()
    if not key:
        raise HTTPException(status_code=503, detail="Supabase server key is not configured. Set SUPABASE_SERVICE_ROLE_KEY in Render.")
    params = {
        "select": "symbol,decision,confidence,entry_low,entry_high,tp1,tp2,tp3,stop_loss,signal_time,result,pnl_r,updated_at",
        "order": "signal_time.desc",
        "limit": str(limit),
    }
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.get(f"{SUPABASE_URL}/rest/v1/bitguru_signal_results", params=params, headers=headers)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Supabase connection failed: {type(exc).__name__}") from exc
    if response.status_code >= 400:
        detail = "Supabase accountability query failed."
        try:
            payload = response.json()
            message = payload.get("message") or payload.get("hint") or payload.get("error")
            if message:
                detail = f"Supabase accountability query failed: {message}"
        except Exception:
            pass
        raise HTTPException(status_code=502, detail=detail)
    data = response.json()
    if not isinstance(data, list):
        raise HTTPException(status_code=502, detail="Supabase returned an invalid accountability payload.")
    return data


def _result_type(value: Any) -> str:
    if value is None or str(value).strip() == "":
        return "OPEN"
    result = str(value).upper().strip()
    if result == "SL" or "SL" in result:
        return "SL"
    if result.startswith("TP"):
        return "WIN"
    return "OPEN"


def _number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if number == number else default
    except (TypeError, ValueError):
        return default


def _pk_day(value: Any) -> str | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (dt.astimezone(timezone.utc) + timedelta(hours=5)).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return None


@router.get("/dashboard/accountability")
async def dashboard_accountability(limit: int = Query(2000, ge=1, le=5000)) -> dict[str, Any]:
    records = await _fetch_results(limit)
    wins = [r for r in records if _result_type(r.get("result")) == "WIN"]
    losses = [r for r in records if _result_type(r.get("result")) == "SL"]
    opens = [r for r in records if _result_type(r.get("result")) == "OPEN"]
    closed = len(wins) + len(losses)
    confidences = [_number(r.get("confidence")) for r in records if r.get("confidence") is not None]
    pnl_r = sum(_number(r.get("pnl_r")) for r in records)
    longs = sum(1 for r in records if str(r.get("decision", "")).upper() == "LONG")
    shorts = sum(1 for r in records if str(r.get("decision", "")).upper() == "SHORT")
    today = (datetime.now(timezone.utc) + timedelta(hours=5)).strftime("%Y-%m-%d")
    today_count = sum(1 for r in records if _pk_day(r.get("signal_time")) == today)
    return {
        "success": True,
        "source": "bitguru_signal_results",
        "server_time": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "total": len(records), "today": today_count, "wins": len(wins), "losses": len(losses),
            "open": len(opens), "closed": closed,
            "win_rate": round((len(wins) / closed * 100.0) if closed else 0.0, 2),
            "net_r": round(pnl_r, 4),
            "avg_confidence": round(sum(confidences) / len(confidences), 2) if confidences else None,
            "long": longs, "short": shorts, "tp_sl_ratio": f"{len(wins)} / {len(losses)}",
            "best_r": round(max((_number(r.get("pnl_r")) for r in wins), default=0.0), 4),
        },
        "records": records,
    }
