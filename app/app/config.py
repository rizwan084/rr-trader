from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass
class Settings:
    """
    RR Trader application configuration.

    Supports:
    - Binance Futures
    - Binance Spot
    - Scanner settings
    - Signal confidence
    - Request/cache settings
    """

    # ---------------------------------------------------------
    # APPLICATION
    # ---------------------------------------------------------

    app_name: str = os.getenv(
        "APP_NAME",
        "RR Trader Live Scanner",
    )

    app_version: str = os.getenv(
        "APP_VERSION",
        "1.0.0",
    )

    # ---------------------------------------------------------
    # BINANCE
    # ---------------------------------------------------------

    binance_futures_url: str = os.getenv(
        "BINANCE_FUTURES_URL",
        "https://fapi.binance.com",
    )

    binance_spot_url: str = os.getenv(
        "BINANCE_SPOT_URL",
        "https://api.binance.com",
    )

    # ---------------------------------------------------------
    # HTTP
    # ---------------------------------------------------------

    request_timeout: float = float(
        os.getenv(
            "REQUEST_TIMEOUT",
            "15",
        )
    )

    # ---------------------------------------------------------
    # SIGNAL
    # ---------------------------------------------------------

    min_confidence: int = int(
        os.getenv(
            "MIN_CONFIDENCE",
            "85",
        )
    )

    # ---------------------------------------------------------
    # AUTO SCANNER
    # ---------------------------------------------------------

    auto_scan_interval: int = int(
        os.getenv(
            "AUTO_SCAN_INTERVAL",
            "60",
        )
    )

    auto_scan_coins: int = int(
        os.getenv(
            "AUTO_SCAN_COINS",
            "6",
        )
    )

    # ---------------------------------------------------------
    # CACHE
    # ---------------------------------------------------------

    cache_seconds: int = int(
        os.getenv(
            "CACHE_SECONDS",
            "20",
        )
    )

    # ---------------------------------------------------------
    # DEFAULT ANALYSIS
    # ---------------------------------------------------------

    default_market: str = os.getenv(
        "DEFAULT_MARKET",
        "futures",
    )

    default_interval: str = os.getenv(
        "DEFAULT_INTERVAL",
        "15m",
    )

    default_candle_limit: int = int(
        os.getenv(
            "DEFAULT_CANDLE_LIMIT",
            "200",
        )
    )

    # ---------------------------------------------------------
    # VALIDATION
    # ---------------------------------------------------------

    def validate(self) -> None:
        """Validate important application settings."""

        if self.min_confidence < 0 or self.min_confidence > 100:
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

        if self.default_market not in {
            "spot",
            "futures",
        }:
            raise ValueError(
                "DEFAULT_MARKET must be 'spot' or 'futures'."
            )

        if self.default_candle_limit < 30:
            raise ValueError(
                "DEFAULT_CANDLE_LIMIT must be at least 30."
            )


settings = Settings()
settings.validate()


__all__ = [
    "Settings",
    "settings",
]
