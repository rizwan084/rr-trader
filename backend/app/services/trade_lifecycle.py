from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.binance_execution import binance_execution_client
from app.services.execution_repository import execution_repository
from app.services.trade_orchestrator import trade_orchestrator


class TradeLifecycleService:
    """Reconciles exchange positions into deterministic TP/SL outcomes."""

    @staticmethod
    def _f(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _result_from_orders(orders: list[dict[str, Any]]) -> str:
        filled = [o for o in orders if str(o.get("status", "")).upper() == "FILLED"]
        if not filled:
            return "CLOSED_EXTERNAL"
        if any(str(o.get("type", "")).upper() == "STOP_MARKET" for o in filled):
            if any(str(o.get("type", "")).upper() == "TAKE_PROFIT_MARKET" for o in filled):
                return "MIXED_TP_SL"
            return "SL"
        tp = [o for o in filled if str(o.get("type", "")).upper() == "TAKE_PROFIT_MARKET"]
        if not tp:
            return "CLOSED"
        return f"TP{min(len(tp), 3)}"

    def _calculate_r(self, trade: dict[str, Any], orders: list[dict[str, Any]]) -> float:
        entry = self._f(trade.get("entry_price") or trade.get("entry"))
        stop = self._f(trade.get("stop_loss"))
        qty_total = self._f(trade.get("position_size"))
        if entry <= 0 or stop <= 0 or qty_total <= 0:
            return 0.0
        risk_distance = abs(entry - stop)
        side = str(trade.get("side", "LONG")).upper()
        total_r = 0.0
        for order in orders:
            if str(order.get("status", "")).upper() != "FILLED":
                continue
            qty = self._f(order.get("executedQty"))
            price = self._f(order.get("avgPrice") or order.get("price"))
            if qty <= 0 or price <= 0:
                continue
            move = (price - entry) if side == "LONG" else (entry - price)
            total_r += (move / risk_distance) * (qty / qty_total)
        return round(total_r, 4)

    async def reconcile_once(self) -> dict[str, Any]:
        if not binance_execution_client.live_enabled or not execution_repository.configured:
            return {"success": True, "status": "DISABLED"}

        trades = await execution_repository.open_trades()
        closed = 0
        errors: list[str] = []
        for trade in trades:
            symbol = str(trade.get("symbol", "")).upper()
            signal_id = str(trade.get("signal_id", ""))
            if not symbol or not signal_id:
                continue
            try:
                positions = await binance_execution_client.position_risk(symbol)
                position = None
                if isinstance(positions, list):
                    position = next((p for p in positions if abs(self._f(p.get("positionAmt"))) > 0), None)
                if position is not None:
                    continue

                order_ids = [trade.get(k) for k in ("tp1_order_id", "tp2_order_id", "tp3_order_id", "sl_order_id") if trade.get(k)]
                orders: list[dict[str, Any]] = []
                for order_id in order_ids:
                    try:
                        orders.append(await binance_execution_client.order_status(symbol, order_id))
                    except Exception as exc:
                        errors.append(f"{symbol}:{order_id}:{exc}")

                result = self._result_from_orders(orders)
                pnl_r = self._calculate_r(trade, orders)
                exits = [self._f(o.get("avgPrice")) for o in orders if str(o.get("status", "")).upper() == "FILLED" and self._f(o.get("avgPrice")) > 0]
                exit_price = exits[-1] if exits else None
                closed_at = datetime.now(timezone.utc).isoformat()

                await execution_repository.close_trade(
                    signal_id,
                    status="CLOSED",
                    result=result,
                    exit_price=exit_price,
                    pnl_r=pnl_r,
                    raw_close={"closed_at": closed_at, "orders": orders},
                )

                # Update the in-memory challenge tracker used by the live dashboard.
                challenge = trade_orchestrator.challenge
                challenge.net_r += pnl_r
                if result.startswith("TP") or result == "MIXED_TP_SL":
                    challenge.wins += 1
                    challenge.consecutive_losses = 0
                elif result == "SL":
                    challenge.losses += 1
                    challenge.consecutive_losses += 1
                if signal_id in trade_orchestrator._active_signal_ids:
                    trade_orchestrator._active_signal_ids.remove(signal_id)
                closed += 1

                await trade_orchestrator._post_trade_event({
                    "event": "TRADE_CLOSED",
                    "symbol": symbol,
                    "side": trade.get("side"),
                    "signal_id": signal_id,
                    "result": result,
                    "pnl_r": pnl_r,
                    "exit_price": exit_price,
                    "closed_at": closed_at,
                })
            except Exception as exc:
                errors.append(f"{symbol}:{exc}")

        return {"success": True, "status": "RECONCILED", "open_records": len(trades), "closed": closed, "errors": errors}


trade_lifecycle_service = TradeLifecycleService()
