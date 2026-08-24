from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query

from app.api.accountability_routes import _fetch_results, _number, _result_type
from app.api.routes import build_24_point_result, build_trade_levels, normalize_market, normalize_symbol
from app.core.config import settings
from app.services.challenge_post_generator import challenge_post_generator
from app.services.master_analysis import master_analysis_engine

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


async def _analyze_challenge_symbol(symbol: str, market: str) -> dict[str, Any]:
    clean_symbol = normalize_symbol(symbol)
    clean_market = normalize_market(market)
    analysis = await master_analysis_engine.analyze(
        symbol=clean_symbol,
        market=clean_market,
        candle_limit=200,
    )
    levels = build_trade_levels(analysis)
    points = build_24_point_result(analysis, levels)
    direction = str(analysis.get("direction") or "NEUTRAL").upper()
    confidence = _number(analysis.get("confidence"))
    failures: list[str] = []
    if not analysis.get("multi_timeframe", {}).get("publishable_mtf", False):
        failures.append("MTF_NOT_ALIGNED")
    if levels.get("stop_quality") != "VALID":
        failures.append("INVALID_STOP")
    if _number(levels.get("risk_reward")) < settings.pro_min_risk_reward:
        failures.append("LOW_RISK_REWARD")
    if confidence < settings.pro_min_confidence:
        failures.append("LOW_CONFIDENCE")
    if direction not in {"LONG", "SHORT"}:
        failures.append("NO_DIRECTION")
    result = {
        **analysis,
        "symbol": clean_symbol,
        "entry": levels.get("entry"),
        "stop_loss": levels.get("stop_loss"),
        "tp1": levels.get("tp1"),
        "tp2": levels.get("tp2"),
        "tp3": levels.get("tp3"),
        "risk_reward": levels.get("risk_reward"),
        "stop_quality": levels.get("stop_quality"),
        "publishable": not failures,
        "critical_failures": failures,
        "24_point_analysis": points,
        "challenge_policy": {
            "min_confidence": settings.pro_min_confidence,
            "min_risk_reward": settings.pro_min_risk_reward,
            "risk_per_trade_percent": settings.pro_risk_per_trade_percent,
            "max_open_positions": settings.pro_max_open_positions,
            "max_daily_loss_percent": settings.pro_max_daily_loss_percent,
            "max_consecutive_losses": settings.pro_max_consecutive_losses,
        },
    }
    return result


@router.get("/challenge/post/preview")
async def challenge_post_preview(
    symbol: str,
    market: str = Query("futures"),
) -> dict[str, Any]:
    try:
        analysis = await _analyze_challenge_symbol(symbol, market)
        overview = await challenge_overview(limit=2000)
        if not analysis.get("publishable"):
            return {
                "success": True,
                "mode": "challenge",
                "publishable": False,
                "analysis": analysis,
                "blocked_by": analysis.get("critical_failures", []),
                "message": "No challenge post generated because the professional challenge gates failed.",
            }
        post = challenge_post_generator.build(analysis, balance=overview["challenge"]["balance"])
        return {"success": True, "mode": "challenge", "publishable": True, "analysis": analysis, "post": post}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Challenge post preview failed: {exc}") from exc


@router.post("/challenge/post/publish")
async def challenge_post_publish(
    symbol: str,
    market: str = Query("futures"),
    force: bool = Query(False),
) -> dict[str, Any]:
    if not settings.challenge_enabled:
        raise HTTPException(status_code=409, detail="Challenge mode is disabled.")
    if not settings.auto_trade_posts_enabled or not settings.trade_post_webhook_url:
        raise HTTPException(status_code=409, detail="Challenge publisher is not configured. Set AUTO_TRADE_POSTS_ENABLED=true and TRADE_POST_WEBHOOK_URL on the server.")

    preview = await challenge_post_preview(symbol=symbol, market=market)
    if not preview.get("publishable") and not force:
        raise HTTPException(status_code=409, detail={"message": "Challenge signal failed professional gates.", "blocked_by": preview.get("blocked_by", [])})

    payload = {
        "mode": "challenge",
        "challenge": "$50_to_$1000",
        "source": "RR Trader",
        "post": preview.get("post", {}).get("post", ""),
        "signal": preview.get("analysis", {}),
        "published_at": datetime.now(timezone.utc).isoformat(),
    }
    headers = {"Content-Type": "application/json"}
    if settings.trade_post_webhook_token:
        headers["Authorization"] = f"Bearer {settings.trade_post_webhook_token}"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(settings.trade_post_webhook_url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Challenge publisher connection failed: {type(exc).__name__}") from exc
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Challenge publisher rejected the post with HTTP {response.status_code}.")
    return {"success": True, "mode": "challenge", "publisher_status": response.status_code, "preview": preview}


__all__ = ["router"]
