from __future__ import annotations

from backend.app.services.trade_engine import TradeEngine


def test_trade_engine_is_paper_only() -> None:
    engine = TradeEngine()

    status = engine.get_status()

    assert status["mode"] == "paper"
    assert status["live_trading"] is False


def test_trade_engine_config() -> None:
    engine = TradeEngine(
        min_confidence=85.0,
        min_risk_reward=2.0,
        max_spread_percent=0.10,
    )

    config = engine.get_config()

    assert config[
        "min_confidence"
    ] == 85.0

    assert config[
        "min_risk_reward"
    ] == 2.0

    assert config[
        "max_spread_percent"
    ] == 0.10


def test_low_confidence_is_rejected() -> None:
    engine = TradeEngine()

    result = engine.evaluate_trade(
        {
            "symbol": "BTCUSDT",
            "direction": "LONG",
            "confidence": 70,
            "risk_reward": 3.0,
            "spread_percent": 0.01,
            "mtf_aligned": True,
            "stop_valid": True,
        }
    )

    assert result[
        "decision"
    ] == "NO_TRADE"

    assert (
        "LOW_CONFIDENCE"
        in result["critical_failures"]
    )


def test_mtf_conflict_is_rejected() -> None:
    engine = TradeEngine()

    result = engine.evaluate_trade(
        {
            "symbol": "BTCUSDT",
            "direction": "LONG",
            "confidence": 92,
            "risk_reward": 3.0,
            "spread_percent": 0.01,
            "mtf_aligned": False,
            "stop_valid": True,
        }
    )

    assert result[
        "decision"
    ] == "NO_TRADE"

    assert (
        "MTF_CONFLICT"
        in result["critical_failures"]
    )


def test_good_signal_can_be_execution_candidate() -> None:
    engine = TradeEngine()

    result = engine.evaluate_trade(
        {
            "symbol": "BTCUSDT",
            "direction": "LONG",
            "confidence": 98,
            "risk_reward": 3.0,
            "spread_percent": 0.01,
            "mtf_aligned": True,
            "stop_valid": True,
        }
    )

    assert result[
        "decision"
    ] == "EXECUTE_CANDIDATE"

    assert result[
        "critical_failures"
    ] == []


def test_paper_trade_opens() -> None:
    engine = TradeEngine()

    result = engine.open_paper_trade(
        {
            "symbol": "BTCUSDT",
            "direction": "LONG",
            "confidence": 98,
            "risk_reward": 3.0,
            "spread_percent": 0.01,
            "mtf_aligned": True,
            "stop_valid": True,
            "entry": 100000,
            "stop_loss": 98000,
            "tp1": 104000,
            "tp2": 108000,
            "tp3": 112000,
        }
    )

    assert result[
        "success"
    ] is True

    assert result[
        "opened"
    ] is True

    assert len(
        engine.get_open_positions()
    ) == 1
