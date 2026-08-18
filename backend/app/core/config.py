from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(
    name: str,
    default: bool,
) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


@dataclass(frozen=True)
class Settings:

    # =====================================================
    # APPLICATION
    # =====================================================

    app_name: str = os.getenv(
        "APP_NAME",
        "RR Trader",
    )

    app_version: str = os.getenv(
        "APP_VERSION",
        "1.0.0",
    )

    # =====================================================
    # BINANCE
    # =====================================================

    binance_futures_url: str = os.getenv(
        "BINANCE_FUTURES_URL",
        "https://fapi.binance.com",
    )

    binance_spot_url: str = os.getenv(
        "BINANCE_SPOT_URL",
        "https://api.binance.com",
    )

    # =====================================================
    # HTTP / PERFORMANCE
    # =====================================================

    request_timeout: float = float(
        os.getenv(
            "REQUEST_TIMEOUT",
            "15",
        )
    )

    http_max_connections: int = int(
        os.getenv(
            "HTTP_MAX_CONNECTIONS",
            "50",
        )
    )

    http_max_keepalive: int = int(
        os.getenv(
            "HTTP_MAX_KEEPALIVE",
            "20",
        )
    )

    # =====================================================
    # CORE MULTI-TIMEFRAME
    # =====================================================

    core_timeframes: tuple[
        str,
        str,
        str,
    ] = (
        "15m",
        "1h",
        "4h",
    )

    # =====================================================
    # SCANNER
    # =====================================================

    auto_scan_interval: int = int(
        os.getenv(
            "AUTO_SCAN_INTERVAL",
            "60",
        )
    )

    deep_analysis_limit: int = int(
        os.getenv(
            "DEEP_ANALYSIS_LIMIT",
            "6",
        )
    )

    min_confidence: float = float(
        os.getenv(
            "MIN_CONFIDENCE",
            "85",
        )
    )

    # =====================================================
    # AI
    # =====================================================

    ai_enabled: bool = _env_bool(
        "AI_ENABLED",
        False,
    )

    openai_api_key: str = os.getenv(
        "OPENAI_API_KEY",
        "",
    )

    # =====================================================
    # TELEGRAM
    # =====================================================

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


settings = Settings()
