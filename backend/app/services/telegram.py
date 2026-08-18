from __future__ import annotations

from typing import Any, Optional

import httpx

from app.core.config import settings


class TelegramService:
    """
    RR Trader Telegram notification service foundation.

    Planned notifications:
    - New LONG / SHORT signals
    - TP1 / TP2 / TP3
    - Stop Loss
    - Signal closed
    - System reports

    Telegram is disabled unless explicitly enabled
    in environment configuration.
    """

    def __init__(self) -> None:

        self.enabled = bool(
            settings.telegram_enabled
            and settings.telegram_bot_token
            and settings.telegram_chat_id
        )

        self.bot_token = (
            settings.telegram_bot_token
        )

        self.chat_id = (
            settings.telegram_chat_id
        )

        self.timeout = float(
            settings.request_timeout
        )

    # =====================================================
    # TELEGRAM API URL
    # =====================================================

    @property
    def api_url(self) -> str:

        return (
            "https://api.telegram.org/"
            f"bot{self.bot_token}/sendMessage"
        )

    # =====================================================
    # SEND MESSAGE
    # =====================================================

    async def send_message(
        self,
        message: str,
        *,
        chat_id: Optional[str] = None,
        parse_mode: Optional[str] = "HTML",
    ) -> dict[str, Any]:

        if not self.enabled:

            return {
                "success": False,
                "enabled": False,
                "error": (
                    "Telegram is disabled or "
                    "credentials are missing."
                ),
            }

        target_chat_id = (
            chat_id
            or self.chat_id
        )

        payload: dict[str, Any] = {
            "chat_id": target_chat_id,
            "text": str(
                message
            ),
        }

        if parse_mode:
            payload["parse_mode"] = (
                parse_mode
            )

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

            if not data.get(
                "ok",
                False,
            ):

                return {
                    "success": False,
                    "enabled": True,
                    "error": data.get(
                        "description",
                        "Telegram API error",
                    ),
                    "response": data,
                }

            return {
                "success": True,
                "enabled": True,
                "response": data,
            }

        except Exception as exc:

            return {
                "success": False,
                "enabled": True,
                "error": str(exc),
            }

    # =====================================================
    # NEW SIGNAL
    # =====================================================

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

        direction = str(
            signal.get(
                "direction",
                "NO TRADE",
            )
        ).upper()

        confidence = signal.get(
            "confidence",
            0,
        )

        entry = signal.get(
            "entry"
        )

        stop_loss = signal.get(
            "stop_loss"
        )

        tp1 = signal.get(
            "tp1"
        )

        tp2 = signal.get(
            "tp2"
        )

        tp3 = signal.get(
            "tp3"
        )

        risk_reward = signal.get(
            "risk_reward"
        )

        reasons = signal.get(
            "reasons",
            [],
        )

        lines = [
            "<b>RR TRADER SIGNAL</b>",
            "",
            f"<b>{symbol}</b>",
            f"Direction: <b>{direction}</b>",
            f"Confidence: <b>{confidence}%</b>",
            "",
            f"Entry: <code>{entry}</code>",
            f"SL: <code>{stop_loss}</code>",
            f"TP1: <code>{tp1}</code>",
            f"TP2: <code>{tp2}</code>",
            f"TP3: <code>{tp3}</code>",
        ]

        if risk_reward is not None:
            lines.append(
                f"Risk/Reward: "
                f"<b>{risk_reward}R</b>"
            )

        if reasons:

            lines.extend(
                [
                    "",
                    "<b>Why this signal:</b>",
                ]
            )

            for reason in reasons[:8]:

                lines.append(
                    "• "
                    + str(reason)
                )

        return await self.send_message(
            "\n".join(lines)
        )

    # =====================================================
    # TP HIT
    # =====================================================

    async def send_tp_hit(
        self,
        symbol: str,
        target_number: int,
        price: float,
        direction: str,
    ) -> dict[str, Any]:

        message = (
            "<b>RR TRADER — TAKE PROFIT HIT</b>\n\n"
            f"<b>{symbol.upper()}</b>\n"
            f"Direction: "
            f"<b>{direction.upper()}</b>\n"
            f"TP{target_number}: "
            f"<code>{price}</code>"
        )

        return await self.send_message(
            message
        )

    # =====================================================
    # STOP LOSS
    # =====================================================

    async def send_stop_loss(
        self,
        symbol: str,
        price: float,
        direction: str,
    ) -> dict[str, Any]:

        message = (
            "<b>RR TRADER — STOP LOSS HIT</b>\n\n"
            f"<b>{symbol.upper()}</b>\n"
            f"Direction: "
            f"<b>{direction.upper()}</b>\n"
            f"SL: <code>{price}</code>"
        )

        return await self.send_message(
            message
        )

    # =====================================================
    # SIGNAL CLOSED
    # =====================================================

    async def send_signal_closed(
        self,
        symbol: str,
        direction: str,
        result: str,
        entry: float | None = None,
        exit_price: float | None = None,
        pnl_percent: float | None = None,
    ) -> dict[str, Any]:

        lines = [
            "<b>RR TRADER — SIGNAL CLOSED</b>",
            "",
            f"<b>{symbol.upper()}</b>",
            f"Direction: "
            f"<b>{direction.upper()}</b>",
            f"Result: "
            f"<b>{result.upper()}</b>",
        ]

        if entry is not None:
            lines.append(
                f"Entry: <code>{entry}</code>"
            )

        if exit_price is not None:
            lines.append(
                f"Exit: "
                f"<code>{exit_price}</code>"
            )

        if pnl_percent is not None:
            lines.append(
                f"PnL: "
                f"<b>{pnl_percent}%</b>"
            )

        return await self.send_message(
            "\n".join(lines)
        )

    # =====================================================
    # GENERAL REPORT
    # =====================================================

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

    # =====================================================
    # TEST CONNECTION
    # =====================================================

    async def test_connection(
        self,
    ) -> dict[str, Any]:

        return await self.send_message(
            (
                "✅ <b>RR Trader Telegram "
                "Connected</b>\n\n"
                "Telegram notification system "
                "is working."
            )
        )

    # =====================================================
    # STATUS
    # =====================================================

    def status(
        self,
    ) -> dict[str, Any]:

        return {
            "enabled": self.enabled,
            "configured": bool(
                self.bot_token
                and self.chat_id
            ),
            "status": (
                "ready"
                if self.enabled
                else "disabled"
            ),
        }


telegram_service = TelegramService()


async def send_telegram_message(
    message: str,
) -> dict[str, Any]:

    return await (
        telegram_service.send_message(
            message
        )
    )


__all__ = [
    "TelegramService",
    "telegram_service",
    "send_telegram_message",
]
