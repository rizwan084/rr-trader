from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings
from app.services.market_data import market_data_service
from app.services.market_scanner import MarketScanner
from app.services.master_analysis import (
    master_analysis_engine,
)
from app.services.post_generator import (
    post_generator,
)
from app.services.signal_memory import (
    signal_memory,
)


router = APIRouter()


# =========================================================
# MARKET SCANNER
# =========================================================

market_scanner = MarketScanner(
    market_data_service
)


# =========================================================
# CONSTANTS
# =========================================================

MIN_PUBLISH_CONFIDENCE = float(
    settings.min_confidence
)

CORE_TIMEFRAMES = (
    "15m",
    "1h",
    "4h",
)


# =========================================================
# HELPERS
# =========================================================

def normalize_market(
    market: str,
) -> str:

    clean = str(
        market or ""
    ).lower().strip()

    if clean not in {
        "spot",
        "futures",
    }:
        raise HTTPException(
            status_code=400,
            detail=(
                "market must be "
                "'spot' or 'futures'"
            ),
        )

    return clean


def normalize_symbol(
    symbol: str,
) -> str:

    clean = (
        str(symbol or "")
        .upper()
        .replace(
            "/",
            "",
        )
        .replace(
            "-",
            "",
        )
        .strip()
    )

    if not clean:
        raise HTTPException(
            status_code=400,
            detail="symbol is required",
        )

    if not clean.endswith(
        "USDT"
    ):
        clean = f"{clean}USDT"

    return clean


def safe_float(
    value: Any,
    default: float = 0.0,
) -> float:

    try:
        return float(value)

    except (
        TypeError,
        ValueError,
    ):
        return default


