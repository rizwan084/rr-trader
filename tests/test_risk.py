from __future__ import annotations

from backend.app.services.risk_engine import RiskEngine


def test_position_size_calculation() -> None:
    engine = RiskEngine(
        risk_per_trade_percent=1.0
    )

    position_size = (
        engine.calculate_position_size(
            account_balance=10000,
            entry=100,
            stop_loss=95,
        )
    )

    # 1% of 10,000 = 100 risk.
    # Stop distance = 5.
    # Position size = 20 units.
    assert position_size == 20.0


def test_invalid_account_balance_is_rejected() -> None:
    engine = RiskEngine()

    result = engine.evaluate(
        account_balance=0,
        entry=100,
        stop_loss=95,
    )

    assert result.allowed is False

    assert (
        "INVALID_ACCOUNT_BALANCE"
        in result.failures
    )


def test_invalid_stop_is_rejected() -> None:
    engine = RiskEngine()

    result = engine.evaluate(
        account_balance=10000,
        entry=100,
        stop_loss=100,
    )

    assert result.allowed is False

    assert (
        "ZERO_STOP_DISTANCE"
        in result.failures
    )


def test_excessive_risk_is_rejected() -> None:
    engine = RiskEngine(
        risk_per_trade_percent=6.0
    )

    result = engine.evaluate(
        account_balance=10000,
        entry=100,
        stop_loss=95,
    )

    assert result.allowed is False

    assert (
        "EXCESSIVE_PER_TRADE_RISK"
        in result.failures
    )


def test_max_open_positions_is_rejected() -> None:
    engine = RiskEngine(
        max_open_positions=5
    )

    result = engine.evaluate(
        account_balance=10000,
        entry=100,
        stop_loss=95,
        current_open_positions=5,
    )

    assert result.allowed is False

    assert (
        "MAX_OPEN_POSITIONS"
        in result.failures
    )


def test_valid_risk_passes() -> None:
    engine = RiskEngine(
        risk_per_trade_percent=1.0,
        max_portfolio_exposure_percent=10.0,
        max_open_positions=5,
    )

    result = engine.evaluate(
        account_balance=10000,
        entry=100,
        stop_loss=95,
        current_open_positions=2,
        portfolio_exposure_percent=4.0,
    )

    assert result.allowed is True

    assert result.failures == []

    assert result.position_size == 20.0
