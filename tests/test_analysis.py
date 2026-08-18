from __future__ import annotations

from backend.app.models.analysis import (
    AnalysisResult,
    MTFAnalysis,
    TimeframeAnalysis,
)
from backend.app.services.analysis_engine import (
    AnalysisEngine,
)


def test_analysis_engine_has_24_points() -> None:
    points = AnalysisEngine.all_points()

    assert len(points) == 24


def test_market_points_are_20() -> None:
    assert len(
        AnalysisEngine.MARKET_POINTS
    ) == 20


def test_risk_points_are_4() -> None:
    assert len(
        AnalysisEngine.RISK_POINTS
    ) == 4


def test_core_timeframes() -> None:
    fifteen = TimeframeAnalysis(
        timeframe="15m",
        direction="LONG",
        confidence=90,
        strength=1.0,
    )

    one_hour = TimeframeAnalysis(
        timeframe="1h",
        direction="LONG",
        confidence=88,
        strength=1.0,
    )

    four_hour = TimeframeAnalysis(
        timeframe="4h",
        direction="LONG",
        confidence=92,
        strength=1.0,
    )

    mtf = MTFAnalysis(
        fifteen_minute=fifteen,
        one_hour=one_hour,
        four_hour=four_hour,
    )

    result = mtf.to_dict()

    assert result[
        "core_timeframes"
    ] == [
        "15m",
        "1h",
        "4h",
    ]

    assert result[
        "direction"
    ] == "LONG"

    assert result[
        "aligned"
    ] is True

    assert result[
        "status"
    ] == "ALIGNED"

    assert result[
        "agreement_ratio"
    ] == 1.0


def test_mtf_conflict() -> None:
    mtf = MTFAnalysis(
        fifteen_minute=TimeframeAnalysis(
            timeframe="15m",
            direction="LONG",
        ),
        one_hour=TimeframeAnalysis(
            timeframe="1h",
            direction="LONG",
        ),
        four_hour=TimeframeAnalysis(
            timeframe="4h",
            direction="SHORT",
        ),
    )

    result = mtf.to_dict()

    assert result[
        "aligned"
    ] is False

    assert result[
        "status"
    ] == "CONFLICT"

    assert result[
        "critical_conflict"
    ] is True

    assert result[
        "agreement_ratio"
    ] == 2 / 3


def test_empty_analysis_result() -> None:
    result = AnalysisEngine.empty_result(
        symbol="BTCUSDT",
        market="futures",
    )

    assert result[
        "success"
    ] is True

    assert result[
        "symbol"
    ] == "BTCUSDT"

    assert result[
        "market"
    ] == "futures"

    assert len(
        result["points"]
    ) == 24


def test_analysis_result_serialization() -> None:
    result = AnalysisResult(
        symbol="BTCUSDT",
        market="futures",
        direction="LONG",
        confidence=91.5,
        publishable=True,
        entry=100000.0,
        stop_loss=98000.0,
        tp1=104000.0,
        tp2=108000.0,
        tp3=112000.0,
        risk_reward=2.0,
    )

    data = result.to_dict()

    assert data[
        "success"
    ] is True

    assert data[
        "symbol"
    ] == "BTCUSDT"

    assert data[
        "direction"
    ] == "LONG"

    assert data[
        "confidence"
    ] == 91.5

    assert data[
        "publishable"
    ] is True
