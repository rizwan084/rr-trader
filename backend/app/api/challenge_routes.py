from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Query

from app.api.accountability_routes import _fetch_results, _number, _result_type

router = APIRouter()

START_BALANCE = 50.0
TARGET_BALANCE = 1000.0
DEFAULT_RISK_PCT = 1.0
DEFAULT_MAX_DAILY_LOSS_PCT = 3.0
DEFAULT_MAX_LEVERAGE = 5.0


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


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _target_progress(direction: str, entry: float, price: float, target: float) -> float | None:
    if entry <= 0 or price <= 0 or target <= 0:
        return None
    direction = direction.upper()
    distance = target - entry if direction == "LONG" else entry - target
    if distance <= 0:
        return None
    moved = price - entry if direction == "LONG" else entry - price
    return _clamp(moved / distance * 100.0, 0.0, 100.0)


def _trade_view(record: dict[str, Any]) -> dict[str, Any]:
    direction = str(record.get("decision") or "").upper()
    entry_low = _number(record.get("entry_low"))
    entry_high = _number(record.get("entry_high"))
    entry = (entry_low + entry_high) / 2 if entry_low and entry_high else entry_low or entry_high
    price = _number(record.get("last_price"))
    tps = [_number(record.get("tp1")), _number(record.get("tp2")), _number(record.get("tp3"))]
    sl = _number(record.get("stop_loss"))
    return {
        **record,
        "entry": entry,
        "current_price": price or None,
        "tp_progress": [
            _target_progress(direction, entry, price, tp) if price and entry and tp else None
            for tp in tps
        ],
        "sl_distance_pct": (abs(entry - sl) / entry * 100.0) if entry and sl else None,
        "status": _result_type(record.get("result")),
    }


@router.get("/challenge/overview")
async def challenge_overview(
    limit: int = Query(2000, ge=1, le=5000),
    start_balance: float = Query(START_BALANCE, gt=0),
    target_balance: float = Query(TARGET_BALANCE, gt=0),
    risk_pct: float = Query(DEFAULT_RISK_PCT, gt=0, le=5),
    max_daily_loss_pct: float = Query(DEFAULT_MAX_DAILY_LOSS_PCT, gt=0, le=10),
    max_leverage: float = Query(DEFAULT_MAX_LEVERAGE, gt=1, le=20),
) -> dict[str, Any]:
    records = await _fetch_results(limit)
    ordered = list(reversed(records))
    balance = float(start_balance)
    closed = 0
    wins = 0
    losses = 0
    risk_used = 0.0
    daily_r: dict[str, float] = {}
    equity_curve: list[dict[str, Any]] = [{"time": None, "balance": round(balance, 4)}]

    for record in ordered:
        result = _result_type(record.get("result"))
        if result == "OPEN":
            continue
        pnl_r = _number(record.get("pnl_r"))
        risk_amount = balance * (risk_pct / 100.0)
        balance += risk_amount * pnl_r
        risk_used += abs(risk_amount)
        closed += 1
        if result == "WIN":
            wins += 1
        elif result == "SL":
            losses += 1
        day = _pk_day(record.get("signal_time"))
        if day:
            daily_r[day] = daily_r.get(day, 0.0) + pnl_r
        equity_curve.append({"time": record.get("signal_time"), "balance": round(balance, 4)})

    open_trades = [_trade_view(r) for r in records if _result_type(r.get("result")) == "OPEN"]
    progress = _clamp((balance - start_balance) / (target_balance - start_balance) * 100.0, 0.0, 100.0) if target_balance > start_balance else 100.0
    drawdown_days = [
        {"date": day, "r": round(value, 4), "loss_pct": round(max(0.0, -value) * risk_pct, 4)}
        for day, value in sorted(daily_r.items())
    ]
    worst_day = min(drawdown_days, key=lambda x: x["r"], default=None)
    win_rate = (wins / closed * 100.0) if closed else 0.0

    return {
        "success": True,
        "challenge": {
            "name": "$50 → $1,000 Challenge",
            "status": "TARGET_REACHED" if balance >= target_balance else "ACTIVE",
            "start_balance": round(start_balance, 4),
            "target_balance": round(target_balance, 4),
            "balance": round(balance, 4),
            "profit": round(balance - start_balance, 4),
            "progress_pct": round(progress, 2),
            "remaining": round(max(0.0, target_balance - balance), 4),
            "multiple_required": round(target_balance / start_balance, 2),
        },
        "risk": {
            "risk_per_trade_pct": risk_pct,
            "max_daily_loss_pct": max_daily_loss_pct,
            "max_leverage": max_leverage,
            "risk_model": "Fixed percentage of current challenge equity; leverage does not increase allowed risk.",
            "daily_loss_guard": "BLOCK_NEW_TRADES" if worst_day and worst_day["loss_pct"] >= max_daily_loss_pct else "OK",
            "worst_day": worst_day,
            "total_risk_budget_used": round(risk_used, 4),
        },
        "performance": {
            "signals": len(records),
            "closed": closed,
            "open": len(open_trades),
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 2),
            "net_r": round(sum(_number(r.get("pnl_r")) for r in records), 4),
        },
        "open_trades": open_trades,
        "recent_trades": [_trade_view(r) for r in records[:100]],
        "equity_curve": equity_curve[-60:],
        "data_notes": {
            "confidence": "Confidence and detailed decision reasons are available from the live RR Trader signal engine; the existing BitGuru result table does not currently persist those fields.",
            "execution": "This challenge dashboard is read-only until Binance execution is explicitly enabled.",
            "supabase": "No schema mutation is performed by this endpoint; it reads the existing accountability result data only.",
        },
    }


__all__ = ["router"]