def build_trade_levels(
    analysis: dict[str, Any],
) -> dict[str, Any]:
    """
    Build deterministic Entry / SL / TP levels from
    current price + 15m ATR.

    This is a preliminary trade-level model.
    Structural stop refinement can be added later.

    Long:
        SL below entry
        TP1 = 1.5R
        TP2 = 2.5R
        TP3 = 3.5R

    Short:
        mirrored logic.
    """

    direction = str(
        analysis.get(
            "direction",
            "NEUTRAL",
        )
    ).upper()

    timeframes = analysis.get(
        "timeframes",
        {},
    )

    fifteen = (
        timeframes.get(
            "15m",
            {}
        )
        if isinstance(
            timeframes,
            dict,
        )
        else {}
    )

    indicators = (
        fifteen.get(
            "indicators",
            {},
        )
        if isinstance(
            fifteen,
            dict,
        )
        else {}
    )

    structure = (
        fifteen.get(
            "structure",
            {},
        )
        if isinstance(
            fifteen,
            dict,
        )
        else {}
    )

    price = safe_float(
        indicators.get(
            "price",
            0,
        )
    )

    atr = safe_float(
        indicators.get(
            "atr",
            0,
        )
    )

    if price <= 0:
        return {
            "entry": 0.0,
            "stop_loss": 0.0,
            "tp1": 0.0,
            "tp2": 0.0,
            "tp3": 0.0,
            "risk_reward": 0.0,
            "stop_quality": "INVALID",
        }

    # -----------------------------------------------------
    # ATR fallback
    # -----------------------------------------------------

    if atr <= 0:

        atr_percent = safe_float(
            indicators.get(
                "atr_percent",
                0,
            )
        )

        if atr_percent > 0:
            atr = (
                price
                * atr_percent
                / 100.0
            )

    # Conservative fallback if ATR is unavailable.
    if atr <= 0:
        atr = price * 0.005

    # -----------------------------------------------------
    # Structural support / resistance
    # -----------------------------------------------------

    sr = (
        structure.get(
            "support_resistance",
            {},
        )
        if isinstance(
            structure,
            dict,
        )
        else {}
    )

    support = safe_float(
        sr.get(
            "support",
            0,
        )
    )

    resistance = safe_float(
        sr.get(
            "resistance",
            0,
        )
    )

    # -----------------------------------------------------
    # LONG
    # -----------------------------------------------------

    if direction == "LONG":

        entry = price

        structural_stop = (
            support - atr * 0.25
            if support > 0
            and support < entry
            else 0.0
        )

        atr_stop = (
            entry - atr * 1.5
        )

        if (
            structural_stop > 0
            and structural_stop < entry
        ):

            stop_loss = max(
                structural_stop,
                atr_stop,
            )

        else:

            stop_loss = atr_stop

        risk = abs(
            entry - stop_loss
        )

        if risk <= 0:
            risk = entry * 0.005
            stop_loss = (
                entry - risk
            )

        tp1 = entry + (
            risk * 1.5
        )

        tp2 = entry + (
            risk * 2.5
        )

        tp3 = entry + (
            risk * 3.5
        )

        stop_quality = (
            "VALID"
            if stop_loss < entry
            else "INVALID"
        )

        rr = (
            abs(
                tp2 - entry
            )
            / risk
            if risk > 0
            else 0.0
        )

    # -----------------------------------------------------
    # SHORT
    # -----------------------------------------------------

    elif direction == "SHORT":

        entry = price

        structural_stop = (
            resistance + atr * 0.25
            if resistance > entry
            else 0.0
        )

        atr_stop = (
            entry + atr * 1.5
        )

        if (
            structural_stop > entry
            and structural_stop > 0
        ):

            stop_loss = min(
                structural_stop,
                atr_stop,
            )

        else:

            stop_loss = atr_stop

        risk = abs(
            stop_loss - entry
        )

        if risk <= 0:
            risk = entry * 0.005
            stop_loss = (
                entry + risk
            )

        tp1 = entry - (
            risk * 1.5
        )

        tp2 = entry - (
            risk * 2.5
        )

        tp3 = entry - (
            risk * 3.5
        )

        stop_quality = (
            "VALID"
            if stop_loss > entry
            else "INVALID"
        )

        rr = (
            abs(
                entry - tp2
            )
            / risk
            if risk > 0
            else 0.0
        )

    # -----------------------------------------------------
    # NO TRADE
    # -----------------------------------------------------

    else:

        return {
            "entry": price,
            "stop_loss": 0.0,
            "tp1": 0.0,
            "tp2": 0.0,
            "tp3": 0.0,
            "risk_reward": 0.0,
            "stop_quality": "NOT_APPLICABLE",
        }

    return {
        "entry": round(
            entry,
            8,
        ),
        "stop_loss": round(
            stop_loss,
            8,
        ),
        "tp1": round(
            tp1,
            8,
        ),
        "tp2": round(
            tp2,
            8,
        ),
        "tp3": round(
            tp3,
            8,
        ),
        "risk_reward": round(
            rr,
            4,
        ),
        "stop_quality": stop_quality,
        "atr": round(
            atr,
            8,
        ),
    }


