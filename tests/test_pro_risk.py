from app.services.pro_risk_engine import ProRiskEngine


def test_weak_signal_is_rejected():
    engine = ProRiskEngine(min_confidence=90, min_rr=2.0, max_risk_percent=1.0)
    decision = engine.evaluate(
        {
            "symbol": "BTCUSDT",
            "direction": "LONG",
            "entry": 100,
            "stop_loss": 99,
            "tp1": 102,
            "confidence": 86,
            "risk_reward": 1.4,
            "setup": "NONE",
            "volume_ratio": 0.6,
        },
        account_balance=50,
    )
    assert not decision.allowed
    assert "CONFIDENCE_BELOW_PRO_THRESHOLD" in decision.failures
    assert "RISK_REWARD_BELOW_PRO_THRESHOLD" in decision.failures
    assert "BAD_TRADE_LOCATION" in decision.failures


def test_quality_signal_passes():
    engine = ProRiskEngine(min_confidence=90, min_rr=2.0, max_risk_percent=1.0)
    decision = engine.evaluate(
        {
            "symbol": "BTCUSDT",
            "direction": "LONG",
            "entry": 100,
            "stop_loss": 98,
            "tp1": 104,
            "confidence": 94,
            "risk_reward": 2.0,
            "setup": "SUPPORT",
            "structure_location": "SUPPORT",
            "mtf_confirmation": True,
            "volume_ratio": 1.2,
            "momentum_score": 70,
        },
        account_balance=50,
    )
    assert decision.allowed
    assert decision.position_size == 0.25
    assert decision.risk_amount == 0.5
