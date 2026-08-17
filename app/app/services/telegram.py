from __future__ import annotations

from typing import Any, Optional

import httpx

from app.config import Settings


class TelegramService:
    """
    RR Trader Telegram notification service.

    Used for:
    - New LONG / SHORT signals
    - TP1 / TP2 / TP3 updates
    - Stop Loss updates
    - Signal closed reports
    - General RR Trader messages
    """

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings()

        self.bot_token = getattr(
            self.settings,
            "telegram_bot_token",
            "",
        )

        self.chat_id = getattr(
            self.settings,
            "telegram_chat_id",
            "",
        )

        self.timeout = float(
            getattr(
                self.settings,
                "request_timeout",
                15,
            )
        )

    # =========================================================
    # CONFIG CHECK
    # =========================================================

    @property
    def enabled(self) -> bool:
        return bool(
            self.bot_token
            and self.chat_id
        )

    # =========================================================
    # TELEGRAM URL
    # =========================================================

    @property
    def api_url(self) -> str:
        return (
            f"https://api.telegram.org/"
            f"bot{self.bot_token}/sendMessage"
        )

    # =========================================================
    # SEND MESSAGE
    # =========================================================

    async def send_message(
        self,
        message: str,
        chat_id: Optional[str] = None,
        parse_mode: Optional[str] = "HTML",
    ) -> dict[str, Any]:

        if not self.bot_token:
            return {
                "success": False,
                "error": "Telegram bot token is not configured",
            }

        target_chat_id = (
            chat_id
            or self.chat_id
        )

        if not target_chat_id:
            return {
                "success": False,
                "error": "Telegram chat ID is not configured",
            }

        payload: dict[str, Any] = {
            "chat_id": target_chat_id,
            "text": message,
        }

        if parse_mode:
            payload["parse_mode"] = parse_mode

        try:

            async with httpx.AsyncClient(
                timeout=self.timeout
            ) as client:

                response = await client.post(
                    self.api_url,
                    json=payload,
                )

                response.raise_for_status()

                data = response.json()

                if not data.get("ok"):
                    return {
                        "success": False,
                        "error": data.get(
                            "description",
                            "Telegram API error",
                        ),
                        "response": data,
                    }

                return {
                    "success": True,
                    "response": data,
                }

        except Exception as exc:

            return {
                "success": False,
                "error": str(exc),
            }

    # =========================================================
    # NEW SIGNAL
    # =========================================================

    async def send_signal(
        self,
        signal: dict[str, Any],
    ) -> dict[str, Any]:

        symbol = str(
            signal.get(
                "symbol",
                "UNKNOWN",
            )
        ).upper()

        market = str(
            signal.get(
                "market",
                "futures",
            )
        ).upper()

        direction = str(
            signal.get(
                "signal",
                signal.get(
                    "direction",
                    "WAIT",
                ),
            )
        ).upper()

        confidence = signal.get(
            "confidence",
            0,
        )

        entry = signal.get(
            "entry",
            signal.get(
                "price",
                0,
            ),
        )

        stop_loss = signal.get(
            "stop_loss"
        )

        targets = signal.get(
            "targets",
            [],
        )

        risk_reward = signal.get(
            "risk_reward"
        )

        reasons = signal.get(
            "reasons",
            [],
        )

        message = (
            "<b>🚨 RR TRADER SIGNAL</b>\n\n"
            f"<b>{symbol}</b>\n"
            f"Market: {market}\n"
            f"Signal: <b>{direction}</b>\n"
            f"Confidence: <b>{confidence}%</b>\n\n"
            f"Entry: <code>{entry}</code>\n"
            f"SL: <code>{stop_loss}</code>\n"
        )

        if targets:

            for index, target in enumerate(
                targets[:3],
                start=1,
            ):

                message += (
                    f"TP{index}: "
                    f"<code>{target}</code>\n"
                )

        if risk_reward is not None:

            message += (
                f"Risk/Reward: "
                f"<b>{risk_reward}R</b>\n"
            )

        if reasons:

            message += "\n<b>Why this signal:</b>\n"

            for reason in reasons[:8]:

                message += (
                    f"• {reason}\n"
                )

        return await self.send_message(
            message
        )

    # =========================================================
    # TP HIT
    # =========================================================

    async def send_tp_hit(
        self,
        symbol: str,
        target_number: int,
        price: float,
        direction: str,
    ) -> dict[str, Any]:

        message = (
            "<b>✅ TAKE PROFIT HIT</b>\n\n"
            f"<b>{symbol.upper()}</b>\n"
            f"Direction: <b>{direction.upper()}</b>\n"
            f"TP{target_number}: "
            f"<code>{price}</code>\n\n"
            "RR Trader signal monitor "
            "detected the target hit."
        )

        return await self.send_message(
            message
        )

    # =========================================================
    # STOP LOSS HIT
    # =========================================================

    async def send_stop_loss(
        self,
        symbol: str,
        price: float,
        direction: str,
    ) -> dict[str, Any]:

        message = (
            "<b>❌ STOP LOSS HIT</b>\n\n"
            f"<b>{symbol.upper()}</b>\n"
            f"Direction: <b>{direction.upper()}</b>\n"
            f"SL: <code>{price}</code>\n\n"
            "RR Trader signal has been closed."
        )

        return await self.send_message(
            message
        )

    # =========================================================
    # SIGNAL CLOSED
    # =========================================================

    async def send_signal_closed(
        self,
        symbol: str,
        direction: str,
        result: str,
        entry: Optional[float] = None,
        exit_price: Optional[float] = None,
        pnl_percent: Optional[float] = None,
    ) -> dict[str, Any]:

        message = (
            "<b>🏁 RR TRADER SIGNAL CLOSED</b>\n\n"
            f"<b>{symbol.upper()}</b>\n"
            f"Direction: <b>{direction.upper()}</b>\n"
            f"Result: <b>{result.upper()}</b>\n"
        )

        if entry is not None:
            message += (
                f"Entry: <code>{entry}</code>\n"
            )

        if exit_price is not None:
            message += (
                f"Exit: <code>{exit_price}</code>\n"
            )

        if pnl_percent is not None:
            message += (
                f"PnL: <b>{pnl_percent}%</b>\n"
            )

        return await self.send_message(
            message
        )

    # =========================================================
    # GENERAL REPORT
    # =========================================================

    async def send_report(
        self,
        title: str,
        body: str,
    ) -> dict[str, Any]:

        message = (
            f"<b>{title}</b>\n\n"
            f"{body}"
        )

        return await self.send_message(
            message
        )

    # =========================================================
    # TEST MESSAGE
    # =========================================================

    async def test_connection(
        self,
    ) -> dict[str, Any]:

        return await self.send_message(
            "✅ <b>RR Trader Telegram Connected</b>\n\n"
            "Telegram notification system is working."
        )


# =============================================================
# SINGLETON
# =============================================================

telegram_service = TelegramService()


# =============================================================
# HELPER
# =============================================================

async def send_telegram_message(
    message: str,
) -> dict[str, Any]:

    return await telegram_service.send_message(
        message
    )


__all__ = [
    "TelegramService",
    "telegram_service",
    "send_telegram_message",
]