def build_24_point_result(
    analysis: dict[str, Any],
    levels: dict[str, Any],
) -> dict[str, Any]:
    """
    Build the canonical RR Trader 24-point output.

    1-20 = market confirmations
    21-24 = risk / execution gates
    """

    direction = str(
        analysis.get(
            "direction",
            "NEUTRAL",
        )
    ).upper()

    confidence = safe_float(
        analysis.get(
            "confidence",
            0,
        )
    )

    mtf = analysis.get(
        "multi_timeframe",
        {},
    )

    derivatives = analysis.get(
        "derivatives",
        {},
    )

    order_book = analysis.get(
        "order_book",
        {},
    )

    liquidations = analysis.get(
        "liquidations",
        {},
    )

    timeframes = analysis.get(
        "timeframes",
        {},
    )

    points: dict[
        str,
        dict[str, Any],
    ] = {}

    # =====================================================
    # 1 — MARKET REGIME
    # =====================================================

    four_hour = (
        timeframes.get(
            "4h",
            {},
        )
        if isinstance(
            timeframes,
            dict,
        )
        else {}
    )

    regime_direction = str(
        four_hour.get(
            "direction",
            "NEUTRAL",
        )
    ).upper()

    regime = (
        "TREND_UP"
        if regime_direction == "LONG"
        else "TREND_DOWN"
        if regime_direction == "SHORT"
        else "RANGE"
    )

    points["1"] = {
        "number": 1,
        "name": "Market Regime",
        "category": "market",
        "status": "CONFIRMED"
        if regime_direction
        in {
            "LONG",
            "SHORT",
        }
        else "NEUTRAL",
        "direction": (
            regime_direction
            if regime_direction
            in {
                "LONG",
                "SHORT",
            }
            else "NEUTRAL"
        ),
        "value": regime,
    }

    # =====================================================
    # 2 — MARKET STRUCTURE
    # =====================================================

    one_hour = (
        timeframes.get(
            "1h",
            {},
        )
        if isinstance(
            timeframes,
            dict,
        )
        else {}
    )

    one_hour_structure = (
        one_hour.get(
            "structure",
            {},
        )
        if isinstance(
            one_hour,
            dict,
        )
        else {}
    )

    structure_direction = str(
        one_hour.get(
            "direction",
            "NEUTRAL",
        )
    ).upper()

    points["2"] = {
        "number": 2,
        "name": "Market Structure",
        "category": "market",
        "status": "CONFIRMED"
        if structure_direction
        in {
            "LONG",
            "SHORT",
        }
        else "NEUTRAL",
        "direction": (
            structure_direction
            if structure_direction
            in {
                "LONG",
                "SHORT",
            }
            else "NEUTRAL"
        ),
        "value": (
            one_hour_structure.get(
                "structure",
                "UNKNOWN",
            )
            if isinstance(
                one_hour_structure,
                dict,
            )
            else "UNKNOWN"
        ),
    }

    # =====================================================
    # 3 — MTF
    # =====================================================

    points["3"] = {
        "number": 3,
        "name": (
            "Multi-Timeframe Confirmation"
        ),
        "category": "market",
        "status": (
            "CONFIRMED"
            if mtf.get(
                "aligned",
                False,
            )
            else "CONFLICT"
        ),
        "direction": (
            mtf.get(
                "direction",
                "NEUTRAL",
            )
        ),
        "agreement_ratio": mtf.get(
            "agreement_ratio",
            0,
        ),
        "weighted_confidence": mtf.get(
            "weighted_confidence",
            0,
        ),
    }

    # =====================================================
    # 4 — ENTRY LOCATION
    # =====================================================

    fifteen = (
        timeframes.get(
            "15m",
            {},
        )
        if isinstance(
            timeframes,
            dict,
        )
        else {}
    )

    fifteen_indicators = (
        fifteen.get(
            "indicators",
            {},
        )
        if isinstance(
            fifteen,
            dict,
        )
        else {}
    )

    fifteen_structure = (
        fifteen.get(
            "structure",
            {},
        )
        if isinstance(
            fifteen,
            dict,
        )
        else {}
    )

    fifteen_sr = (
        fifteen_structure.get(
            "support_resistance",
            {},
        )
        if isinstance(
            fifteen_structure,
            dict,
        )
        else {}
    )

    location = (
        fifteen_sr.get(
            "location",
            "UNKNOWN",
        )
        if isinstance(
            fifteen_sr,
            dict,
        )
        else "UNKNOWN"
    )

    points["4"] = {
        "number": 4,
        "name": "Entry Location",
        "category": "market",
        "status": "CONFIRMED"
        if location
        not in {
            "UNKNOWN",
            "MID_RANGE",
        }
        else "NEUTRAL",
        "direction": (
            "LONG"
            if location
            == "NEAR_SUPPORT"
            else "SHORT"
            if location
            == "NEAR_RESISTANCE"
            else "NEUTRAL"
        ),
        "location": location,
    }

    # =====================================================
    # 5 — LIQUIDITY SWEEP
    # =====================================================

    points["5"] = {
        "number": 5,
        "name": "Liquidity Sweep",
        "category": "market",
        "status": (
            liquidations.get(
                "status",
                "UNAVAILABLE",
            )
        ),
        "direction": (
            liquidations.get(
                "direction",
                "NEUTRAL",
            )
        ),
        "score": liquidations.get(
            "score",
            0,
        ),
    }

    # =====================================================
    # 6 — VWAP
    # =====================================================

    price = safe_float(
        fifteen_indicators.get(
            "price",
            0,
        )
    )

    vwap = safe_float(
        fifteen_indicators.get(
            "vwap",
            0,
        )
    )

    vwap_direction = (
        "LONG"
        if price > vwap > 0
        else "SHORT"
        if price < vwap
        else "NEUTRAL"
    )

    points["6"] = {
        "number": 6,
        "name": "VWAP",
        "category": "market",
        "status": (
            "CONFIRMED"
            if vwap > 0
            else "UNAVAILABLE"
        ),
        "direction": vwap_direction,
        "price": price,
        "vwap": vwap,
    }

    # =====================================================
    # 7 — ATR / VOLATILITY
    # =====================================================

    atr_percent = safe_float(
        fifteen_indicators.get(
            "atr_percent",
            0,
        )
    )

    volatility_ok = (
        0.10
        <= atr_percent
        <= 12.0
    )

    points["7"] = {
        "number": 7,
        "name": "ATR / Volatility",
        "category": "market",
        "status": (
            "CONFIRMED"
            if volatility_ok
            else "REJECTED"
        ),
        "direction": "NEUTRAL",
        "atr_percent": atr_percent,
    }

    # =====================================================
    # 8 — MOMENTUM
    # =====================================================

    momentum = safe_float(
        fifteen_indicators.get(
            "momentum",
            0,
        )
    )

    points["8"] = {
        "number": 8,
        "name": "Momentum",
        "category": "market",
        "status": (
            "CONFIRMED"
            if momentum != 0
            else "NEUTRAL"
        ),
        "direction": (
            "LONG"
            if momentum > 0
            else "SHORT"
            if momentum < 0
            else "NEUTRAL"
        ),
        "value": momentum,
    }

    # =====================================================
    # 9 — DIVERGENCE
    # =====================================================

    # Actual swing/indicator divergence needs a dedicated
    # divergence engine. Until then we explicitly report
    # UNKNOWN rather than fabricating a signal.

    points["9"] = {
        "number": 9,
        "name": "Divergence",
        "category": "market",
        "status": "UNKNOWN",
        "direction": "NEUTRAL",
        "value": "NOT_IMPLEMENTED",
    }

    # =====================================================
    # 10 — BREAKOUT
    # =====================================================

    breakout = (
        fifteen_indicators.get(
            "breakout",
            {},
        )
        if isinstance(
            fifteen_indicators.get(
                "breakout",
                {},
            ),
            dict,
        )
        else {}
    )

    breakout_direction = str(
        breakout.get(
            "direction",
            "NONE",
        )
    ).upper()

    points["10"] = {
        "number": 10,
        "name": "Breakout",
        "category": "market",
        "status": (
            "CONFIRMED"
            if breakout.get(
                "breakout",
                False,
            )
            else "NEUTRAL"
        ),
        "direction": (
            breakout_direction
            if breakout_direction
            in {
                "LONG",
                "SHORT",
            }
            else "NEUTRAL"
        ),
        "level": breakout.get(
            "level",
            0,
        ),
    }

    # =====================================================
    # 11 — RETEST
    # =====================================================

    points["11"] = {
        "number": 11,
        "name": "Retest",
        "category": "market",
        "status": "UNKNOWN",
        "direction": "NEUTRAL",
        "value": "DEDICATED_RETEST_ENGINE_PENDING",
    }

    # =====================================================
    # 12 — DERIVATIVES
    # =====================================================

    points["12"] = {
        "number": 12,
        "name": "Derivatives",
        "category": "market",
        "status": derivatives.get(
            "status",
            "UNAVAILABLE",
        ),
        "direction": derivatives.get(
            "direction",
            "NEUTRAL",
        ),
        "score": derivatives.get(
            "score",
            0,
        ),
    }

    # =====================================================
    # 13 — LIQUIDATIONS
    # =====================================================

    points["13"] = {
        "number": 13,
        "name": "Liquidations",
        "category": "market",
        "status": liquidations.get(
            "status",
            "UNAVAILABLE",
        ),
        "direction": liquidations.get(
            "direction",
            "NEUTRAL",
        ),
        "score": liquidations.get(
            "score",
            0,
        ),
    }

    # =====================================================
    # 14 — ORDER BOOK
    # =====================================================

    points["14"] = {
        "number": 14,
        "name": "Order Book",
        "category": "market",
        "status": order_book.get(
            "status",
            "UNAVAILABLE",
        ),
        "direction": order_book.get(
            "direction",
            "NEUTRAL",
        ),
        "score": order_book.get(
            "score",
            0,
        ),
        "imbalance": order_book.get(
            "imbalance",
            0,
        ),
    }

    # =====================================================
    # 15 — TRADEABILITY
    # =====================================================

    points["15"] = {
        "number": 15,
        "name": "Tradeability",
        "category": "market",
        "status": "PENDING_EXECUTION_CHECK",
        "direction": "NEUTRAL",
    }

    # =====================================================
    # 16 — NEWS / EVENT RISK
    # =====================================================

    points["16"] = {
        "number": 16,
        "name": "News / Event Risk",
        "category": "market",
        "status": "UNKNOWN",
        "direction": "NEUTRAL",
        "value": "NEWS_PROVIDER_NOT_CONNECTED",
    }

    # =====================================================
    # 17 — BTC / MARKET CONTEXT
    # =====================================================

    points["17"] = {
        "number": 17,
        "name": "BTC / Market Context",
        "category": "market",
        "status": (
            "NOT_REQUIRED_FOR_BTC"
            if analysis.get(
                "symbol"
            ) == "BTCUSDT"
            else "PENDING"
        ),
        "direction": "NEUTRAL",
    }

    # =====================================================
    # 18 — RELATIVE STRENGTH
    # =====================================================

    points["18"] = {
        "number": 18,
        "name": "Relative Strength",
        "category": "market",
        "status": "PENDING_RELATIVE_STRENGTH_ENGINE",
        "direction": "NEUTRAL",
    }

    # =====================================================
    # 19 — RISK / REWARD
    # =====================================================

    rr = safe_float(
        levels.get(
            "risk_reward",
            0,
        )
    )

    points["19"] = {
        "number": 19,
        "name": "Risk / Reward",
        "category": "market",
        "status": (
            "CONFIRMED"
            if rr >= 2.0
            else "REJECTED"
        ),
        "direction": (
            direction
            if direction
            in {
                "LONG",
                "SHORT",
            }
            else "NEUTRAL"
        ),
        "risk_reward": rr,
    }

    # =====================================================
    # 20 — STOP QUALITY
    # =====================================================

    stop_quality = str(
        levels.get(
            "stop_quality",
            "INVALID",
        )
    ).upper()

    points["20"] = {
        "number": 20,
        "name": "Stop Quality",
        "category": "market",
        "status": (
            "CONFIRMED"
            if stop_quality == "VALID"
            else "REJECTED"
        ),
        "direction": direction,
        "value": stop_quality,
    }

    # =====================================================
    # 21 — POSITION SIZING
    # =====================================================

    points["21"] = {
        "number": 21,
        "name": "Position Sizing",
        "category": "risk",
        "status": "PENDING_ACCOUNT_RISK",
        "direction": "NEUTRAL",
    }

    # =====================================================
    # 22 — PORTFOLIO RISK
    # =====================================================

    points["22"] = {
        "number": 22,
        "name": "Portfolio Risk",
        "category": "risk",
        "status": "PENDING_PORTFOLIO_STATE",
        "direction": "NEUTRAL",
    }

    # =====================================================
    # 23 — EXECUTION QUALITY
    # =====================================================

    points["23"] = {
        "number": 23,
        "name": "Execution Quality",
        "category": "risk",
        "status": "PENDING_EXECUTION_CHECK",
        "direction": "NEUTRAL",
    }

    # =====================================================
    # 24 — SIGNAL FRESHNESS
    # =====================================================

    points["24"] = {
        "number": 24,
        "name": "Signal Freshness",
        "category": "risk",
        "status": "FRESH",
        "direction": "NEUTRAL",
    }

    return {
        "points": points,
        "levels": levels,
        "market_confirmation_count": sum(
            1
            for number in range(
                1,
                21,
            )
            if points[
                str(number)
            ].get(
                "status"
            )
            == "CONFIRMED"
        ),
        "market_confirmation_total": 20,
        "risk_gate_count": 0,
        "risk_gate_total": 4,
    }


