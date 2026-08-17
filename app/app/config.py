from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "RR Trader"
    app_version: str = "1.0.0"
    environment: str = "development"

    binance_futures_url: str = "https://fapi.binance.com"
    binance_spot_url: str = "https://api.binance.com"

    request_timeout: float = 10.0

    min_confidence: int = 85
    auto_scan_interval: int = 60
    auto_scan_coins: int = 6
    cache_seconds: int = 20

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
