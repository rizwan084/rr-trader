from __future__ import annotations

import asyncio
import gc
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from app.app.api.routes import router as api_router
from app.app.api.trade_routes import router as trade_api_router
from app.app.clients.binance import BinanceClient
from app.app.services.scanner import MarketScanner
from app.app.services.trade_engine import default_trade_engine


app = FastAPI(
    title="RR Trader Live Scanner",
    description="AI-powered Binance Spot and Futures market scanner",
    version="4.3.1",
)


# =========================================================
# HELPERS
# =========================================================

def _safe_float(
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


def _confidence_level(
    confidence: float,
) -> str:

    if confidence >= 99:
        return "EXTREME"

    if confidence >= 95:
        return "VERY HIGH"

    if confidence >= 90:
        return "HIGH"

    if confidence >= 85:
        return "WATCH"

    return "LOW"


def _signal_sort_key(
    item: Dict[str, Any],
):
    return _safe_float(
        item.get(
            "confidence",
            0,
        )
    )


# =========================================================
# BACKGROUND AUTO SCANNER
# =========================================================

AUTO_SCAN_INTERVAL_SECONDS = 60
AUTO_UNIVERSE_SIZE = 150
AUTO_DEEP_ANALYSIS_SIZE = 1

_auto_scanner_task: Optional[
    asyncio.Task
] = None

_auto_state: Dict[str, Any] = {
    "running": False,
    "last_scan": None,
    "next_scan_in_seconds": (
        AUTO_SCAN_INTERVAL_SECONDS
    ),
    "error": None,
    "market": "futures",
    "universe": [],
    "signals": [],
    "trade_evaluations": [],
    "scanned": 0,
    "deep_analyzed": 0,
}


_auto_binance = BinanceClient()
_auto_scanner = MarketScanner()


def _candidate_score(
    ticker: Dict[str, Any],
) -> float:
    """
    Cheap pre-screen score.

    This is NOT trade confidence.

    It only ranks liquid and moving contracts
    before expensive deep analysis.
    """

    change = _safe_float(
        ticker.get(
            "priceChangePercent",
            0,
        )
    )

    volume = _safe_float(
        ticker.get(
            "quoteVolume",
            0,
        )
    )

    volume_score = min(
        35.0,
        max(
            0.0,
            (
                (volume / 10_000_000.0)
                ** 0.5
            )
            * 8.0,
        ),
    )

    momentum_score = min(
        50.0,
        abs(change) * 5.0,
    )

    direction_bonus = (
        10.0
        if abs(change) >= 2.0
        else 5.0
        if abs(change) >= 1.0
        else 0.0
    )

    return round(
        min(
            100.0,
            volume_score
            + momentum_score
            + direction_bonus,
        ),
        2,
    )


def _is_valid_futures_usdt_ticker(
    ticker: Dict[str, Any],
) -> bool:

    symbol = str(
        ticker.get(
            "symbol",
            "",
        )
    ).upper()

    if not symbol.endswith(
        "USDT"
    ):
        return False

    if any(
        blocked in symbol
        for blocked in (
            "UPUSDT",
            "DOWNUSDT",
            "BULLUSDT",
            "BEARUSDT",
        )
    ):
        return False

    return (
        _safe_float(
            ticker.get(
                "lastPrice",
                0,
            )
        )
        > 0
    )


async def _build_candidate_universe() -> List[
    Dict[str, Any]
]:
    """
    Build a cheap Futures universe.

    Up to 150 symbols are retained.

    Only a small subset is deeply analyzed,
    keeping Render memory usage under control.
    """

    tickers = await _auto_binance.ticker_24h(
        market="futures"
    )

    if not isinstance(
        tickers,
        list,
    ):
        return []

    candidates: List[
        Dict[str, Any]
    ] = []

    for ticker in tickers:

        if not isinstance(
            ticker,
            dict,
        ):
            continue

        if not _is_valid_futures_usdt_ticker(
            ticker
        ):
            continue

        symbol = str(
            ticker.get(
                "symbol",
                "",
            )
        ).upper()

        change = _safe_float(
            ticker.get(
                "priceChangePercent",
                0,
            )
        )

        quote_volume = _safe_float(
            ticker.get(
                "quoteVolume",
                0,
            )
        )

        last_price = _safe_float(
            ticker.get(
                "lastPrice",
                0,
            )
        )

        score = _candidate_score(
            ticker
        )

        candidates.append(
            {
                "symbol": symbol,
                "coin": symbol[:-4],
                "price": last_price,
                "price_change_24h": round(
                    change,
                    4,
                ),
                "quote_volume_24h": quote_volume,
                "candidate_score": score,
            }
        )

    candidates.sort(
        key=lambda item: (
            _safe_float(
                item.get(
                    "candidate_score",
                    0,
                )
            ),
            abs(
                _safe_float(
                    item.get(
                        "price_change_24h",
                        0,
                    )
                )
            ),
            _safe_float(
                item.get(
                    "quote_volume_24h",
                    0,
                )
            ),
        ),
        reverse=True,
    )

    return candidates[
        :AUTO_UNIVERSE_SIZE
    ]


async def _auto_scan_cycle() -> None:
    """
    One background scan cycle.

    1. Build a 150-symbol cheap universe.
    2. Deep-analyze top 1 only.
    3. Keep 90%+ signals.
    """

    _auto_state[
        "running"
    ] = True

    _auto_state[
        "error"
    ] = None

    try:

        universe = (
            await _build_candidate_universe()
        )

        _auto_state[
            "universe"
        ] = universe

        _auto_state[
            "scanned"
        ] = len(
            universe
        )

        deep_candidates = (
            universe[
                :AUTO_DEEP_ANALYSIS_SIZE
            ]
        )

        signals: List[
            Dict[str, Any]
        ] = []

        trade_evaluations: List[
            Dict[str, Any]
        ] = []

        for candidate in deep_candidates:

            symbol = candidate[
                "symbol"
            ]

            try:

                analysis = (
                    await _auto_scanner.scan_symbol(
                        symbol=symbol,
                        market="futures",
                        limit=60,
                    )
                )

                if not isinstance(
                    analysis,
                    dict,
                ):
                    continue

                if not analysis.get(
                    "success",
                    False,
                ):
                    continue

                confidence = _safe_float(
                    analysis.get(
                        "confidence",
                        0,
                    )
                )

                direction = str(
                    analysis.get(
                        "direction",
                        "NEUTRAL",
                    )
                ).upper()

                # Run the strict 24-point trade gate on every
                # deep analysis. This is still PAPER-TRADING only;
                # no live order is placed here.
                try:
                    trade_decision = (
                        default_trade_engine
                        .evaluate_trade(
                            analysis
                        )
                    )
                except Exception as trade_exc:
                    trade_decision = {
                        "decision": "NO_TRADE",
                        "trade_score": 0.0,
                        "reason": str(trade_exc),
                    }

                trade_record = {
                    "symbol": symbol,
                    "coin": symbol[:-4],
                    "direction": direction,
                    "scanner_confidence": confidence,
                    "candidate_score": candidate.get(
                        "candidate_score",
                        0,
                    ),
                    "decision": trade_decision.get(
                        "decision",
                        "NO_TRADE",
                    ),
                    "trade_score": _safe_float(
                        trade_decision.get(
                            "trade_score",
                            0,
                        )
                    ),
                    "passed_confirmations": trade_decision.get(
                        "passed_confirmations",
                        0,
                    ),
                    "total_confirmations": trade_decision.get(
                        "total_confirmations",
                        24,
                    ),
                    "critical_failures": trade_decision.get(
                        "critical_failures",
                        [],
                    ),
                    "reasons": trade_decision.get(
                        "reasons",
                        [],
                    ),
                }

                trade_evaluations.append(
                    trade_record
                )

                if (
                    direction
                    in {
                        "LONG",
                        "SHORT",
                    }
                    and confidence >= 90.0
                ):

                    enriched = dict(
                        analysis
                    )

                    enriched[
                        "candidate_score"
                    ] = candidate.get(
                        "candidate_score",
                        0,
                    )

                    enriched[
                        "confidence_level"
                    ] = _confidence_level(
                        confidence
                    )

                    enriched[
                        "trade_decision"
                    ] = trade_decision

                    signals.append(
                        enriched
                    )

            except Exception:
                continue

        signals.sort(
            key=lambda item: (
                _safe_float(
                    item.get(
                        "confidence",
                        0,
                    )
                ),
                _safe_float(
                    item.get(
                        "candidate_score",
                        0,
                    )
                ),
            ),
            reverse=True,
        )

        _auto_state[
            "signals"
        ] = signals

        _auto_state[
            "trade_evaluations"
        ] = trade_evaluations

        _auto_state[
            "deep_analyzed"
        ] = len(
            deep_candidates
        )

        _auto_state[
            "last_scan"
        ] = datetime.now(
            timezone.utc
        ).isoformat()

        # Release temporary deep-analysis objects
        # before the next 60-second cycle.
        del signals
        del trade_evaluations
        del deep_candidates
        del universe

        gc.collect()

    except Exception as exc:

        _auto_state[
            "error"
        ] = str(exc)

    finally:

        _auto_state[
            "running"
        ] = False

        _auto_state[
            "next_scan_in_seconds"
        ] = AUTO_SCAN_INTERVAL_SECONDS

        gc.collect()


async def _auto_scanner_loop() -> None:
    """
    Continuous one-minute scanner.

    A new scan starts only after the previous
    scan has completed.
    """

    await asyncio.sleep(3)

    while True:

        try:

            await _auto_scan_cycle()

        except asyncio.CancelledError:
            raise

        except Exception as exc:

            _auto_state[
                "error"
            ] = str(exc)

            _auto_state[
                "running"
            ] = False

        for remaining in range(
            AUTO_SCAN_INTERVAL_SECONDS,
            0,
            -1,
        ):

            _auto_state[
                "next_scan_in_seconds"
            ] = remaining

            try:

                await asyncio.sleep(
                    1
                )

            except asyncio.CancelledError:
                raise


@app.on_event(
    "startup"
)
async def start_background_scanner() -> None:

    global _auto_scanner_task

    if (
        _auto_scanner_task is None
        or _auto_scanner_task.done()
    ):

        _auto_scanner_task = (
            asyncio.create_task(
                _auto_scanner_loop()
            )
        )


@app.on_event(
    "shutdown"
)
async def stop_background_scanner() -> None:

    global _auto_scanner_task

    if _auto_scanner_task is None:
        return

    _auto_scanner_task.cancel()

    try:

        await _auto_scanner_task

    except asyncio.CancelledError:
        pass

    _auto_scanner_task = None


# =========================================================
# FUTURES SYMBOL SEARCH
# =========================================================

_symbol_cache: Dict[
    str,
    Dict[str, Any],
] = {}


async def _load_futures_symbols() -> List[
    Dict[str, str]
]:

    cached = _symbol_cache.get(
        "futures"
    )

    if cached:

        return cached.get(
            "symbols",
            [],
        )

    info = (
        await _auto_binance.exchange_info(
            market="futures"
        )
    )

    raw_symbols = (
        info.get(
            "symbols",
            [],
        )
        if isinstance(
            info,
            dict,
        )
        else []
    )

    symbols: List[
        Dict[str, str]
    ] = []

    for item in raw_symbols:

        if not isinstance(
            item,
            dict,
        ):
            continue

        symbol = str(
            item.get(
                "symbol",
                "",
            )
        ).upper()

        status = str(
            item.get(
                "status",
                "",
            )
        ).upper()

        quote_asset = str(
            item.get(
                "quoteAsset",
                "",
            )
        ).upper()

        contract_type = str(
            item.get(
                "contractType",
                "",
            )
        ).upper()

        if (
            symbol.endswith("USDT")
            and quote_asset == "USDT"
            and status == "TRADING"
            and contract_type == "PERPETUAL"
        ):

            symbols.append(
                {
                    "symbol": symbol,
                    "coin": symbol[:-4],
                    "market": "futures",
                }
            )

    symbols.sort(
        key=lambda item: item[
            "coin"
        ]
    )

    _symbol_cache[
        "futures"
    ] = {
        "symbols": symbols
    }

    return symbols


@app.get(
    "/api/search"
)
async def search_coins(
    q: str = Query(
        default="",
        min_length=0,
        max_length=30,
    ),
    market: str = Query(
        default="futures",
    ),
) -> Dict[str, Any]:

    market = (
        market
        .lower()
        .strip()
    )

    if market != "futures":

        raise HTTPException(
            status_code=400,
            detail=(
                "Coin search currently "
                "uses the Binance Futures "
                "perpetual universe."
            ),
        )

    query = (
        q
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

    symbols = (
        await _load_futures_symbols()
    )

    if not query:

        return {
            "success": True,
            "query": "",
            "coins": symbols[:20],
        }

    starts_with = []
    contains = []

    for item in symbols:

        coin = item[
            "coin"
        ]

        if coin.startswith(
            query
        ):

            starts_with.append(
                item
            )

        elif query in coin:

            contains.append(
                item
            )

    results = (
        starts_with
        + contains
    )[:20]

    return {
        "success": True,
        "query": query,
        "coins": results,
    }


# =========================================================
# AUTO SCANNER API
# =========================================================

@app.get(
    "/api/auto/status"
)
async def auto_scan_status() -> Dict[
    str,
    Any,
]:

    return {
        "success": True,
        "market": _auto_state[
            "market"
        ],
        "running": _auto_state[
            "running"
        ],
        "last_scan": _auto_state[
            "last_scan"
        ],
        "next_scan_in_seconds": (
            _auto_state[
                "next_scan_in_seconds"
            ]
        ),
        "scanned_universe": (
            _auto_state[
                "scanned"
            ]
        ),
        "deep_analyzed": (
            _auto_state[
                "deep_analyzed"
            ]
        ),
        "signals_count": len(
            _auto_state[
                "signals"
            ]
        ),
        "error": _auto_state[
            "error"
        ],
    }


@app.get(
    "/api/auto/signals"
)
async def auto_signals(
    min_confidence: float = Query(
        default=90.0,
        ge=0,
        le=100,
    ),
) -> Dict[
    str,
    Any,
]:

    signals = [
        item
        for item in _auto_state[
            "signals"
        ]
        if _safe_float(
            item.get(
                "confidence",
                0,
            )
        ) >= min_confidence
    ]

    return {
        "success": True,
        "market": "futures",
        "min_confidence": (
            min_confidence
        ),
        "scanned": _auto_state[
            "scanned"
        ],
        "deep_analyzed": _auto_state[
            "deep_analyzed"
        ],
        "signals_count": len(
            signals
        ),
        "signals": signals,
        "last_scan": _auto_state[
            "last_scan"
        ],
        "running": _auto_state[
            "running"
        ],
        "next_scan_in_seconds": (
            _auto_state[
                "next_scan_in_seconds"
            ]
        ),
    }


@app.get(
    "/api/auto/candidates"
)
async def auto_candidates(
    limit: int = Query(
        default=20,
        ge=1,
        le=150,
    ),
) -> Dict[
    str,
    Any,
]:

    return {
        "success": True,
        "market": "futures",
        "universe_size": _auto_state[
            "scanned"
        ],
        "candidates": _auto_state[
            "universe"
        ][:limit],
        "last_scan": _auto_state[
            "last_scan"
        ],
    }


# =========================================================
# AUTO TRADE-GATE API
# =========================================================

@app.get(
    "/api/auto/trades"
)
async def auto_trade_evaluations() -> Dict[
    str,
    Any,
]:

    return {
        "success": True,
        "market": "futures",
        "count": len(
            _auto_state["trade_evaluations"]
        ),
        "trade_evaluations": _auto_state[
            "trade_evaluations"
        ],
        "last_scan": _auto_state[
            "last_scan"
        ],
    }


# =========================================================
# ROOT
# =========================================================

@app.get("/")
async def root():

    return {
        "app": "RR Trader Live Scanner",
        "status": "online",
        "version": "4.3.0",
        "markets": [
            "futures",
            "spot",
        ],
        "dashboard": "/dashboard",
        "high_confidence_api": (
            "/api/signals"
        ),
        "post_api": (
            "/api/post/generate"
        ),
        "trade_api": (
            "/api/trade/status"
        ),
        "chart": "TradingView Advanced Chart",
        "message": (
            "RR Trader backend is working"
        ),
    }


# =========================================================
# HEALTH
# =========================================================

@app.get("/health")
async def health():

    return {
        "success": True,
        "status": "healthy",
        "service": "rr-trader",
    }


# =========================================================
# API ROUTES
# =========================================================

app.include_router(
    api_router,
    prefix="/api",
    tags=[
        "RR Trader API"
    ],
)

app.include_router(
    trade_api_router,
    prefix="/api",
    tags=[
        "Trade Engine",
    ],
)


# =========================================================
# DASHBOARD HTML
# =========================================================

DASHBOARD_HTML = r"""
<!DOCTYPE html>
<html lang="en">

<head>

    <meta charset="UTF-8">

    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0"
    >

    <title>
        RR Trader Live Intelligence
    </title>

    <style>

        * {
            box-sizing: border-box;
        }

        body {

            margin: 0;

            min-height: 100vh;

            font-family:
                Inter,
                system-ui,
                -apple-system,
                BlinkMacSystemFont,
                "Segoe UI",
                sans-serif;

            color: #f4f7fb;

            background:
                radial-gradient(
                    circle at 10% 0%,
                    #172b52 0%,
                    #0a1020 32%,
                    #05070c 72%,
                    #03050a 100%
                );
        }

        .topbar {

            position: sticky;
            top: 0;
            z-index: 100;

            display: flex;
            justify-content: space-between;
            align-items: center;

            padding: 14px 24px;

            background:
                rgba(
                    4,
                    7,
                    14,
                    0.90
                );

            border-bottom:
                1px solid
                rgba(
                    255,
                    255,
                    255,
                    0.08
                );

            backdrop-filter:
                blur(18px);
        }

        .brand {

            display: flex;
            align-items: center;
            gap: 12px;
        }

        .logo {

            width: 42px;
            height: 42px;

            display: grid;
            place-items: center;

            border-radius: 12px;

            font-size: 15px;
            font-weight: 900;

            color: #061018;

            background:
                linear-gradient(
                    135deg,
                    #00e5ff,
                    #7c4dff
                );

            box-shadow:
                0 0 24px
                rgba(
                    0,
                    229,
                    255,
                    0.25
                );
        }

        .brand-title {

            font-weight: 850;
            font-size: 18px;
        }

        .brand-subtitle {

            color: #7f8ba0;
            font-size: 11px;
            margin-top: 2px;
        }

        .live {

            display: flex;
            align-items: center;
            gap: 7px;

            color: #91a0b5;
            font-size: 12px;
        }

        .live-dot {

            width: 8px;
            height: 8px;

            border-radius: 50%;

            background: #00e676;

            box-shadow:
                0 0 12px
                rgba(
                    0,
                    230,
                    118,
                    0.9
                );
        }

        .container {

            width:
                min(
                    1500px,
                    calc(
                        100% - 32px
                    )
                );

            margin: 0 auto;

            padding:
                24px 0 60px;
        }

        .toolbar {

            display: flex;
            flex-wrap: wrap;
            gap: 10px;

            margin-bottom: 18px;
        }

        select,
        input,
        button {

            border-radius: 10px;

            border:
                1px solid
                rgba(
                    255,
                    255,
                    255,
                    0.09
                );

            color: #fff;

            background:
                rgba(
                    255,
                    255,
                    255,
                    0.055
                );

            padding:
                11px 13px;

            outline: none;

            font-size: 13px;
        }

        select,
        input {

            min-width: 150px;
        }

        input {

            min-width: 190px;
        }

        button {

            cursor: pointer;

            border: none;

            font-weight: 800;

            background:
                linear-gradient(
                    135deg,
                    #00bdf7,
                    #5c52ff
                );

            box-shadow:
                0 8px 24px
                rgba(
                    63,
                    84,
                    255,
                    0.22
                );
        }

        button:hover {

            transform:
                translateY(-1px);
        }

        .btn-secondary {

            background:
                rgba(
                    255,
                    255,
                    255,
                    0.07
                );

            box-shadow: none;
        }

        .section-title {

            margin:
                24px 0 11px;

            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .section-title h2 {

            margin: 0;

            font-size: 17px;

            letter-spacing:
                0.01em;
        }

        .section-title span {

            color: #748198;
            font-size: 11px;
        }

        .card {

            background:
                linear-gradient(
                    180deg,
                    rgba(
                        255,
                        255,
                        255,
                        0.065
                    ),
                    rgba(
                        255,
                        255,
                        255,
                        0.028
                    )
                );

            border:
                1px solid
                rgba(
                    255,
                    255,
                    255,
                    0.075
                );

            border-radius: 17px;

            box-shadow:
                0 16px 42px
                rgba(
                    0,
                    0,
                    0,
                    0.23
                );

            backdrop-filter:
                blur(14px);
        }

        .overview {

            display: grid;

            grid-template-columns:
                repeat(
                    4,
                    1fr
                );

            gap: 13px;
        }

        .overview-card {

            padding: 17px;
        }

        .label {

            color: #77849b;

            text-transform:
                uppercase;

            letter-spacing:
                0.08em;

            font-size: 10px;
        }

        .overview-value {

            margin-top: 7px;

            font-size: 24px;

            font-weight: 850;
        }

        .signals {

            display: grid;

            grid-template-columns:
                repeat(
                    2,
                    1fr
                );

            gap: 13px;
        }

        .signal-card {

            position: relative;

            padding: 17px;

            overflow: hidden;
        }

        .signal-card.long {

            border-left:
                3px solid
                #00e676;
        }

        .signal-card.short {

            border-left:
                3px solid
                #ff5252;
        }

        .signal-top {

            display: flex;

            justify-content:
                space-between;

            align-items:
                flex-start;

            gap: 10px;
        }

        .symbol {

            font-size: 19px;

            font-weight: 900;
        }

        .direction {

            margin-top: 4px;

            font-weight: 900;

            font-size: 14px;
        }

        .long-text {

            color: #00e676;
        }

        .short-text {

            color: #ff5252;
        }

        .confidence {

            padding:
                7px 10px;

            border-radius: 9px;

            font-size: 15px;

            font-weight: 900;
        }

        .confidence.high {

            color: #02150b;

            background:
                linear-gradient(
                    135deg,
                    #00e676,
                    #4dff9e
                );
        }

        .confidence.very-high {

            color: #09110a;

            background:
                linear-gradient(
                    135deg,
                    #b4ff00,
                    #00e676
                );
        }

        .confidence.extreme {

            color: #061019;

            background:
                linear-gradient(
                    135deg,
                    #00e5ff,
                    #00e676
                );
        }

        .signal-grid {

            display: grid;

            grid-template-columns:
                repeat(
                    4,
                    1fr
                );

            gap: 8px;

            margin-top: 15px;
        }

        .mini {

            padding: 9px;

            border-radius: 10px;

            background:
                rgba(
                    255,
                    255,
                    255,
                    0.04
                );
        }

        .mini .mini-label {

            color: #6f7b90;

            font-size: 9px;

            text-transform:
                uppercase;
        }

        .mini .mini-value {

            margin-top: 4px;

            font-size: 12px;

            font-weight: 800;
        }

        .signal-footer {

            display: flex;

            flex-wrap: wrap;

            gap: 7px;

            margin-top: 12px;
        }

        .badge {

            border-radius: 999px;

            padding:
                6px 9px;

            color: #aeb8c7;

            background:
                rgba(
                    255,
                    255,
                    255,
                    0.055
                );

            font-size: 10px;
        }

        .empty {

            padding:
                35px 18px;

            text-align:
                center;

            color: #758197;
        }

        .timeframes {

            display: grid;

            grid-template-columns:
                repeat(
                    4,
                    1fr
                );

            gap: 10px;
        }

        .tf-card {

            padding: 13px;

            border-radius: 13px;

            background:
                rgba(
                    255,
                    255,
                    255,
                    0.04
                );

            border:
                1px solid
                rgba(
                    255,
                    255,
                    255,
                    0.065
                );
        }

        .tf-head {

            display: flex;

            justify-content:
                space-between;
        }

        .tf-name {

            font-weight:
                900;
        }

        .tf-dir {

            font-weight:
                900;
        }

        .tf-row {

            display: flex;

            justify-content:
                space-between;

            color: #7d899c;

            margin-top: 6px;

            font-size: 10px;
        }

        .error {

            margin-top:
                12px;

            color: #ff8a80;

            font-size: 12px;
        }

        .updated {

            color: #69768b;

            font-size: 10px;
        }

        .search-wrap {

            position: relative;

            flex: 1;

            min-width: 280px;
        }

        .search-suggestions {

            display: none;

            position: absolute;

            left: 0;
            right: 0;

            top: 48px;

            z-index: 200;

            max-height: 280px;

            overflow: auto;

            padding: 6px;
        }

        .suggestion {

            padding:
                10px 11px;

            border-radius: 9px;

            cursor: pointer;

            display: flex;

            justify-content:
                space-between;
        }

        .suggestion:hover {

            background:
                rgba(
                    255,
                    255,
                    255,
                    0.06
                );
        }

        .trade-panel {

            display: grid;

            grid-template-columns:
                repeat(
                    4,
                    1fr
                );

            gap: 10px;

            margin-top: 14px;
        }

        .trade-stat {

            padding: 12px;

            border-radius: 12px;

            background:
                rgba(
                    255,
                    255,
                    255,
                    0.04
                );

            border:
                1px solid
                rgba(
                    255,
                    255,
                    255,
                    0.06
                );
        }

        .trade-stat-label {

            color: #718099;

            font-size: 9px;

            text-transform:
                uppercase;

            letter-spacing: 0.06em;
        }

        .trade-stat-value {

            margin-top: 5px;

            font-size: 14px;

            font-weight: 900;
        }

        .decision-execute {
            color: #00e676;
        }

        .decision-watch {
            color: #ffd54f;
        }

        .decision-no-trade {
            color: #ff6b6b;
        }

        .chart-card {

            padding: 0;

            overflow: hidden;
        }

        .chart-toolbar {

            display: flex;

            flex-wrap: wrap;

            align-items: center;

            justify-content: space-between;

            gap: 10px;

            padding: 13px 16px;

            border-bottom:
                1px solid
                rgba(
                    255,
                    255,
                    255,
                    0.06
                );
        }

        .chart-intervals {

            display: flex;

            gap: 6px;

            flex-wrap: wrap;
        }

        .chart-intervals button {

            padding:
                7px 10px;

            font-size: 10px;

            box-shadow: none;
        }

        .chart-intervals button.active {

            background:
                linear-gradient(
                    135deg,
                    #00bdf7,
                    #5c52ff
                );
        }

        .chart-container {

            height: 620px;

            width: 100%;
        }

        .chart-levels {

            display: grid;

            grid-template-columns:
                repeat(
                    5,
                    1fr
                );

            gap: 8px;

            padding: 12px 16px 16px;
        }

        .chart-level {

            padding: 9px 10px;

            border-radius: 10px;

            background:
                rgba(
                    255,
                    255,
                    255,
                    0.035
                );
        }

        .chart-level-label {

            color: #738097;

            font-size: 9px;
        }

        .chart-level-value {

            margin-top: 4px;

            font-size: 12px;

            font-weight: 850;
        }

        @media (
            max-width: 1000px
        ) {

            .trade-panel {

                grid-template-columns:
                    repeat(
                        2,
                        1fr
                    );
            }

            .chart-levels {

                grid-template-columns:
                    repeat(
                        3,
                        1fr
                    );
            }

            .chart-container {
                height: 520px;
            }
        }

        @media (
            max-width: 620px
        ) {

            .trade-panel,
            .chart-levels {

                grid-template-columns:
                    1fr;
            }

            .chart-container {
                height: 440px;
            }
        }

        textarea {

            font-family:
                inherit;

            line-height:
                1.6;
        }

        @media (
            max-width: 1000px
        ) {

            .overview {

                grid-template-columns:
                    repeat(
                        2,
                        1fr
                    );
            }

            .signals {

                grid-template-columns:
                    1fr;
            }

            .timeframes {

                grid-template-columns:
                    repeat(
                        2,
                        1fr
                    );
            }
        }

        @media (
            max-width: 620px
        ) {

            .container {

                width:
                    calc(
                        100% - 20px
                    );
            }

            .overview,
            .timeframes {

                grid-template-columns:
                    1fr;
            }

            .signal-grid {

                grid-template-columns:
                    repeat(
                        2,
                        1fr
                    );
            }

            .toolbar {

                flex-direction:
                    column;
            }

            select,
            input,
            button {

                width:
                    100%;
            }
        }

    </style>

</head>


<body>


<header class="topbar">

    <div class="brand">

        <div class="logo">
            RR
        </div>

        <div>

            <div class="brand-title">
                RR Trader
            </div>

            <div class="brand-subtitle">
                Live Crypto Intelligence Dashboard
            </div>

        </div>

    </div>


    <div class="live">

        <span class="live-dot"></span>

        Live

    </div>

</header>


<main class="container">


    <!-- SEARCH + CONTROLS -->

    <div class="toolbar">

        <div class="search-wrap">

            <input
                id="coinSearch"
                placeholder="Search Futures coin â e.g. BTC, BANK, ZDC"
                autocomplete="off"
                style="width:100%;"
            >

            <div
                id="searchSuggestions"
                class="card search-suggestions"
            ></div>

        </div>


        <select id="market">

            <option value="futures">
                Binance Futures
            </option>

            <option value="spot">
                Binance Spot
            </option>

        </select>


        <select id="filter">

            <option value="90">
                90%+
            </option>

            <option value="95">
                95%+
            </option>

            <option value="99">
                99%+
            </option>

        </select>


        <select id="directionFilter">

            <option value="ALL">
                LONG + SHORT
            </option>

            <option value="LONG">
                LONG
            </option>

            <option value="SHORT">
                SHORT
            </option>

        </select>


        <button
            onclick="analyzeSearchCoin()"
        >
            Analyze Coin
        </button>


        <button
            class="btn-secondary"
            onclick="refreshAutoSignals()"
        >
            Refresh Now
        </button>

    </div>


    <!-- AUTO SCANNER STATUS -->

    <section
        class="card"
        style="
            padding:14px 16px;
            margin-bottom:14px;
            display:flex;
            flex-wrap:wrap;
            align-items:center;
            justify-content:space-between;
            gap:12px;
        "
    >

        <div>

            <strong>
                LIVE AUTO SCANNER
            </strong>

            <div
                id="autoStatusText"
                class="updated"
                style="margin-top:4px;"
            >
                Starting background scanner...
            </div>

        </div>


        <div
            style="
                display:flex;
                gap:8px;
                flex-wrap:wrap;
            "
        >

            <span class="badge">
                Universe:
                <strong id="autoUniverse">
                    0
                </strong>
            </span>


            <span class="badge">
                Deep:
                <strong id="autoDeep">
                    0
                </strong>
            </span>


            <span class="badge">
                Next:
                <strong id="autoNext">
                    60s
                </strong>
            </span>

        </div>

    </section>


    <!-- TOP CANDIDATES -->

    <div class="section-title">

        <h2>
            Top Futures Candidates
        </h2>

        <span>
            Live 150-coin universe
        </span>

    </div>


    <section
        id="candidateGrid"
        class="signals"
        style="
            grid-template-columns:
                repeat(
                    3,
                    1fr
                );
        "
    >

        <div class="card empty">
            Loading candidate universe...
        </div>

    </section>


    <!-- OVERVIEW -->

    <section class="overview">

        <div class="card overview-card">

            <div class="label">
                90%+ Signals
            </div>

            <div
                id="count90"
                class="overview-value"
            >
                0
            </div>

        </div>


        <div class="card overview-card">

            <div class="label">
                95%+ Signals
            </div>

            <div
                id="count95"
                class="overview-value"
            >
                0
            </div>

        </div>


        <div class="card overview-card">

            <div class="label">
                99%+ Signals
            </div>

            <div
                id="count99"
                class="overview-value"
            >
                0
            </div>

        </div>


        <div class="card overview-card">

            <div class="label">
                Coins Scanned
            </div>

            <div
                id="scanned"
                class="overview-value"
            >
                0
            </div>

        </div>

    </section>


    <!-- HIGH CONFIDENCE SIGNALS -->

    <div class="section-title">

        <h2>
            High Confidence Signals
        </h2>

        <div>

            <span id="lastUpdated">
                Waiting for scan...
            </span>

        </div>

    </div>


    <section
        id="signals"
        class="signals"
    >

        <div class="card empty">
            Waiting for the automatic background scan...
        </div>

    </section>


    <div
        id="signalError"
        class="error"
    ></div>


    <!-- SELECTED SYMBOL -->

    <div class="section-title">

        <h2>
            Selected Symbol Analysis
        </h2>

        <span>
            15m â 1h â 4h
        </span>

    </div>


    <section
        id="selectedAnalysis"
        class="card"
        style="
            padding:18px;
        "
    >

        <div class="empty">
            Analyze a symbol to see its full analysis.
        </div>

    </section>


    <!-- TRADE GATE -->

    <div class="section-title">

        <h2>
            24-Point Trade Gate
        </h2>

        <span>
            Paper mode â¢ no live orders
        </span>

    </div>


    <section
        id="tradeGate"
        class="card"
        style="padding:18px; margin-bottom:20px;"
    >

        <div class="empty">
            Analyze a coin to evaluate the full trade gate.
        </div>

    </section>


    <!-- TRADINGVIEW CHART -->

    <div class="section-title">

        <h2>
            TradingView Chart
        </h2>

        <span>
            Draw â¢ edit â¢ analyze
        </span>

    </div>


    <section class="card chart-card">

        <div class="chart-toolbar">

            <div>

                <strong id="chartSymbolLabel">
                    Select a coin
                </strong>

                <div class="updated" style="margin-top:4px;">
                    TradingView Advanced Chart
                </div>

            </div>

            <div class="chart-intervals">

                <button
                    class="btn-secondary chart-interval active"
                    data-interval="15"
                    onclick="setChartInterval('15', this)"
                >
                    15m
                </button>


                <button
                    class="btn-secondary chart-interval"
                    data-interval="60"
                    onclick="setChartInterval('60', this)"
                >
                    1h
                </button>

                <button
                    class="btn-secondary chart-interval"
                    data-interval="240"
                    onclick="setChartInterval('240', this)"
                >
                    4h
                </button>

            </div>

        </div>


        <div
            id="tradingviewChart"
            class="chart-container"
        >

            <div class="empty">
                Search and analyze a Futures coin to load its chart.
            </div>

        </div>


        <div class="chart-levels">

            <div class="chart-level">
                <div class="chart-level-label">ENTRY</div>
                <div class="chart-level-value" id="chartEntry">â</div>
            </div>

            <div class="chart-level">
                <div class="chart-level-label">STOP LOSS</div>
                <div class="chart-level-value" id="chartSL">â</div>
            </div>

            <div class="chart-level">
                <div class="chart-level-label">TP1</div>
                <div class="chart-level-value" id="chartTP1">â</div>
            </div>

            <div class="chart-level">
                <div class="chart-level-label">TP2</div>
                <div class="chart-level-value" id="chartTP2">â</div>
            </div>

            <div class="chart-level">
                <div class="chart-level-label">TP3</div>
                <div class="chart-level-value" id="chartTP3">â</div>
            </div>

        </div>

        <div
            class="updated"
            style="padding:0 16px 15px;"
        >
            Use the TradingView drawing toolbar to manually add or edit support,
            resistance, entry, SL and TP levels on the chart.
        </div>

    </section>


    <!-- PAPER TRADING STATUS -->

    <div class="section-title">

        <h2>
            Paper Trading Engine
        </h2>

        <span>
            No real orders
        </span>

    </div>


    <section
        id="paperStatus"
        class="card"
        style="padding:18px; margin-bottom:20px;"
    >

        <div class="trade-panel">

            <div class="trade-stat">
                <div class="trade-stat-label">Mode</div>
                <div class="trade-stat-value" id="paperMode">â</div>
            </div>

            <div class="trade-stat">
                <div class="trade-stat-label">Balance</div>
                <div class="trade-stat-value" id="paperBalance">â</div>
            </div>

            <div class="trade-stat">
                <div class="trade-stat-label">Open Positions</div>
                <div class="trade-stat-value" id="paperPositions">â</div>
            </div>

            <div class="trade-stat">
                <div class="trade-stat-label">Daily PnL</div>
                <div class="trade-stat-value" id="paperPnl">â</div>
            </div>

        </div>

    </section>


    <!-- POST GENERATOR -->

    <div class="section-title">

        <h2>
            Binance Community Post
        </h2>

        <span>
            Generate â¢ Edit â¢ Copy
        </span>

    </div>


    <section
        class="card"
        style="
            padding:18px;
            margin-bottom:20px;
        "
    >

        <div
            style="
                display:flex;
                gap:10px;
                flex-wrap:wrap;
                margin-bottom:12px;
            "
        >

            <button
                onclick="generateBinancePost()"
            >
                Generate Post
            </button>

            <button
                class="btn-secondary"
                onclick="copyBinancePost()"
            >
                Copy Post
            </button>

            <span
                id="postStatus"
                class="updated"
                style="
                    align-self:center;
                "
            ></span>

        </div>


        <textarea
            id="binancePost"
            placeholder="
Your generated Binance community post will appear here...
            "
            style="
                width:100%;
                min-height:260px;
                resize:vertical;
                padding:14px;
                border-radius:12px;
                border:
                    1px solid
                    rgba(
                        255,
                        255,
                        255,
                        0.10
                    );
                background:
                    rgba(
                        255,
                        255,
                        255,
                        0.045
                    );
                color:#f4f7fb;
                outline:none;
                font-size:14px;
            "
        ></textarea>

    </section>


</main>


<script>

let allSignals = [];
let searchTimer = null;
let autoPollTimer = null;
let selectedAnalysisData = null;
let selectedCoin = "";
let selectedMarket = document.getElementById("market").value || "futures";
let currentChartInterval = "15";


// =========================================================
// UTILITIES
// =========================================================

function number(
    value
) {

    const parsed =
        Number(
            value
        );

    return Number.isNaN(
        parsed
    )
        ? 0
        : parsed;
}


function money(
    value
) {

    if (
        value === null ||
        value === undefined
    ) {

        return "-";

    }

    const n =
        Number(
            value
        );

    if (
        Number.isNaN(n)
    ) {

        return "-";

    }

    return n.toLocaleString(
        undefined,
        {
            maximumFractionDigits:
                6
        }
    );
}


function compact(
    value
) {

    const n =
        number(
            value
        );

    if (
        n >= 1_000_000_000
    ) {

        return (
            n /
            1_000_000_000
        ).toFixed(2) +
        "B";

    }

    if (
        n >= 1_000_000
    ) {

        return (
            n /
            1_000_000
        ).toFixed(2) +
        "M";

    }

    if (
        n >= 1_000
    ) {

        return (
            n /
            1_000
        ).toFixed(2) +
        "K";

    }

    return n.toFixed(
        2
    );
}


function escapeHtml(
    value
) {

    return String(
        value ?? ""
    )
    .replace(
        /&/g,
        "&amp;"
    )
    .replace(
        /</g,
        "&lt;"
    )
    .replace(
        />/g,
        "&gt;"
    )
    .replace(
        /"/g,
        "&quot;"
    )
    .replace(
        /'/g,
        "&#039;"
    );
}


function directionClass(
    direction
) {

    const normalized = String(
        direction || ""
    ).toUpperCase();

    if (normalized === "LONG") {
        return "long-text";
    }

    if (normalized === "SHORT") {
        return "short-text";
    }

    return "updated";
}


function confidenceClass(
    confidence
) {

    if (
        confidence >= 99
    ) {

        return "extreme";

    }

    if (
        confidence >= 95
    ) {

        return "very-high";

    }

    return "high";
}


// =========================================================
// SEARCH
// =========================================================

async function searchCoins(
    query
) {

    const suggestions =
        document.getElementById(
            "searchSuggestions"
        );

    const market =
        document.getElementById(
            "market"
        ).value;

    if (
        market !==
        "futures"
    ) {

        suggestions.style.display =
            "none";

        return;

    }

    const q =
        String(
            query || ""
        )
        .toUpperCase()
        .replace(
            /USDT$/i,
            ""
        )
        .trim();

    if (!q) {

        suggestions.innerHTML =
            "";

        suggestions.style.display =
            "none";

        return;

    }

    try {

        const response =
            await fetch(
                `/api/search?q=${encodeURIComponent(
                    q
                )}&market=futures`
            );

        const data =
            await response.json();

        if (
            !response.ok ||
            !data.success
        ) {

            throw new Error(
                data.detail ||
                "Search failed"
            );

        }

        const coins =
            data.coins || [];

        if (
            coins.length === 0
        ) {

            suggestions.innerHTML =
                `
                <div class="empty">
                    No Futures coin found.
                </div>
                `;

            suggestions.style.display =
                "block";

            return;

        }

        suggestions.innerHTML =
            coins.map(
                item => {

                    const coin =
                        escapeHtml(
                            item.coin ||
                            String(
                                item.symbol ||
                                ""
                            )
                            .replace(
                                /USDT$/i,
                                ""
                            )
                        );

                    const symbol =
                        escapeHtml(
                            item.symbol ||
                            `${coin}USDT`
                        );

                    return `
                        <div
                            class="suggestion"
                            onclick="selectSearchCoin('${coin}')"
                        >
                            <strong>
                                $${coin}
                            </strong>

                            <span class="updated">
                                ${symbol}
                            </span>
                        </div>
                    `;

                }
            ).join("");

        suggestions.style.display =
            "block";

    } catch (err) {

        suggestions.innerHTML =
            `
            <div class="empty">
                ${escapeHtml(
                    err.message ||
                    "Search unavailable."
                )}
            </div>
            `;

        suggestions.style.display =
            "block";

    }
}


function selectSearchCoin(
    coin
) {

    const input =
        document.getElementById(
            "coinSearch"
        );

    input.value =
        String(
            coin || ""
        )
        .toUpperCase()
        .replace(
            /USDT$/i,
            ""
        )
        .trim();

    document.getElementById(
        "searchSuggestions"
    ).style.display =
        "none";

    analyzeSearchCoin();

}


// =========================================================
// SELECTED COIN ANALYSIS
// =========================================================

async function analyzeSearchCoin() {

    const input =
        document.getElementById(
            "coinSearch"
        );

    const coin =
        String(
            input.value || ""
        )
        .toUpperCase()
        .replace(
            /USDT$/i,
            ""
        )
        .trim();

    if (!coin) {

        input.focus();

        return;

    }

    const container =
        document.getElementById(
            "selectedAnalysis"
        );

    container.innerHTML =
        `
        <div class="empty">
            Loading
            ${escapeHtml(
                coin
            )}
            ${escapeHtml(selectedMarket.toUpperCase())} analysis...
        </div>
        `;

    try {

        const response =
            await fetch(
                `/api/analyze?symbol=${encodeURIComponent(
                    coin
                )}&market=${encodeURIComponent(selectedMarket)}`
            );

        const result =
            await response.json();

        if (
            !response.ok
        ) {

            throw new Error(
                result.detail ||
                result.error ||
                "Analysis failed"
            );

        }

        const data =
            result.data ||
            result.analysis ||
            result;

        selectedAnalysisData = data;
        selectedCoin = coin;
        selectedMarket = document.getElementById("market").value || "futures";

        renderSelectedAnalysis(
            data
        );

        updateChartLevels(data);
        renderTradingViewChart(
            coin,
            selectedMarket,
            currentChartInterval
        );

        await evaluateSelectedTrade(data);

    } catch (err) {

        container.innerHTML =
            `
            <div class="empty">
                ${escapeHtml(
                    err.message ||
                    "Unable to analyze coin."
                )}
            </div>
            `;

    }

}


function renderSelectedAnalysis(
    data
) {

    const container =
        document.getElementById(
            "selectedAnalysis"
        );

    const timeframes =
        data.timeframes ||
        {};

    const timeframeOrder = [
        "15m",
        "1h",
        "4h"
    ];

    const cards =
        timeframeOrder
            .map(
                tf => {

                    const item =
                        timeframes[
                            tf
                        ];

                    if (
                        !item
                    ) {

                        return "";

                    }

                    const analysis =
                        item.analysis ||
                        {};

                    const score =
                        item.score ||
                        {};

                    const direction =
                        score.direction ||
                        analysis.direction ||
                        "NEUTRAL";

                    return `
                        <div class="tf-card">

                            <div class="tf-head">

                                <div class="tf-name">
                                    ${tf}
                                </div>

                                <div
                                    class="
                                        tf-dir
                                        ${directionClass(
                                            direction
                                        )}
                                    "
                                >
                                    ${number(
                                        score.confidence ||
                                        0
                                    ).toFixed(0)}%
                                </div>

                            </div>

                            <div
                                class="
                                    tf-dir
                                    ${directionClass(
                                        direction
                                    )}
                                "
                                style="
                                    margin-top:6px;
                                "
                            >
                                ${escapeHtml(
                                    direction
                                )}
                            </div>


                            <div class="tf-row">

                                <span>
                                    Price
                                </span>

                                <span>
                                    ${money(
                                        analysis.price
                                    )}
                                </span>

                            </div>


                            <div class="tf-row">

                                <span>
                                    EMA20
                                </span>

                                <span>
                                    ${money(
                                        analysis.ema20
                                    )}
                                </span>

                            </div>


                            <div class="tf-row">

                                <span>
                                    EMA50
                                </span>

                                <span>
                                    ${money(
                                        analysis.ema50
                                    )}
                                </span>

                            </div>


                            <div class="tf-row">

                                <span>
                                    Momentum
                                </span>

                                <span>
                                    ${number(
                                        analysis.momentum
                                    ).toFixed(4)}%
                                </span>

                            </div>


                            <div class="tf-row">

                                <span>
                                    Volume
                                </span>

                                <span>
                                    ${number(
                                        analysis.volume_ratio
                                    ).toFixed(2)}x
                                </span>

                            </div>

                        </div>
                    `;

                }
            )
            .join("");


    const confidence =
        number(
            data.confidence
        );

    const direction =
        data.direction ||
        "NEUTRAL";


    container.innerHTML =
        `

        <div>

            <div
                style="
                    display:flex;
                    gap:10px;
                    flex-wrap:wrap;
                    margin-bottom:14px;
                "
            >

                <span class="badge">
                    ${escapeHtml(
                        direction
                    )}
                </span>

                <span class="badge">
                    Confidence:
                    ${confidence.toFixed(
                        1
                    )}%
                </span>

                <span class="badge">
                    Entry:
                    ${money(
                        data.entry
                    )}
                </span>

                <span class="badge">
                    SL:
                    ${money(
                        data.stop_loss
                    )}
                </span>

                <span class="badge">
                    R:R:
                    ${number(
                        data.risk_reward
                    ).toFixed(2)}R
                </span>

            </div>


            <div class="timeframes">

                ${cards}

            </div>

        </div>
        `;
}


// =========================================================
// TRADE GATE + CHART
// =========================================================

function decisionClass(
    decision
) {

    const normalized =
        String(
            decision || ""
        ).toUpperCase();

    if (
        normalized ===
        "EXECUTE_CANDIDATE"
    ) {

        return "decision-execute";

    }

    if (
        normalized ===
        "WATCH"
    ) {

        return "decision-watch";

    }

    return "decision-no-trade";
}


function renderTradeGate(
    result
) {

    const container =
        document.getElementById(
            "tradeGate"
        );

    if (!result) {

        container.innerHTML =
            `
            <div class="empty">
                No trade-gate result available.
            </div>
            `;

        return;

    }

    const decision =
        result.decision ||
        "NO_TRADE";

    const score =
        number(
            result.trade_score
        );

    const scannerConfidence =
        number(
            result.scanner_confidence
        );

    const passed =
        number(
            result.passed_confirmations
        );

    const total =
        number(
            result.total_confirmations ||
            24
        );

    const criticalFailures =
        result.critical_failures ||
        [];

    const decisionLabel =
        decision ===
        "EXECUTE_CANDIDATE"
            ? "EXECUTE CANDIDATE"
            : decision ===
              "WATCH"
                ? "WATCH"
                : "NO TRADE";

    const details =
        criticalFailures.length
            ? criticalFailures
                .slice(
                    0,
                    6
                )
                .map(
                    item =>
                        `
                        <span class="badge">
                            ${escapeHtml(
                                item
                            )}
                        </span>
                        `
                )
                .join("")
            : `
                <span class="badge">
                    No critical failures
                </span>
            `;

    container.innerHTML =
        `
        <div>

            <div
                style="
                    display:flex;
                    justify-content:
                        space-between;
                    align-items:center;
                    gap:10px;
                    flex-wrap:wrap;
                "
            >

                <div>

                    <div
                        style="
                            font-size:19px;
                            font-weight:900;
                        "
                    >
                        $${escapeHtml(
                            selectedCoin
                        )}
                    </div>

                    <div
                        class="
                            ${decisionClass(
                                decision
                            )}
                        "
                        style="
                            font-size:14px;
                            font-weight:900;
                            margin-top:5px;
                        "
                    >
                        ${decisionLabel}
                    </div>

                </div>

                <div
                    class="
                        confidence
                        ${confidenceClass(
                            score
                        )}
                    "
                >
                    ${score.toFixed(1)}%
                </div>

            </div>


            <div class="trade-panel">

                <div class="trade-stat">

                    <div class="trade-stat-label">
                        Trade Quality
                    </div>

                    <div class="trade-stat-value">
                        ${score.toFixed(1)}%
                    </div>

                </div>


                <div class="trade-stat">

                    <div class="trade-stat-label">
                        Scanner Confidence
                    </div>

                    <div class="trade-stat-value">
                        ${scannerConfidence.toFixed(1)}%
                    </div>

                </div>


                <div class="trade-stat">

                    <div class="trade-stat-label">
                        Confirmations
                    </div>

                    <div class="trade-stat-value">
                        ${passed}/${total}
                    </div>

                </div>


                <div class="trade-stat">

                    <div class="trade-stat-label">
                        Mode
                    </div>

                    <div class="trade-stat-value">
                        PAPER
                    </div>

                </div>

            </div>


            <div
                class="signal-footer"
                style="margin-top:14px;"
            >

                ${details}

            </div>


            <div
                class="updated"
                style="
                    margin-top:12px;
                "
            >
                95%+ is an execution candidate only when the
                programmed critical gates pass. It does not
                guarantee profit.
            </div>

        </div>
        `;

}


async function evaluateSelectedTrade(
    analysis
) {

    const container =
        document.getElementById(
            "tradeGate"
        );

    try {

        const response =
            await fetch(
                "/api/trade/evaluate",
                {
                    method: "POST",
                    headers: {
                        "Content-Type":
                            "application/json"
                    },
                    body: JSON.stringify(
                        analysis
                    )
                }
            );

        const data =
            await response.json();

        if (
            !response.ok ||
            !data.success
        ) {

            throw new Error(
                data.detail ||
                "Trade evaluation failed."
            );

        }

        renderTradeGate(
            data.result
        );

    } catch (err) {

        container.innerHTML =
            `
            <div class="empty">
                ${escapeHtml(
                    err.message ||
                    "Trade gate unavailable."
                )}
            </div>
            `;

    }
}


function updateChartLevels(
    data
) {

    document.getElementById(
        "chartEntry"
    ).textContent =
        money(
            data.entry
        );

    document.getElementById(
        "chartSL"
    ).textContent =
        money(
            data.stop_loss
        );

    document.getElementById(
        "chartTP1"
    ).textContent =
        money(
            data.tp1
        );

    document.getElementById(
        "chartTP2"
    ).textContent =
        money(
            data.tp2
        );

    document.getElementById(
        "chartTP3"
    ).textContent =
        money(
            data.tp3
        );

}


function tradingViewSymbol(
    coin,
    market
) {

    const clean =
        String(
            coin || ""
        )
        .toUpperCase()
        .replace(
            /USDT$/i,
            ""
        )
        .trim();

    if (
        market ===
        "futures"
    ) {

        return `BINANCE:${clean}USDT.P`;

    }

    return `BINANCE:${clean}USDT`;
}


function renderTradingViewChart(
    coin,
    market = "futures",
    interval = "5"
) {

    const container =
        document.getElementById(
            "tradingviewChart"
        );

    const label =
        document.getElementById(
            "chartSymbolLabel"
        );

    if (!container) {
        return;
    }

    const clean =
        String(
            coin || ""
        )
        .toUpperCase()
        .replace(
            /USDT$/i,
            ""
        )
        .trim();

    if (!clean) {

        container.innerHTML =
            `
            <div class="empty">
                Select a coin to load TradingView.
            </div>
            `;

        return;

    }

    label.textContent =
        `$${clean}`;

    container.innerHTML =
        `
        <div
            class="tradingview-widget-container"
            style="
                height:100%;
                width:100%;
            "
        >

            <div
                class="tradingview-widget-container__widget"
                style="
                    height:100%;
                    width:100%;
                "
            ></div>

            <div
                class="tradingview-widget-copyright"
                style="
                    padding:4px 8px;
                    font-size:9px;
                "
            >
                <a
                    href="https://www.tradingview.com/"
                    rel="noopener nofollow"
                    target="_blank"
                >
                    TradingView
                </a>
            </div>

        </div>
        `;

    const widgetContainer =
        container.querySelector(
            ".tradingview-widget-container"
        );

    const widget =
        document.createElement(
            "script"
        );

    widget.type =
        "text/javascript";

    widget.src =
        "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";

    widget.async =
        true;

    const widgetConfig = {

        autosize: true,

        symbol:
            tradingViewSymbol(
                clean,
                market
            ),

        interval:
            interval,

        timezone:
            "exchange",

        theme:
            "dark",

        style:
            "1",

        locale:
            "en",

        allow_symbol_change:
            true,

        hide_side_toolbar:
            false,

        hide_top_toolbar:
            false,

        hide_legend:
            false,

        hide_volume:
            false,

        save_image:
            true,

        withdateranges:
            true,

        hotlist:
            false,

        calendar:
            false,

        details:
            false,

        studies: [
            "Moving Average Exponential@tv-basicstudies",
            "Moving Average Exponential@tv-basicstudies",
            "RSI@tv-basicstudies"
        ],

        support_host:
            "https://www.tradingview.com"

    };

    widget.innerHTML =
        JSON.stringify(
            widgetConfig
        );

    widgetContainer.appendChild(
        widget
    );


    document
        .querySelectorAll(
            ".chart-interval"
        )
        .forEach(
            button => {

                button.classList.toggle(
                    "active",
                    button.dataset.interval ===
                        String(
                            interval
                        )
                );

            }
        );
}


function setChartInterval(
    interval,
    button
) {

    currentChartInterval =
        String(
            interval
        );

    document
        .querySelectorAll(
            ".chart-interval"
        )
        .forEach(
            item => {
                item.classList.remove(
                    "active"
                );
            }
        );

    if (button) {

        button.classList.add(
            "active"
        );

    }

    if (
        selectedCoin
    ) {

        renderTradingViewChart(
            selectedCoin,
            selectedMarket,
            currentChartInterval
        );

    }

}


async function refreshPaperStatus() {

    try {

        const response =
            await fetch(
                "/api/trade/status"
            );

        const data =
            await response.json();

        if (
            !response.ok ||
            !data.success
        ) {

            return;

        }

        const engine =
            data.engine ||
            {};

        document.getElementById(
            "paperMode"
        ).textContent =
            String(
                engine.mode ||
                "paper"
            ).toUpperCase();

        document.getElementById(
            "paperBalance"
        ).textContent =
            `$${number(
                engine.balance
            ).toFixed(2)}`;

        document.getElementById(
            "paperPositions"
        ).textContent =
            `${number(
                engine.open_positions
            )} / ${number(
                engine.max_open_positions
            )}`;

        document.getElementById(
            "paperPnl"
        ).textContent =
            `$${number(
                engine.daily_realized_pnl
            ).toFixed(2)}`;

    } catch (err) {

        // Keep dashboard alive if the paper
        // trading API is temporarily unavailable.

    }

}


async function refreshAutoTradeGate() {

    try {

        const response =
            await fetch(
                "/api/auto/trades"
            );

        const data =
            await response.json();

        if (
            !response.ok ||
            !data.success
        ) {

            return;

        }

        const evaluations =
            data.trade_evaluations ||
            [];

        const best =
            evaluations
                .slice()
                .sort(
                    (
                        a,
                        b
                    ) =>
                        number(
                            b.trade_score
                        )
                        -
                        number(
                            a.trade_score
                        )
                )[0];

        if (
            best &&
            selectedCoin
            &&
            best.coin ===
                selectedCoin
        ) {

            renderTradeGate(
                best
            );

        }

    } catch (err) {

        // Ignore background status failures.

    }

}


// =========================================================
// AUTO SIGNALS
// =========================================================

function renderSignals() {

    const threshold =
        number(
            document.getElementById(
                "filter"
            ).value
        );

    const directionFilter =
        document.getElementById(
            "directionFilter"
        ).value;

    const container =
        document.getElementById(
            "signals"
        );

    const filtered =
        allSignals.filter(
            signal => {

                const confidence =
                    number(
                        signal.confidence
                    );

                const direction =
                    signal.direction;

                return (
                    confidence >=
                        threshold
                    &&
                    (
                        directionFilter ===
                            "ALL"
                        ||
                        direction ===
                            directionFilter
                    )
                );
            }
        );


    if (
        filtered.length === 0
    ) {

        container.innerHTML =
            `
            <div class="card empty">
                No matching
                ${threshold}%+
                signals right now.
            </div>
            `;

        return;

    }


    container.innerHTML =
        filtered
            .map(
                signal => {

                    const confidence =
                        number(
                            signal.confidence
                        );

                    const direction =
                        signal.direction;

                    const cClass =
                        confidenceClass(
                            confidence
                        );

                    const dClass =
                        direction ===
                        "LONG"
                            ? "long"
                            : "short";

                    const level =
                        signal.confidence_level ||
                        (
                            confidence >=
                            99
                                ? "EXTREME"
                                :
                            confidence >=
                            95
                                ? "VERY HIGH"
                                :
                            confidence >=
                            90
                                ? "HIGH"
                                :
                            "WATCH"
                        );

                    const confirmation =
                        number(
                            signal.confirmation_percent
                        );

                    const reasons =
                        (
                            signal.reasons ||
                            []
                        )
                        .slice(
                            0,
                            4
                        )
                        .map(
                            reason =>
                                `
                                <span class="badge">
                                    ${escapeHtml(
                                        reason
                                    )}
                                </span>
                                `
                        )
                        .join("");


                    return `
                        <div
                            class="
                                card
                                signal-card
                                ${dClass}
                            "
                        >

                            <div
                                class="
                                    signal-top
                                "
                            >

                                <div>

                                    <div class="symbol">

                                        ${escapeHtml(
                                            signal.coin ||
                                            String(
                                                signal.symbol ||
                                                ""
                                            )
                                            .replace(
                                                /USDT$/i,
                                                ""
                                            )
                                        )}

                                    </div>

                                    <div
                                        class="
                                            direction
                                            ${
                                                direction ===
                                                "LONG"
                                                    ? "long-text"
                                                    : "short-text"
                                            }
                                        "
                                    >
                                        ${escapeHtml(
                                            direction
                                        )}
                                    </div>

                                </div>


                                <div
                                    class="
                                        confidence
                                        ${cClass}
                                    "
                                >
                                    ${confidence.toFixed(
                                        1
                                    )}%
                                </div>

                            </div>


                            <div class="signal-footer">

                                <span class="badge">
                                    ${escapeHtml(
                                        level
                                    )}
                                </span>

                                <span class="badge">
                                    ${escapeHtml(
                                        signal.market ||
                                        "futures"
                                    )}
                                </span>

                                ${
                                    confirmation > 0
                                        ? `
                                            <span class="badge">
                                                ${confirmation.toFixed(
                                                    0
                                                )}% confirmations
                                            </span>
                                        `
                                        : ""
                                }

                            </div>


                            <div class="signal-grid">


                                <div class="mini">

                                    <div class="mini-label">
                                        Price
                                    </div>

                                    <div class="mini-value">
                                        ${money(
                                            signal.price
                                        )}
                                    </div>

                                </div>


                                <div class="mini">

                                    <div class="mini-label">
                                        Entry
                                    </div>

                                    <div class="mini-value">
                                        ${money(
                                            signal.entry
                                        )}
                                    </div>

                                </div>


                                <div class="mini">

                                    <div class="mini-label">
                                        Stop Loss
                                    </div>

                                    <div class="mini-value">
                                        ${money(
                                            signal.stop_loss
                                        )}
                                    </div>

                                </div>


                                <div class="mini">

                                    <div class="mini-label">
                                        R:R
                                    </div>

                                    <div class="mini-value">
                                        ${number(
                                            signal.risk_reward
                                        ).toFixed(
                                            2
                                        )}R
                                    </div>

                                </div>


                                <div class="mini">

                                    <div class="mini-label">
                                        TP1
                                    </div>

                                    <div class="mini-value">
                                        ${money(
                                            signal.tp1
                                        )}
                                    </div>

                                </div>


                                <div class="mini">

                                    <div class="mini-label">
                                        TP2
                                    </div>

                                    <div class="mini-value">
                                        ${money(
                                            signal.tp2
                                        )}
                                    </div>

                                </div>


                                <div class="mini">

                                    <div class="mini-label">
                                        TP3
                                    </div>

                                    <div class="mini-value">
                                        ${money(
                                            signal.tp3
                                        )}
                                    </div>

                                </div>


                                <div class="mini">

                                    <div class="mini-label">
                                        24H Volume
                                    </div>

                                    <div class="mini-value">
                                        ${compact(
                                            signal.quote_volume_24h
                                        )}
                                    </div>

                                </div>

                            </div>


                            <div class="signal-footer">

                                ${reasons}

                            </div>

                        </div>
                    `;

                }
            )
            .join("");
}


// =========================================================
// AUTO REFRESH
// =========================================================

async function refreshAutoSignals() {

    try {

        const response =
            await fetch(
                "/api/auto/signals?min_confidence=90"
            );

        const data =
            await response.json();

        if (
            !response.ok ||
            !data.success
        ) {

            throw new Error(
                data.detail ||
                "Auto signal request failed."
            );

        }

        allSignals =
            data.signals || [];

        document.getElementById(
            "scanned"
        ).textContent =
            data.scanned || 0;

        document.getElementById(
            "count90"
        ).textContent =
            allSignals.filter(
                item =>
                    number(
                        item.confidence
                    ) >= 90
            ).length;

        document.getElementById(
            "count95"
        ).textContent =
            allSignals.filter(
                item =>
                    number(
                        item.confidence
                    ) >= 95
            ).length;

        document.getElementById(
            "count99"
        ).textContent =
            allSignals.filter(
                item =>
                    number(
                        item.confidence
                    ) >= 99
            ).length;

        document.getElementById(
            "lastUpdated"
        ).textContent =
            "Updated " +
            new Date()
                .toLocaleTimeString();

        renderSignals();

    } catch (err) {

        document.getElementById(
            "signalError"
        ).textContent =
            err.message ||
            "Unable to refresh signals.";

    }

    refreshAutoStatus();

    refreshCandidates();

    refreshAutoTradeGate();

    refreshPaperStatus();
}


// =========================================================
// AUTO STATUS
// =========================================================

async function refreshAutoStatus() {

    try {

        const response =
            await fetch(
                "/api/auto/status"
            );

        const data =
            await response.json();

        if (
            !response.ok ||
            !data.success
        ) {
            return;
        }

        document.getElementById(
            "autoUniverse"
        ).textContent =
            data.scanned_universe ||
            0;

        document.getElementById(
            "autoDeep"
        ).textContent =
            data.deep_analyzed ||
            0;

        document.getElementById(
            "autoNext"
        ).textContent =
            `${data.next_scan_in_seconds || 0}s`;

        document.getElementById(
            "autoStatusText"
        ).textContent =
            data.running
                ? "Deep analysis is running..."
                : data.error
                    ? (
                        "Scanner error: " +
                        data.error
                    )
                    : "Background scanner is running every 60 seconds.";

    } catch (err) {

        document.getElementById(
            "autoStatusText"
        ).textContent =
            "Auto scanner status unavailable.";

    }
}


// =========================================================
// CANDIDATE LIST
// =========================================================

async function refreshCandidates() {

    const container =
        document.getElementById(
            "candidateGrid"
        );

    try {

        const response =
            await fetch(
                "/api/auto/candidates?limit=12"
            );

        const data =
            await response.json();

        if (
            !response.ok ||
            !data.success
        ) {

            return;

        }

        const candidates =
            data.candidates || [];

        if (
            candidates.length === 0
        ) {

            container.innerHTML =
                `
                <div class="card empty">
                    Waiting for candidate universe...
                </div>
                `;

            return;

        }

        container.innerHTML =
            candidates.map(
                item => {

                    const coin =
                        escapeHtml(
                            item.coin ||
                            String(
                                item.symbol ||
                                ""
                            ).replace(
                                /USDT$/i,
                                ""
                            )
                        );

                    return `
                        <div
                            class="card"
                            style="
                                padding:15px;
                            "
                        >

                            <div
                                style="
                                    display:flex;
                                    justify-content:
                                        space-between;
                                    gap:10px;
                                "
                            >

                                <strong>
                                    $${coin}
                                </strong>

                                <span class="badge">
                                    Score
                                    ${number(
                                        item.candidate_score
                                    ).toFixed(
                                        0
                                    )}
                                </span>

                            </div>


                            <div class="tf-row">

                                <span>
                                    24H Change
                                </span>

                                <span>
                                    ${number(
                                        item.price_change_24h
                                    ).toFixed(
                                        2
                                    )}%
                                </span>

                            </div>


                            <div class="tf-row">

                                <span>
                                    Price
                                </span>

                                <span>
                                    ${money(
                                        item.price
                                    )}
                                </span>

                            </div>


                            <div class="tf-row">

                                <span>
                                    24H Quote Volume
                                </span>

                                <span>
                                    ${compact(
                                        item.quote_volume_24h
                                    )}
                                </span>

                            </div>

                        </div>
                    `;

                }
            ).join("");

    } catch (err) {

        // Keep the existing dashboard
        // alive if the candidate request fails.

    }
}


// =========================================================
// POST GENERATOR
// =========================================================

async function generateBinancePost() {

    const input =
        document.getElementById(
            "coinSearch"
        );

    const postBox =
        document.getElementById(
            "binancePost"
        );

    const status =
        document.getElementById(
            "postStatus"
        );

    const coin =
        String(
            input.value || ""
        )
        .toUpperCase()
        .replace(
            /USDT$/i,
            ""
        )
        .trim();

    if (!coin) {

        status.textContent =
            "Enter a coin first.";

        input.focus();

        return;
    }

    status.textContent =
        "Generating post...";

    postBox.value =
        "";

    try {

        const response =
            await fetch(
                `/api/post/generate?symbol=${encodeURIComponent(
                    coin
                )}&market=${encodeURIComponent(selectedMarket)}`
            );

        const result =
            await response.json();

        if (
            !response.ok
        ) {

            throw new Error(
                result.detail ||
                result.error ||
                "Post generation failed."
            );

        }

        const generated =
            result.post ||
            {};

        postBox.value =
            generated.post ||
            "";

        status.textContent =
            `Generated for $${coin}`;

    } catch (err) {

        status.textContent =
            err.message ||
            "Unable to generate post.";

    }
}


async function copyBinancePost() {

    const postBox =
        document.getElementById(
            "binancePost"
        );

    const status =
        document.getElementById(
            "postStatus"
        );

    const text =
        postBox.value || "";

    if (
        !text.trim()
    ) {

        status.textContent =
            "Generate a post first.";

        return;

    }

    try {

        await navigator.clipboard.writeText(
            text
        );

        status.textContent =
            "Post copied.";

    } catch (err) {

        postBox.select();

        document.execCommand(
            "copy"
        );

        status.textContent =
            "Post copied.";

    }
}


// =========================================================
// EVENT LISTENERS
// =========================================================

document
    .getElementById(
        "filter"
    )
    .addEventListener(
        "change",
        renderSignals
    );


document
    .getElementById(
        "directionFilter"
    )
    .addEventListener(
        "change",
        renderSignals
    );


document
    .getElementById(
        "coinSearch"
    )
    .addEventListener(
        "input",
        event => {

            clearTimeout(
                searchTimer
            );

            searchTimer =
                setTimeout(
                    () => {
                        searchCoins(
                            event.target.value
                        );
                    },
                    250
                );

        }
    );


document
    .getElementById(
        "coinSearch"
    )
    .addEventListener(
        "keydown",
        event => {

            if (
                event.key === "Enter"
            ) {

                event.preventDefault();

                document.getElementById(
                    "searchSuggestions"
                ).style.display =
                    "none";

                analyzeSearchCoin();

            }

        }
    );


document
    .getElementById(
        "market"
    )
    .addEventListener(
        "change",
        () => {

            allSignals = [];

            document.getElementById(
                "searchSuggestions"
            ).style.display =
                "none";

            if (
                document.getElementById(
                    "market"
                ).value ===
                "futures"
            ) {

                searchCoins(
                    document.getElementById(
                        "coinSearch"
                    ).value
                );

            }

            refreshAutoSignals();

        }
    );


// =========================================================
// CLOSE SEARCH SUGGESTIONS
// =========================================================

document.addEventListener(
    "click",
    event => {

        const wrap =
            document.querySelector(
                ".search-wrap"
            );

        if (
            wrap &&
            !wrap.contains(
                event.target
            )
        ) {

            document.getElementById(
                "searchSuggestions"
            ).style.display =
                "none";

        }

    }
);


// =========================================================
// START
// =========================================================

window.addEventListener(
    "load",
    () => {

        refreshAutoSignals();

        autoPollTimer =
            setInterval(
                refreshAutoSignals,
                15_000
            );

    }
);

</script>


</body>
</html>
"""


# =========================================================
# DASHBOARD ROUTE
# =========================================================

@app.get(
    "/dashboard",
    response_class=HTMLResponse,
)
async def dashboard():

    return HTMLResponse(
        content=DASHBOARD_HTML
    )
