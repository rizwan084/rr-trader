from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import settings
from app.models.execution import ChallengeState, ExecutionResult, TradePlan
from app.services.binance_execution import BinanceExecutionError, binance_execution_client
from app.services.pro_risk_engine import pro_risk_engine


class TradeOrchestrator:
    """Final gate between RR Trader analysis and exchange execution."""

    def __init__(self) -> None:
        self.challenge = ChallengeState(
            starting_balance=settings.challenge_start_balance,
            target_balance=settings.challenge_target_balance,
            current_balance=settings.challenge_start_balance,
            peak_balance=settings.challenge_start_balance,
            daily_start_balance=settings.challenge_start_balance,
        )
        self._active_signal_ids: set[str] = set()
        self._last_symbol_execution: dict[str, float] = {}
        self.cooldown_seconds = 30 * 60

    @staticmethod
    def _f(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _signal_id(signal: dict[str, Any]) -> str:
        raw = "|".join(
            str(signal.get(k, ""))
            for k in ("symbol", "direction", "entry", "stop_loss", "tp1", "tp2", "tp3", "timestamp")
        )
        return hashlib.sha256(raw.encode()).hexdigest()[:24]

    def _account_balance(self) -> float:
        return max(self.challenge.current_balance, 0.0)

    def build_plan(self, signal: dict[str, Any]) -> TradePlan:
        return TradePlan(
            symbol=str(signal.get("symbol", "")).upper(),
            side=str(signal.get("direction") or signal.get("decision") or "").upper(),
            entry=self._f(signal.get("entry")),
            stop_loss=self._f(signal.get("stop_loss")),
            take_profits=tuple(
                x for x in (
                    self._f(signal.get("tp1")),
                    self._f(signal.get("tp2")),
                    self._f(signal.get("tp3")),
                ) if x > 0
            ),
            confidence=self._f(signal.get("confidence")),
            risk_reward=self._f(signal.get("risk_reward")),
            risk_percent=settings.pro_risk_per_trade_percent,
            leverage=max(1, min(settings.default_leverage, settings.max_leverage)),
            setup=str(signal.get("setup") or signal.get("setup_type") or ""),
            signal_id=self._signal_id(signal),
        )

    def preview(self, signal: dict[str, Any]) -> dict[str, Any]:
        plan = self.build_plan(signal)
        decision = pro_risk_engine.evaluate(
            signal,
            account_balance=self._account_balance(),
            open_positions=len(self._active_signal_ids),
            daily_pnl_percent=(
                self.challenge.daily_pnl / self.challenge.daily_start_balance * 100.0
                if self.challenge.daily_start_balance > 0 else 0.0
            ),
            consecutive_losses=self.challenge.consecutive_losses,
            risk_percent=plan.risk_percent,
        )
        return {
            "success": True,
            "mode": "live" if binance_execution_client.live_enabled else "paper",
            "live_enabled": binance_execution_client.live_enabled,
            "configured": binance_execution_client.configured,
            "plan": {
                "symbol": plan.symbol,
                "side": plan.side,
                "entry": plan.entry,
                "stop_loss": plan.stop_loss,
                "take_profits": list(plan.take_profits),
                "confidence": plan.confidence,
                "risk_reward": plan.risk_reward,
                "risk_percent": plan.risk_percent,
                "leverage": plan.leverage,
                "signal_id": plan.signal_id,
            },
            "risk": decision.as_dict(),
        }

    async def execute(self, signal: dict[str, Any]) -> dict[str, Any]:
        preview = self.preview(signal)
        plan = self.build_plan(signal)
        risk = preview["risk"]

        if not risk["allowed"]:
            return ExecutionResult(
                success=False,
                mode="live" if binance_execution_client.live_enabled else "paper",
                symbol=plan.symbol,
                side=plan.side,
                status="REJECTED",
                message=risk["reason"],
                risk=risk,
                signal_id=plan.signal_id,
            ).__dict__

        if plan.signal_id in self._active_signal_ids:
            return ExecutionResult(False, "live", plan.symbol, plan.side, "DUPLICATE", "Signal already active", risk=risk, signal_id=plan.signal_id).__dict__

        if not binance_execution_client.live_enabled:
            return ExecutionResult(True, "paper", plan.symbol, plan.side, "PAPER_APPROVED", "Risk gates passed; live execution is disabled", risk=risk, signal_id=plan.signal_id).__dict__

        now = datetime.now(timezone.utc).timestamp()
        last = self._last_symbol_execution.get(plan.symbol, 0.0)
        if now - last < self.cooldown_seconds:
            return ExecutionResult(False, "live", plan.symbol, plan.side, "COOLDOWN", "Symbol execution cooldown is active", risk=risk, signal_id=plan.signal_id).__dict__

        if not plan.take_profits:
            return ExecutionResult(False, "live", plan.symbol, plan.side, "REJECTED", "At least one take-profit is required", risk=risk, signal_id=plan.signal_id).__dict__

        try:
            await binance_execution_client.set_leverage(plan.symbol, plan.leverage)
            quantity = await binance_execution_client.normalize_order_quantity(plan.symbol, plan.entry and plan.entry * 0 + risk["position_size"] or 0)
            if quantity <= 0:
                raise BinanceExecutionError("Calculated position quantity is zero.")

            entry_order = await binance_execution_client.new_order(
                symbol=plan.symbol,
                side=plan.direction_side,
                type="MARKET",
                quantity=quantity,
            )

            protective: list[dict[str, Any]] = []
            # Split the position across TP1/TP2/TP3. The stop remains a full-position
            # close so a failed target never leaves an unprotected position.
            allocations = [0.40, 0.30, 0.30]
            for index, target in enumerate(plan.take_profits[:3]):
                target_price = await binance_execution_client.normalize_price(plan.symbol, target)
                qty = await binance_execution_client.normalize_order_quantity(plan.symbol, quantity * allocations[index])
                if qty <= 0:
                    continue
                protective.append(await binance_execution_client.new_order(
                    symbol=plan.symbol,
                    side=plan.close_side,
                    type="TAKE_PROFIT_MARKET",
                    stopPrice=target_price,
                    quantity=qty,
                    reduceOnly="true",
                    workingType="MARK_PRICE",
                ))

            stop_price = await binance_execution_client.normalize_price(plan.symbol, plan.stop_loss)
            protective.append(await binance_execution_client.new_order(
                symbol=plan.symbol,
                side=plan.close_side,
                type="STOP_MARKET",
                stopPrice=stop_price,
                closePosition="true",
                workingType="MARK_PRICE",
            ))

            self._active_signal_ids.add(plan.signal_id)
            self._last_symbol_execution[plan.symbol] = now
            self.challenge.total_trades += 1

            await self._post_trade_event({
                "event": "TRADE_OPENED",
                "symbol": plan.symbol,
                "side": plan.side,
                "signal_id": plan.signal_id,
                "entry_order": entry_order,
                "protective_orders": protective,
                "risk": risk,
            })

            return ExecutionResult(
                True,
                "live",
                plan.symbol,
                plan.side,
                "OPEN",
                "Live trade opened with protective TP/SL orders",
                entry_order=entry_order,
                protective_orders=protective,
                risk=risk,
                signal_id=plan.signal_id,
            ).__dict__
        except Exception as exc:
            return ExecutionResult(
                False,
                "live",
                plan.symbol,
                plan.side,
                "EXECUTION_ERROR",
                str(exc),
                risk=risk,
                signal_id=plan.signal_id,
            ).__dict__

    async def _post_trade_event(self, payload: dict[str, Any]) -> None:
        if not settings.auto_trade_posts_enabled or not settings.trade_post_webhook_url:
            return
        headers = {"Content-Type": "application/json"}
        if settings.trade_post_webhook_token:
            headers["Authorization"] = f"Bearer {settings.trade_post_webhook_token}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(settings.trade_post_webhook_url, json=payload, headers=headers)
        except Exception:
            # Posting must never be allowed to break trade execution.
            return

    def status(self) -> dict[str, Any]:
        return {
            "success": True,
            "mode": settings.trading_mode,
            "live_enabled": binance_execution_client.live_enabled,
            "binance_configured": binance_execution_client.configured,
            "challenge": self.challenge.snapshot(),
            "active_signals": len(self._active_signal_ids),
            "active_signal_ids": sorted(self._active_signal_ids),
            "default_leverage": settings.default_leverage,
            "max_leverage": settings.max_leverage,
            "pro_risk": pro_risk_engine.status(),
        }

    async def account_status(self) -> dict[str, Any]:
        status = self.status()
        if not binance_execution_client.live_enabled:
            return status
        try:
            account = await binance_execution_client.account()
            positions = await binance_execution_client.position_risk()
            status["binance_account"] = {
                "available_balance": account.get("availableBalance"),
                "total_wallet_balance": account.get("totalWalletBalance"),
                "total_unrealized_pnl": account.get("totalUnrealizedProfit"),
            }
            status["positions"] = [p for p in positions if self._f(p.get("positionAmt")) != 0]
        except Exception as exc:
            status["account_error"] = str(exc)
        return status


trade_orchestrator = TradeOrchestrator()