# =========================================================
# HEALTH
# =========================================================

@router.get("/health")
async def health() -> dict[str, Any]:

    return {
        "success": True,
        "status": "healthy",
        "service": "rr-trader",
        "version": settings.app_version,
        "core_timeframes": list(
            CORE_TIMEFRAMES
        ),
    }


# =========================================================
# MARKETS
# =========================================================

@router.get("/markets")
async def markets() -> dict[str, Any]:

    return {
        "success": True,
        "markets": [
            {
                "id": "futures",
                "name": "Binance Futures",
                "enabled": True,
            },
            {
                "id": "spot",
                "name": "Binance Spot",
                "enabled": True,
            },
        ],
    }


# =========================================================
# SEARCH
# =========================================================

@router.get("/search")
async def search(
    q: str = Query(
        default="",
        max_length=30,
    ),
    market: str = Query(
        default="futures",
    ),
) -> dict[str, Any]:

    clean_market = normalize_market(
        market
    )

    clean_query = (
        str(q or "")
        .upper()
        .replace(
            "/",
            "",
        )
        .replace(
            "-",
            "",
        )
        .replace(
            "USDT",
            "",
        )
        .strip()
    )

    if not clean_query:

        return {
            "success": True,
            "market": clean_market,
            "coins": [],
        }

    target_symbol = (
        f"{clean_query}USDT"
    )

    try:

        exchange_info = (
            await market_data_service
            .exchange_info(
                market=clean_market
            )
        )

    except Exception as exc:

        raise HTTPException(
            status_code=502,
            detail=(
                "Binance market lookup failed: "
                f"{str(exc)}"
            ),
        ) from exc

    symbols = (
        exchange_info.get(
            "symbols",
            [],
        )
        if isinstance(
            exchange_info,
            dict,
        )
        else []
    )

    matches = []

    for item in symbols:

        if not isinstance(
            item,
            dict,
        ):
            continue

        item_symbol = str(
            item.get(
                "symbol",
                "",
            )
        ).upper()

        if item_symbol != target_symbol:
            continue

        if str(
            item.get(
                "status",
                "",
            )
        ).upper() != "TRADING":
            continue

        matches.append(
            {
                "symbol": item_symbol,
                "coin": clean_query,
                "market": clean_market,
                "base_asset": item.get(
                    "baseAsset"
                ),
                "quote_asset": item.get(
                    "quoteAsset"
                ),
                "status": "TRADING",
            }
        )

    return {
        "success": True,
        "market": clean_market,
        "query": clean_query,
        "coins": matches,
    }


