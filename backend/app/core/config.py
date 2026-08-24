from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "RR Trader")
    app_version: str = os.getenv("APP_VERSION", "1.0.0")

    binance_futures_url: str = os.getenv("BINANCE_FUTURES_URL", "https://fapi.binance.com")
    binance_spot_url: str = os.getenv("BINANCE_SPOT_URL", "https://api.binance.com")
    binance_api_key: str = os.getenv("BINANCE_API_KEY", "")
    binance_api_secret: str = os.getenv("BINANCE_API_SECRET", "")
    binance_recv_window: int = int(os.getenv("BINANCE_RECV_WINDOW", "5000"))

    # Safety: live execution is OFF unless explicitly enabled in the deployment.
    trading_mode: str = os.getenv("TRADING_MODE", "paper").strip().lower()
    live_trading_enabled: bool = _env_bool("LIVE_TRADING_ENABLED", False)
    binance_position_mode: str = os.getenv("BINANCE_POSITION_MODE", "ONE_WAY").strip().upper()
    default_leverage: int = max(1, int(os.getenv("DEFAULT_LEVERAGE", "3")))
    max_leverage: int = max(1, int(os.getenv("MAX_LEVERAGE", "5")))
    require_pro_risk_gate: bool = _env_bool("REQUIRE_PRO_RISK_GATE", True)

    request_timeout: float = float(os.getenv("REQUEST_TIMEOUT", "30"))
    http_max_connections: int = int(os.getenv("HTTP_MAX_CONNECTIONS", "50"))
    http_max_keepalive: int = int(os.getenv("HTTP_MAX_KEEPALIVE", "20"))

    core_timeframes: tuple[str, str, str] = ("15m", "1h", "4h")

    auto_scan_interval: int = int(os.getenv("AUTO_SCAN_INTERVAL", "60"))
    deep_analysis_limit: int = int(os.getenv("DEEP_ANALYSIS_LIMIT", "6"))
    min_confidence: float = float(os.getenv("MIN_CONFIDENCE", "85"))
    min_risk_reward: float = max(1.1, float(os.getenv("MIN_RISK_REWARD", "1.10")))

    # Existing risk engine compatibility settings.
    risk_per_trade_percent: float = float(os.getenv("RISK_PER_TRADE_PERCENT", "1.0"))
    max_portfolio_exposure_percent: float = float(os.getenv("MAX_PORTFOLIO_EXPOSURE_PERCENT", "10.0"))
    max_open_positions: int = int(os.getenv("MAX_OPEN_POSITIONS", "5"))
    max_daily_loss_percent: float = float(os.getenv("MAX_DAILY_LOSS_PERCENT", "3.0"))

    # Professional challenge risk policy.
    challenge_enabled: bool = _env_bool("CHALLENGE_ENABLED", True)
    challenge_start_balance: float = float(os.getenv("CHALLENGE_START_BALANCE", "50"))
    challenge_target_balance: float = float(os.getenv("CHALLENGE_TARGET_BALANCE", "1000"))
    pro_min_confidence: float = float(os.getenv("PRO_MIN_CONFIDENCE", "90"))
    pro_min_risk_reward: float = float(os.getenv("PRO_MIN_RISK_REWARD", "2.0"))
    pro_risk_per_trade_percent: float = min(1.0, float(os.getenv("PRO_RISK_PER_TRADE_PERCENT", "1.0")))
    pro_max_open_positions: int = int(os.getenv("PRO_MAX_OPEN_POSITIONS", "3"))
    pro_max_daily_loss_percent: float = float(os.getenv("PRO_MAX_DAILY_LOSS_PERCENT", "2.0"))
    pro_max_consecutive_losses: int = int(os.getenv("PRO_MAX_CONSECUTIVE_LOSSES", "3"))

    # Post/event automation. Kept disabled until the publisher credentials are configured.
    auto_trade_posts_enabled: bool = _env_bool("AUTO_TRADE_POSTS_ENABLED", False)
    trade_post_webhook_url: str = os.getenv("TRADE_POST_WEBHOOK_URL", "")
    trade_post_webhook_token: str = os.getenv("TRADE_POST_WEBHOOK_TOKEN", "")

    # Supabase - server-side only for accountability / lifecycle data.
    supabase_url: str = os.getenv("SUPABASE_URL", "https://orarigjdzfrdsehcnkdb.supabase.co").strip().rstrip("/")
    supabase_service_role_key: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

    # =====================================================
    # FOREX / GOLD — MT5 bridge on Windows/VPS
    # =====================================================
    mt5_bridge_url: str = os.getenv("MT5_BRIDGE_URL", "")
    mt5_bridge_token: str = os.getenv("MT5_BRIDGE_TOKEN", "")
    forex_primary_symbol: str = os.getenv("FOREX_PRIMARY_SYMBOL", "XAUUSD").upper()
    forex_timeframes: str = os.getenv("FOREX_TIMEFRAMES", "1m,3m,5m,15m")

    # =====================================================
    # AI
    # =====================================================
    ai_enabled: bool = _env_bool("AI_ENABLED", True)
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5.6")
    openai_image_model: str = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2")
    openai_api_url: str = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/responses")
    openai_image_api_url: str = os.getenv("OPENAI_IMAGE_API_URL", "https://api.openai.com/v1/images/generations")
    ai_max_output_tokens: int = int(os.getenv("AI_MAX_OUTPUT_TOKENS", "2500"))

    # =====================================================
    # TELEGRAM
    # =====================================================
    telegram_enabled: bool = _env_bool("TELEGRAM_ENABLED", False)
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")


settings = Settings()
