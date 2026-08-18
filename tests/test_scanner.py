from __future__ import annotations

import pytest

from backend.app.services.scanner import MarketScanner


def test_core_timeframes_are_locked() -> None:
    assert MarketScanner.CORE_TIMEFRAMES == (
        "15m",
        "1h",
        "4h",
    )


def test_timeframe_weights_total_one() -> None:
    total = sum(
        MarketScanner.TIMEFRAME_WEIGHTS.values()
    )

    assert total == pytest.approx(
        1.0
    )


def test_normalize_symbol() -> None:
    scanner = MarketScanner()

    assert scanner.normalize_symbol(
        "btc"
    ) == "BTCUSDT"

    assert scanner.normalize_symbol(
        "BTC/USDT"
    ) == "BTCUSDT"

    assert scanner.normalize_symbol(
        "ethusdt"
    ) == "ETHUSDT"


def test_normalize_market() -> None:
    scanner = MarketScanner()

    assert scanner.normalize_market(
        "futures"
    ) == "futures"

    assert scanner.normalize_market(
        "SPOT"
    ) == "spot"


def test_invalid_market() -> None:
    scanner = MarketScanner()

    with pytest.raises(
        ValueError,
        match="market must be",
    ):
        scanner.normalize_market(
            "invalid"
        )


@pytest.mark.asyncio
async def test_scan_returns_foundation_result(
) -> None:
    scanner = MarketScanner()

    result = await scanner.scan(
        market="futures"
    )

    assert result["success"] is True
    assert result["market"] == "futures"

    assert result[
        "core_timeframes"
    ] == [
        "15m",
        "1h",
        "4h",
    ]

    assert (
        result["universe_mode"]
        == "FULL_MARKET"
    )

    assert (
        result["deep_analysis_limit"]
        > 0
    )