# =========================================================
# ANALYZE
# =========================================================

@router.get("/analyze")
async def analyze(
    symbol: str,
    market: str = Query(
        default="futures",
    ),
    candle_limit: int = Query(
        default=200,
        ge=50,
        le=500,
    ),
) -> dict[str, Any]:

    clean_market = normalize_market(
        market
    )

    clean_symbol = normalize_symbol(
        symbol
    )

    try:

        analysis = await (
            master_analysis_engine.analyze(
                symbol=clean_symbol,
                market=clean_market,
                candle_limit=candle_limit,
            )
        )

    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:

        raise HTTPException(
            status_code=502,
            detail=(
                "Market analysis failed: "
                f"{str(exc)}"
            ),
        ) from exc

    levels = build_trade_levels(
        analysis
    )

    point_result = (
        build_24_point_result(
            analysis,
            levels,
        )
    )

    direction = str(
        analysis.get(
            "direction",
            "NEUTRAL",
        )
    ).upper()

    confidence = safe_float(
        analysis.get(
            "confidence",
            0,
        )
    )

    # -----------------------------------------------------
    # Final publishability
    # -----------------------------------------------------

    critical_market_failures = []

    if not analysis.get(
        "multi_timeframe",
        {},
    ).get(
        "publishable_mtf",
        False,
    ):

        critical_market_failures.append(
            "MTF_NOT_ALIGNED"
        )

    if levels.get(
        "stop_quality"
    ) != "VALID":

        critical_market_failures.append(
            "INVALID_STOP"
        )

    if safe_float(
        levels.get(
            "risk_reward",
            0,
        )
    ) < 2.0:

        critical_market_failures.append(
            "LOW_RISK_REWARD"
        )

    if confidence < (
        MIN_PUBLISH_CONFIDENCE
    ):

        critical_market_failures.append(
            "LOW_CONFIDENCE"
        )

    if direction not in {
        "LONG",
        "SHORT",
    }:

        critical_market_failures.append(
            "NO_DIRECTION"
        )

    publishable = (
        len(
            critical_market_failures
        )
        == 0
    )

    # -----------------------------------------------------
    # Final reasons
    # -----------------------------------------------------

    reasons = list(
        analysis.get(
            "reasons",
            [],
        )
        or []
    )

    if publishable:

        reasons.append(
            "All current directional gates passed."
        )

    else:

        reasons.append(
            "Trade is not publishable because one or more critical gates failed."
        )

    result = {
        **analysis,
        "entry": levels.get(
            "entry",
            0,
        ),
        "stop_loss": levels.get(
            "stop_loss",
            0,
        ),
        "tp1": levels.get(
            "tp1",
            0,
        ),
        "tp2": levels.get(
            "tp2",
            0,
        ),
        "tp3": levels.get(
            "tp3",
            0,
        ),
        "risk_reward": levels.get(
            "risk_reward",
            0,
        ),
        "stop_quality": levels.get(
            "stop_quality",
            "INVALID",
        ),
        "atr": levels.get(
            "atr",
            0,
        ),
        "publishable": publishable,
        "critical_failures": (
            critical_market_failures
        ),
        "reasons": list(
            dict.fromkeys(
                reasons
            )
        ),
        "24_point_analysis": point_result,
        "signal_status": (
            "PUBLISHABLE"
            if publishable
            else "NO_TRADE"
        ),
    }

    # -----------------------------------------------------
    # Store useful analysis
    # -----------------------------------------------------

    signal_memory.add(
        {
            "symbol": clean_symbol,
            "market": clean_market,
            "direction": direction,
            "confidence": confidence,
            "entry": result[
                "entry"
            ],
            "stop_loss": result[
                "stop_loss"
            ],
            "tp1": result[
                "tp1"
            ],
            "tp2": result[
                "tp2"
            ],
            "tp3": result[
                "tp3"
            ],
            "risk_reward": result[
                "risk_reward"
            ],
            "publishable": publishable,
            "signal_status": result[
                "signal_status"
            ],
            "critical_failures":
                critical_market_failures,
            "24_point_analysis":
                point_result,
        }
    )

    return result


