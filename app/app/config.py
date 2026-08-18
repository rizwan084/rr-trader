from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    # =========================================================
    # APPLICATION
    # =========================================================

    app_name: str = os.getenv(
        "APP_NAME",
        "RR Trader Live Scanner",
    )

    app_version: str = os.getenv(
        "APP_VERSION",
        "2.0.0",
    )

    # =========================================================
    # BINANCE
    # =========================================================

    binance_futures_url: str = os.getenv(
        "BINANCE_FUTURES_URL",
        "https://fapi.binance.com",
    )

    binance_spot_url: str = os.getenv(
        "BINANCE_SPOT_URL",
        "https://api.binance.com",
    )

    # =========================================================
    # HTTP
    # =========================================================

    request_timeout: float = float(
        os.getenv("REQUEST_TIMEOUT", "15")
    )

    # =========================================================
    # SIGNAL ENGINE
    # =========================================================

    min_confidence: int = int(
        os.getenv("MIN_CONFIDENCE", "85")
    )

    # =========================================================
    # AUTO SCANNER
    # =========================================================

    auto_scan_interval: int = int(
        os.getenv("AUTO_SCAN_INTERVAL", "60")
    )

    auto_scan_coins: int = int(
        os.getenv("AUTO_SCAN_COINS", "6")
    )

    # =========================================================
    # CACHE
    # =========================================================

    cache_seconds: int = int(
        os.getenv("CACHE_SECONDS", "20")
    )

    # =========================================================
    # DEFAULT ANALYSIS
    # =========================================================

    default_market: str = os.getenv(
        "DEFAULT_MARKET",
        "futures",
    ).strip().lower()

    default_interval: str = os.getenv(
        "DEFAULT_INTERVAL",
        "15m",
    )

    default_candle_limit: int = int(
        os.getenv("DEFAULT_CANDLE_LIMIT", "200")
    )

    # =========================================================
    # AI ASSISTANT
    # =========================================================

    ai_enabled: bool = _env_bool(
        "AI_ENABLED",
        False,
    )

    openai_api_key: str = os.getenv(
        "OPENAI_API_KEY",
        "",
    )

    ai_model: str = os.getenv(
        "AI_MODEL",
        "gpt-5.6",
    )

    ai_timeout: float = float(
        os.getenv("AI_TIMEOUT", "30")
    )

    # =========================================================
    # SIGNAL MEMORY
    # =========================================================

    signal_memory_enabled: bool = _env_bool(
        "SIGNAL_MEMORY_ENABLED",
        True,
    )

    signal_monitor_enabled: bool = _env_bool(
        "SIGNAL_MONITOR_ENABLED",
        True,
    )

    signal_monitor_interval: int = int(
        os.getenv("SIGNAL_MONITOR_INTERVAL", "60")
    )

    # =========================================================
    # TELEGRAM
    # =========================================================

    telegram_enabled: bool = _env_bool(
        "TELEGRAM_ENABLED",
        False,
    )

    telegram_bot_token: str = os.getenv(
        "TELEGRAM_BOT_TOKEN",
        "",
    )

    telegram_chat_id: str = os.getenv(
        "TELEGRAM_CHAT_ID",
        "",
    )

    telegram_timeout: float = float(
        os.getenv("TELEGRAM_TIMEOUT", "15")
    )

    telegram_signal_notifications: bool = _env_bool(
        "TELEGRAM_SIGNAL_NOTIFICATIONS",
        True,
    )

    telegram_result_notifications: bool = _env_bool(
        "TELEGRAM_RESULT_NOTIFICATIONS",
        True,
    )

    # =========================================================
    # VALIDATION
    # =========================================================

    def validate(self) -> None:
        if not 0 <= self.min_confidence <= 100:
            raise ValueError(
                "MIN_CONFIDENCE must be between 0 and 100."
            )

        if self.auto_scan_interval < 1:
            raise ValueError(
                "AUTO_SCAN_INTERVAL must be at least 1 second."
            )

        if self.auto_scan_coins < 1:
            raise ValueError(
                "AUTO_SCAN_COINS must be at least 1."
            )

        if self.cache_seconds < 0:
            raise ValueError(
                "CACHE_SECONDS cannot be negative."
            )

        if self.default_market not in {"spot", "futures"}:
            raise ValueError(
                "DEFAULT_MARKET must be 'spot' or 'futures'."
            )

        if self.default_candle_limit < 30:
            raise ValueError(
                "DEFAULT_CANDLE_LIMIT must be at least 30."
            )

        if self.signal_monitor_interval < 10:
            raise ValueError(
                "SIGNAL_MONITOR_INTERVAL must be at least 10 seconds."
            )

        # AI is optional.
        # Do not crash the entire server if the API key
        # has not been configured in Render yet.
        if self.ai_enabled and not self.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY is required when AI_ENABLED=true."
            )

        # Telegram is optional.
        # Only validate credentials when explicitly enabled.
        if self.telegram_enabled:
            if not self.telegram_bot_token:
                raise ValueError(
                    "TELEGRAM_BOT_TOKEN is required when "
                    "TELEGRAM_ENABLED=true."
                )

            if not self.telegram_chat_id:
                raise ValueError(
                    "TELEGRAM_CHAT_ID is required when "
                    "TELEGRAM_ENABLED=true."
                )


# =============================================================
# GLOBAL SETTINGS INSTANCE
# =============================================================

settings = Settings()
settings.validate()


__all__ = [
    "Settings",
    "settings",
]