# =========================================================
# FULL MARKET SCAN
# =========================================================

@router.get("/scan")
async def scan(
    market: str = Query(
        default="futures",
    ),
    limit: int = Query(
        default=6,
        ge=1,
        le=20,
    ),
    candle_limit: int = Query(
        default=120,
        ge=50,
        le=300,
    ),
) -> dict[str, Any]:

    clean_market = normalize_market(
        market
    )

    try:

        universe = await (
            market_scanner.top_candidates(
                market=clean_market,
                limit=limit,
            )
        )

    except Exception as exc:

        raise HTTPException(
            status_code=502,
            detail=(
                "Market universe scan failed: "
                f"{str(exc)}"
            ),
        ) from exc

    candidates = universe.get(
        "candidates",
        [],
    )

    if not isinstance(
        candidates,
        list,
    ):

        candidates = []

    async def analyze_candidate(
        candidate: dict[str, Any],
    ) -> dict[str, Any]:

        candidate_symbol = (
            normalize_symbol(
                candidate.get(
                    "symbol",
                    "",
                )
            )
        )

        try:

            analysis = await (
                master_analysis_engine
                .analyze(
                    symbol=candidate_symbol,
                    market=clean_market,
                    candle_limit=candle_limit,
                )
            )

            levels = build_trade_levels(
                analysis
            )

            point_result = (
                build_24_point_result(
                    analysis,
                    levels,
                )
            )

            direction = str(
                analysis.get(
                    "direction",
                    "NEUTRAL",
                )
            ).upper()

            confidence = safe_float(
                analysis.get(
                    "confidence",
                    0,
                )
            )

            publishable = (
                direction
                in {
                    "LONG",
                    "SHORT",
                }
                and confidence
                >= MIN_PUBLISH_CONFIDENCE
                and analysis.get(
                    "multi_timeframe",
                    {},
                ).get(
                    "publishable_mtf",
                    False,
                )
                and levels.get(
                    "stop_quality"
                ) == "VALID"
                and safe_float(
                    levels.get(
                        "risk_reward",
                        0,
                    )
                ) >= 2.0
            )

            result = {
                **analysis,
                "symbol":
                    candidate_symbol,
                "entry":
                    levels.get(
                        "entry",
                        0,
                    ),
                "stop_loss":
                    levels.get(
                        "stop_loss",
                        0,
                    ),
                "tp1":
                    levels.get(
                        "tp1",
                        0,
                    ),
                "tp2":
                    levels.get(
                        "tp2",
                        0,
                    ),
                "tp3":
                    levels.get(
                        "tp3",
                        0,
                    ),
                "risk_reward":
                    levels.get(
                        "risk_reward",
                        0,
                    ),
                "stop_quality":
                    levels.get(
                        "stop_quality",
                        "INVALID",
                    ),
                "publishable":
                    publishable,
                "24_point_analysis":
                    point_result,
            }

            return {
                "success": True,
                "candidate": candidate,
                "analysis": result,
            }

        except Exception as exc:

            return {
                "success": False,
                "candidate": candidate,
                "analysis": None,
                "error": str(exc),
            }

    results = await asyncio.gather(
        *[
            analyze_candidate(
                candidate
            )
            for candidate in candidates
        ],
        return_exceptions=False,
    )

    analyses = []

    for item in results:

        analysis = item.get(
            "analysis"
        )

        if isinstance(
            analysis,
            dict,
        ):

            analyses.append(
                analysis
            )

    analyses.sort(
        key=lambda item: (
            safe_float(
                item.get(
                    "confidence",
                    0,
                )
            )
        ),
        reverse=True,
    )

    publishable_signals = [
        item
        for item in analyses
        if item.get(
            "publishable",
            False,
        )
    ]

    # -----------------------------------------------------
    # Store publishable signals
    # -----------------------------------------------------

    for signal in publishable_signals:

        signal_memory.add(
            {
                "symbol": signal.get(
                    "symbol"
                ),
                "market": clean_market,
                "direction": signal.get(
                    "direction"
                ),
                "confidence": signal.get(
                    "confidence"
                ),
                "entry": signal.get(
                    "entry"
                ),
                "stop_loss": signal.get(
                    "stop_loss"
                ),
                "tp1": signal.get(
                    "tp1"
                ),
                "tp2": signal.get(
                    "tp2"
                ),
                "tp3": signal.get(
                    "tp3"
                ),
                "risk_reward": signal.get(
                    "risk_reward"
                ),
                "publishable": True,
            }
        )

    return {
        "success": True,
        "market": clean_market,
        "universe_mode": "FULL_MARKET",
        "scanned_universe": (
            universe.get(
                "eligible_markets",
                0,
            )
        ),
        "candidate_count": len(
            candidates
        ),
        "deep_analyzed": len(
            analyses
        ),
        "publishable_count": len(
            publishable_signals
        ),
        "core_timeframes": list(
            CORE_TIMEFRAMES
        ),
        "candidates": candidates,
        "analyses": analyses,
        "publishable_signals":
            publishable_signals,
    }


# =========================================================
# SIGNALS
# =========================================================

@router.get("/signals")
async def signals(
    limit: int = Query(
        default=50,
        ge=1,
        le=500,
    ),
) -> dict[str, Any]:

    return {
        "success": True,
        "signals": signal_memory.latest(
            limit
        ),
        "stats": signal_memory.stats(),
    }


# =========================================================
# GENERATE POST
# =========================================================

@router.post("/post/generate")
async def generate_post(
    analysis: dict[str, Any],
) -> dict[str, Any]:

    if not isinstance(
        analysis,
        dict,
    ):

        raise HTTPException(
            status_code=400,
            detail=(
                "Analysis must be an object."
            ),
        )

    direction = str(
        analysis.get(
            "direction",
            "NEUTRAL",
        )
    ).upper()

    if direction not in {
        "LONG",
        "SHORT",
    }:

        raise HTTPException(
            status_code=400,
            detail=(
                "Post can only be generated "
                "for LONG or SHORT."
            ),
        )

    try:

        return post_generator.generate(
            analysis
        )

    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=(
                "Post generation failed: "
                f"{str(exc)}"
            ),
        ) from exc
