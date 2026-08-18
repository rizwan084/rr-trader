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


# =========================================================
# APP
# =========================================================

app = FastAPI(
    title="RR Trader Live Scanner",
    description=(
        "RR Trader Futures scanner, "
        "24-point trade gate and dashboard"
    ),
    version="5.0.0",
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


def _normalize_symbol(
    symbol: str,
) -> str:

    cleaned = (
        str(symbol or "")
        .upper()
        .replace("/", "")
        .replace("-", "")
        .strip()
    )

    if not cleaned:
        return ""

    if not cleaned.endswith("USDT"):
        cleaned = f"{cleaned}USDT"

    return cleaned


# =========================================================
# FULL FUTURES SCANNER CONFIG
# =========================================================
#
# IMPORTANT
# ---------
# AUTO_UNIVERSE_SIZE = None
# means:
#
# ALL active Binance Futures USDT perpetual contracts.
#
# AUTO_DEEP_ANALYSIS_BATCH controls how many expensive
# full analyses happen per 60-second cycle.
#
# We intentionally keep this small to protect Render memory.
# =========================================================

AUTO_SCAN_INTERVAL_SECONDS = 60

AUTO_UNIVERSE_SIZE = None

AUTO_DEEP_ANALYSIS_BATCH = 3


# =========================================================
# BACKGROUND SCANNER STATE
# =========================================================

_auto_scanner_task: Optional[
    asyncio.Task
] = None


_auto_binance = BinanceClient()

_auto_scanner = MarketScanner()


_auto_state: Dict[str, Any] = {
    "running": False,

    "last_scan": None,

    "next_scan_in_seconds":
        AUTO_SCAN_INTERVAL_SECONDS,

    "error": None,

    "market": "futures",

    "universe": [],

    "results": {},

    "signals": [],

    "scanned_universe": 0,

    "scan_total": 0,

    "completed_symbols": 0,

    "scan_cursor": 0,

    "deep_analyzed_last_batch": 0,

    "trade_gate": {
        "execute_candidates": 0,
        "watch": 0,
        "no_trade": 0,
    },
}


# =========================================================
# CANDIDATE PRE-SCORE
# =========================================================

def _candidate_score(
    ticker: Dict[str, Any],
) -> float:
    """
    Cheap ranking only.

    This is NOT the final scanner confidence
    and NOT the trade score.

    It is only used to prioritize the next batch
    while still retaining the COMPLETE Futures universe.
    """

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

    volume_score = min(
        35.0,
        max(
            0.0,
            (
                quote_volume / 10_000_000.0
            ) ** 0.5
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


def _is_valid_futures_ticker(
    ticker: Dict[str, Any],
) -> bool:

    symbol = str(
        ticker.get(
            "symbol",
            "",
        )
    ).upper()

    if not symbol.endswith("USDT"):
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


# =========================================================
# COMPLETE FUTURES UNIVERSE
# =========================================================

async def _build_full_futures_universe() -> List[
    Dict[str, Any]
]:

    """
    Build the complete active Binance Futures USDT
    perpetual universe.

    No artificial 150-coin cap.
    """

    exchange_info = (
        await _auto_binance.exchange_info(
            market="futures"
        )
    )

    if not isinstance(
        exchange_info,
        dict,
    ):
        return []

    raw_symbols = exchange_info.get(
        "symbols",
        [],
    )

    if not isinstance(
        raw_symbols,
        list,
    ):
        return []

    # Get 24h tickers once for cheap ranking.
    tickers = await _auto_binance.ticker_24h(
        market="futures"
    )

    ticker_map: Dict[
        str,
        Dict[str, Any],
    ] = {}

    if isinstance(
        tickers,
        list,
    ):

        for ticker in tickers:

            if not isinstance(
                ticker,
                dict,
            ):
                continue

            symbol = str(
                ticker.get(
                    "symbol",
                    "",
                )
            ).upper()

            ticker_map[
                symbol
            ] = ticker

    universe: List[
        Dict[str, Any]
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

        if not (
            symbol.endswith("USDT")
            and quote_asset == "USDT"
            and status == "TRADING"
            and contract_type == "PERPETUAL"
        ):
            continue

        ticker = ticker_map.get(
            symbol,
            {},
        )

        if ticker and not _is_valid_futures_ticker(
            ticker
        ):
            continue

        universe.append(
            {
                "symbol": symbol,
                "coin": symbol[:-4],
                "market": "futures",
                "price": _safe_float(
                    ticker.get(
                        "lastPrice",
                        0,
                    )
                ),
                "price_change_24h": round(
                    _safe_float(
                        ticker.get(
                            "priceChangePercent",
                            0,
                        )
                    ),
                    4,
                ),
                "quote_volume_24h": _safe_float(
                    ticker.get(
                        "quoteVolume",
                        0,
                    )
                ),
                "candidate_score": _candidate_score(
                    ticker
                )
                if ticker
                else 0.0,
            }
        )

    # Prioritize the strongest movers/liquidity,
    # but retain ALL symbols in the universe.
    universe.sort(
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

    return universe


# =========================================================
# AUTO SCAN CYCLE
# =========================================================

async def _auto_scan_cycle() -> None:

    """
    Full-universe rotating scanner.

    Every cycle:

    1. Load ALL active Futures contracts.
    2. Keep the complete universe in backend state.
    3. Take a small memory-safe batch.
    4. Deep-analyze each symbol.
    5. Run the complete 24-point Trade Gate.
    6. Save the exact backend result.
    7. Advance cursor.
    8. Continue next cycle.

    Dashboard reads this exact stored state.
    """

    _auto_state[
        "running"
    ] = True

    _auto_state[
        "error"
    ] = None

    try:

        universe = (
            await _build_full_futures_universe()
        )

        if not universe:

            raise RuntimeError(
                "Binance Futures universe is empty."
            )

        _auto_state[
            "universe"
        ] = universe

        _auto_state[
            "scanned_universe"
        ] = len(
            universe
        )

        _auto_state[
            "scan_total"
        ] = len(
            universe
        )

        # -------------------------------------------------
        # START / CONTINUE CURSOR
        # -------------------------------------------------

        cursor = int(
            _auto_state.get(
                "scan_cursor",
                0,
            )
        )

        if cursor >= len(
            universe
        ):

            cursor = 0

        batch_size = min(
            AUTO_DEEP_ANALYSIS_BATCH,
            len(universe),
        )

        batch: List[
            Dict[str, Any]
        ] = []

        for offset in range(
            batch_size
        ):

            index = (
                cursor
                + offset
            ) % len(
                universe
            )

            batch.append(
                universe[
                    index
                ]
            )

        # -------------------------------------------------
        # DEEP SCAN
        # -------------------------------------------------

        for candidate in batch:

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

                # -----------------------------------------
                # RUN THE 24-POINT TRADE GATE
                # -----------------------------------------

                trade_decision = (
                    default_trade_engine.evaluate_trade(
                        analysis
                    )
                )

                scanner_confidence = (
                    _safe_float(
                        analysis.get(
                            "confidence",
                            0,
                        )
                    )
                )

                direction = str(
                    analysis.get(
                        "direction",
                        "NEUTRAL",
                    )
                ).upper()

                trade_score = (
                    _safe_float(
                        trade_decision.get(
                            "trade_score",
                            0,
                        )
                    )
                )

                passed_confirmations = int(
                    trade_decision.get(
                        "passed_confirmations",
                        0,
                    )
                )

                total_confirmations = int(
                    trade_decision.get(
                        "total_confirmations",
                        24,
                    )
                )

                decision = (
                    trade_decision.get(
                        "decision",
                        "NO_TRADE",
                    )
                )

                # -----------------------------------------
                # BACKEND RESULT
                # -----------------------------------------

                result = dict(
                    analysis
                )

                result[
                    "symbol"
                ] = symbol

                result[
                    "coin"
                ] = candidate.get(
                    "coin",
                    symbol[:-4],
                )

                result[
                    "scan_complete"
                ] = True

                result[
                    "scanner_confidence"
                ] = scanner_confidence

                result[
                    "trade_score"
                ] = trade_score

                result[
                    "passed_confirmations"
                ] = passed_confirmations

                result[
                    "total_confirmations"
                ] = total_confirmations

                result[
                    "trade_decision"
                ] = decision

                result[
                    "critical_failures"
                ] = trade_decision.get(
                    "critical_failures",
                    [],
                )

                result[
                    "confirmations"
                ] = trade_decision.get(
                    "confirmations",
                    [],
                )

                result[
                    "candidate_score"
                ] = candidate.get(
                    "candidate_score",
                    0,
                )

                result[
                    "confidence_level"
                ] = _confidence_level(
                    scanner_confidence
                )

                result[
                    "backend_scanned_at"
                ] = datetime.now(
                    timezone.utc
                ).isoformat()

                # -----------------------------------------
                # SAVE EXACT RESULT
                # -----------------------------------------

                _auto_state[
                    "results"
                ][symbol] = result

            except Exception as exc:

                _auto_state[
                    "error"
                ] = (
                    f"{symbol}: {exc}"
                )

            finally:

                gc.collect()

        # -------------------------------------------------
        # UPDATE CURSOR
        # -------------------------------------------------

        _auto_state[
            "scan_cursor"
        ] = (
            cursor
            + batch_size
        ) % len(
            universe
        )

        _auto_state[
            "deep_analyzed_last_batch"
        ] = batch_size

        _auto_state[
            "completed_symbols"
        ] = len(
            _auto_state[
                "results"
            ]
        )

        # -------------------------------------------------
        # BUILD SIGNAL VIEW FROM BACKEND RESULTS
        # -------------------------------------------------

        signals = []

        for item in (
            _auto_state[
                "results"
            ].values()
        ):

            if not isinstance(
                item,
                dict,
            ):
                continue

            if not item.get(
                "scan_complete",
                False,
            ):
                continue

            direction = str(
                item.get(
                    "direction",
                    "NEUTRAL",
                )
            ).upper()

            scanner_confidence = (
                _safe_float(
                    item.get(
                        "scanner_confidence",
                        item.get(
                            "confidence",
                            0,
                        ),
                    )
                )
            )

            if (
                direction
                in {
                    "LONG",
                    "SHORT",
                }
                and scanner_confidence >= 90
            ):

                signals.append(
                    item
                )

        signals.sort(
            key=lambda item: (
                _safe_float(
                    item.get(
                        "trade_score",
                        0,
                    )
                ),
                _safe_float(
                    item.get(
                        "scanner_confidence",
                        0,
                    )
                ),
            ),
            reverse=True,
        )

        _auto_state[
            "signals"
        ] = signals

        # -------------------------------------------------
        # TRADE GATE SUMMARY
        # -------------------------------------------------

        execute_count = 0
        watch_count = 0
        no_trade_count = 0

        for item in (
            _auto_state[
                "results"
            ].values()
        ):

            decision = item.get(
                "trade_decision",
                "NO_TRADE",
            )

            if decision == (
                "EXECUTE_CANDIDATE"
            ):

                execute_count += 1

            elif decision == "WATCH":

                watch_count += 1

            else:

                no_trade_count += 1

        _auto_state[
            "trade_gate"
        ] = {
            "execute_candidates":
                execute_count,
            "watch":
                watch_count,
            "no_trade":
                no_trade_count,
        }

        _auto_state[
            "last_scan"
        ] = datetime.now(
            timezone.utc
        ).isoformat()

    except Exception as exc:

        _auto_state[
            "error"
        ] = str(
            exc
        )

    finally:

        _auto_state[
            "running"
        ] = False

        _auto_state[
            "next_scan_in_seconds"
        ] = AUTO_SCAN_INTERVAL_SECONDS

        gc.collect()


# =========================================================
# SCAN LOOP
# =========================================================

async def _auto_scanner_loop() -> None:

    await asyncio.sleep(
        3
    )

    while True:

        try:

            await _auto_scan_cycle()

        except asyncio.CancelledError:

            raise

        except Exception as exc:

            _auto_state[
                "error"
            ] = str(
                exc
            )

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


# =========================================================
# STARTUP / SHUTDOWN
# =========================================================

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

    if (
        _auto_scanner_task is None
    ):

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

    info = await _auto_binance.exchange_info(
        market="futures"
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
            symbol.endswith(
                "USDT"
            )
            and quote_asset == "USDT"
            and status == "TRADING"
            and contract_type == "PERPETUAL"
        ):

            symbols.append(
                {
                    "symbol":
                        symbol,
                    "coin":
                        symbol[:-4],
                    "market":
                        "futures",
                }
            )

    symbols.sort(
        key=lambda item:
            item["coin"]
    )

    _symbol_cache[
        "futures"
    ] = {
        "symbols":
            symbols
    }

    return symbols


# =========================================================
# SEARCH API
# =========================================================

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
        str(q)
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

    symbols = (
        await _load_futures_symbols()
    )

    if not query:

        return {
            "success":
                True,
            "query":
                "",
            "coins":
                symbols[:20],
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
        "success":
            True,
        "query":
            query,
        "coins":
            results,
    }


# =========================================================
# AUTO STATUS API
# =========================================================

@app.get(
    "/api/auto/status"
)
async def auto_scan_status() -> Dict[
    str,
    Any,
]:

    universe_total = _auto_state[
        "scan_total"
    ]

    completed = _auto_state[
        "completed_symbols"
    ]

    completion = (
        (
            completed
            / universe_total
            * 100.0
        )
        if universe_total
        else 0.0
    )

    return {
        "success":
            True,

        "market":
            "futures",

        "running":
            _auto_state[
                "running"
            ],

        "last_scan":
            _auto_state[
                "last_scan"
            ],

        "next_scan_in_seconds":
            _auto_state[
                "next_scan_in_seconds"
            ],

        "universe_total":
            universe_total,

        "completed_symbols":
            completed,

        "completion_percent":
            round(
                completion,
                2,
            ),

        "deep_analyzed_last_batch":
            _auto_state[
                "deep_analyzed_last_batch"
            ],

        "trade_gate":
            _auto_state[
                "trade_gate"
            ],

        "error":
            _auto_state[
                "error"
            ],
    }


# =========================================================
# AUTO SIGNALS API
# =========================================================

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

    signals = []

    for item in (
        _auto_state[
            "signals"
        ]
    ):

        scanner_confidence = (
            _safe_float(
                item.get(
                    "scanner_confidence",
                    item.get(
                        "confidence",
                        0,
                    ),
                )
            )
        )

        if (
            scanner_confidence
            >= min_confidence
        ):

            signals.append(
                item
            )

    return {
        "success":
            True,

        "market":
            "futures",

        "min_confidence":
            min_confidence,

        "scanned":
            _auto_state[
                "scan_total"
            ],

        "completed_symbols":
            _auto_state[
                "completed_symbols"
            ],

        "signals_count":
            len(
                signals
            ),

        "signals":
            signals,

        "last_scan":
            _auto_state[
                "last_scan"
            ],

        "running":
            _auto_state[
                "running"
            ],

        "next_scan_in_seconds":
            _auto_state[
                "next_scan_in_seconds"
            ],

        "trade_gate":
            _auto_state[
                "trade_gate"
            ],
    }


# =========================================================
# AUTO CANDIDATES API
# =========================================================

@app.get(
    "/api/auto/candidates"
)
async def auto_candidates(
    limit: int = Query(
        default=20,
        ge=1,
        le=2000,
    ),
) -> Dict[
    str,
    Any,
]:

    return {
        "success":
            True,

        "market":
            "futures",

        "universe_size":
            _auto_state[
                "scan_total"
            ],

        "candidates":
            _auto_state[
                "universe"
            ][:limit],

        "last_scan":
            _auto_state[
                "last_scan"
            ],
    }


# =========================================================
# EXACT BACKEND RESULT SNAPSHOT
# =========================================================

@app.get(
    "/api/auto/results"
)
async def auto_results(
    min_confidence: float = Query(
        default=0.0,
        ge=0.0,
        le=100.0,
    ),
) -> Dict[
    str,
    Any,
]:

    results = []

    for item in (
        _auto_state[
            "results"
        ].values()
    ):

        scanner_confidence = (
            _safe_float(
                item.get(
                    "scanner_confidence",
                    item.get(
                        "confidence",
                        0,
                    ),
                )
            )
        )

        if (
            scanner_confidence
            >= min_confidence
        ):

            results.append(
                item
            )

    results.sort(
        key=lambda item: (
            _safe_float(
                item.get(
                    "trade_score",
                    0,
                )
            ),
            _safe_float(
                item.get(
                    "scanner_confidence",
                    0,
                )
            ),
        ),
        reverse=True,
    )

    universe_total = _auto_state[
        "scan_total"
    ]

    completed = _auto_state[
        "completed_symbols"
    ]

    completion = (
        (
            completed
            / universe_total
            * 100.0
        )
        if universe_total
        else 0.0
    )

    return {
        "success":
            True,

        "market":
            "futures",

        "universe_total":
            universe_total,

        "completed_symbols":
            completed,

        "completion_percent":
            round(
                completion,
                2,
            ),

        "running":
            _auto_state[
                "running"
            ],

        "scan_cursor":
            _auto_state[
                "scan_cursor"
            ],

        "last_scan":
            _auto_state[
                "last_scan"
            ],

        "next_scan_in_seconds":
            _auto_state[
                "next_scan_in_seconds"
            ],

        "trade_gate":
            _auto_state[
                "trade_gate"
            ],

        "results":
            results,
    }


# =========================================================
# ROOT
# =========================================================

@app.get("/")
async def root():

    return {
        "app":
            "RR Trader Live Scanner",

        "status":
            "online",

        "version":
            "5.0.0",

        "markets":
            [
                "futures",
                "spot",
            ],

        "dashboard":
            "/dashboard",

        "high_confidence_api":
            "/api/signals",

        "post_api":
            "/api/post/generate",

        "trade_status":
            "/api/trade/status",

        "full_scan_status":
            "/api/auto/status",

        "full_scan_results":
            "/api/auto/results",

        "message":
            "RR Trader backend is working",
    }


# =========================================================
# HEALTH
# =========================================================

@app.get(
    "/health"
)
async def health():

    return {
        "success":
            True,
        "status":
            "healthy",
        "service":
            "rr-trader",
    }


# =========================================================
# NORMAL API ROUTES
# =========================================================

app.include_router(
    api_router,
    prefix="/api",
    tags=[
        "RR Trader API"
    ],
)


# =========================================================
# TRADE ENGINE ROUTES
# =========================================================

app.include_router(
    trade_api_router,
    prefix="/api",
    tags=[
        "Trade Engine"
    ],
)


# =========================================================
# DASHBOARD
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
        RR Trader — Full Futures Intelligence
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

            color:
                #f4f7fb;

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

            justify-content:
                space-between;

            align-items:
                center;

            padding:
                14px 24px;

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

            align-items:
                center;

            gap: 12px;
        }

        .logo {

            width: 42px;
            height: 42px;

            display: grid;

            place-items:
                center;

            border-radius: 12px;

            font-size: 15px;

            font-weight: 900;

            color:
                #061018;

            background:
                linear-gradient(
                    135deg,
                    #00e5ff,
                    #7c4dff
                );
        }

        .brand-title {

            font-size: 18px;

            font-weight: 850;
        }

        .brand-subtitle {

            margin-top:
                2px;

            color:
                #7f8ba0;

            font-size: 11px;
        }

        .live {

            display: flex;

            align-items:
                center;

            gap: 7px;

            color:
                #91a0b5;

            font-size: 12px;
        }

        .live-dot {

            width: 8px;
            height: 8px;

            border-radius: 50%;

            background:
                #00e676;
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

            flex-wrap:
                wrap;

            gap: 10px;

            margin-bottom:
                18px;
        }

        select,
        input,
        button {

            border-radius:
                10px;

            border:
                1px solid
                rgba(
                    255,
                    255,
                    255,
                    0.09
                );

            color:
                #fff;

            background:
                rgba(
                    255,
                    255,
                    255,
                    0.055
                );

            padding:
                11px 13px;

            outline:
                none;

            font-size:
                13px;
        }

        input {

            min-width:
                250px;
        }

        button {

            cursor:
                pointer;

            border:
                none;

            font-weight:
                800;

            background:
                linear-gradient(
                    135deg,
                    #00bdf7,
                    #5c52ff
                );
        }

        .btn-secondary {

            background:
                rgba(
                    255,
                    255,
                    255,
                    0.07
                );
        }

        .section-title {

            margin:
                24px 0 11px;

            display: flex;

            justify-content:
                space-between;

            align-items:
                center;
        }

        .section-title h2 {

            margin:
                0;

            font-size:
                17px;
        }

        .section-title span {

            color:
                #748198;

            font-size:
                11px;
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

            border-radius:
                17px;

            box-shadow:
                0 16px 42px
                rgba(
                    0,
                    0,
                    0,
                    0.23
                );
        }

        .status-card {

            padding:
                18px;
        }

        .status-row {

            display:
                grid;

            grid-template-columns:
                repeat(
                    4,
                    1fr
                );

            gap:
                10px;
        }

        .metric {

            padding:
                12px;

            border-radius:
                12px;

            background:
                rgba(
                    255,
                    255,
                    255,
                    0.04
                );
        }

        .metric-label {

            color:
                #77849b;

            text-transform:
                uppercase;

            letter-spacing:
                0.07em;

            font-size:
                9px;
        }

        .metric-value {

            margin-top:
                5px;

            font-size:
                19px;

            font-weight:
                900;
        }

        .signals {

            display:
                grid;

            grid-template-columns:
                repeat(
                    2,
                    1fr
                );

            gap:
                13px;
        }

        .signal-card {

            padding:
                17px;

            border-left:
                3px solid
                #6d7b91;
        }

        .signal-card.long {

            border-left-color:
                #00e676;
        }

        .signal-card.short {

            border-left-color:
                #ff5252;
        }

        .signal-header {

            display:
                flex;

            justify-content:
                space-between;

            gap:
                10px;
        }

        .symbol {

            font-size:
                20px;

            font-weight:
                900;
        }

        .direction-long {

            color:
                #00e676;

            font-weight:
                900;
        }

        .direction-short {

            color:
                #ff5252;

            font-weight:
                900;
        }

        .score-box {

            padding:
                8px 10px;

            border-radius:
                9px;

            background:
                rgba(
                    255,
                    255,
                    255,
                    0.06
                );

            font-weight:
                900;
        }

        .grid-4 {

            display:
                grid;

            grid-template-columns:
                repeat(
                    4,
                    1fr
                );

            gap:
                8px;

            margin-top:
                14px;
        }

        .mini {

            padding:
                9px;

            border-radius:
                10px;

            background:
                rgba(
                    255,
                    255,
                    255,
                    0.04
                );
        }

        .mini-label {

            color:
                #6f7b90;

            font-size:
                9px;

            text-transform:
                uppercase;
        }

        .mini-value {

            margin-top:
                4px;

            font-size:
                12px;

            font-weight:
                800;
        }

        .badges {

            display:
                flex;

            flex-wrap:
                wrap;

            gap:
                7px;

            margin-top:
                12px;
        }

        .badge {

            padding:
                6px 9px;

            border-radius:
                999px;

            color:
                #aeb8c7;

            background:
                rgba(
                    255,
                    255,
                    255,
                    0.055
                );

            font-size:
                10px;
        }

        .empty {

            padding:
                35px 18px;

            text-align:
                center;

            color:
                #758197;
        }

        .search-wrap {

            position:
                relative;

            flex:
                1;

            min-width:
                280px;
        }

        .search-suggestions {

            display:
                none;

            position:
                absolute;

            top:
                48px;

            left:
                0;

            right:
                0;

            z-index:
                200;

            max-height:
                280px;

            overflow:
                auto;

            padding:
                6px;
        }

        .suggestion {

            padding:
                10px;

            border-radius:
                9px;

            cursor:
                pointer;

            display:
                flex;

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

        .trade-gate {

            display:
                grid;

            grid-template-columns:
                repeat(
                    4,
                    1fr
                );

            gap:
                10px;

            margin-top:
                14px;
        }

        .gate-card {

            padding:
                12px;

            border-radius:
                12px;

            background:
                rgba(
                    255,
                    255,
                    255,
                    0.04
                );
        }

        .gate-label {

            color:
                #77849b;

            font-size:
                9px;

            text-transform:
                uppercase;
        }

        .gate-value {

            margin-top:
                5px;

            font-size:
                18px;

            font-weight:
                900;
        }

        .timeframes {

            display:
                grid;

            grid-template-columns:
                repeat(
                    4,
                    1fr
                );

            gap:
                10px;

            margin-top:
                15px;
        }

        .tf {

            padding:
                12px;

            border-radius:
                12px;

            background:
                rgba(
                    255,
                    255,
                    255,
                    0.04
                );
        }

        .tf-head {

            display:
                flex;

            justify-content:
                space-between;
        }

        .chart-shell {

            padding:
                12px;

            overflow:
                hidden;
        }

        .chart-toolbar {

            display:
                flex;

            flex-wrap:
                wrap;

            gap:
                8px;

            margin-bottom:
                10px;
        }

        .chart-btn {

            padding:
                8px 12px;

            border-radius:
                8px;

            background:
                rgba(
                    255,
                    255,
                    255,
                    0.06
                );

            box-shadow:
                none;

            font-size:
                11px;
        }

        .chart-btn.active {

            background:
                linear-gradient(
                    135deg,
                    #00bdf7,
                    #5c52ff
                );
        }

        .chart-container {

            min-height:
                620px;

            width:
                100%;
        }

        textarea {

            width:
                100%;

            min-height:
                260px;

            resize:
                vertical;

            padding:
                14px;

            border-radius:
                12px;

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

            color:
                #f4f7fb;

            outline:
                none;

            font-size:
                14px;

            line-height:
                1.6;
        }

        @media (
            max-width: 1000px
        ) {

            .status-row {

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

            .trade-gate {

                grid-template-columns:
                    repeat(
                        2,
                        1fr
                    );
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

            .status-row,
            .trade-gate,
            .timeframes {

                grid-template-columns:
                    1fr;
            }

            .grid-4 {

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

            input,
            select,
            button {

                width:
                    100%;
            }

            .chart-container {

                min-height:
                    470px;
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
                Full Futures Scanner • 24-Point Trade Gate
            </div>

        </div>

    </div>

    <div class="live">

        <span class="live-dot"></span>

        Live

    </div>

</header>


<main class="container">


    <!-- SEARCH -->

    <div class="toolbar">

        <div class="search-wrap">

            <input
                id="coinSearch"
                placeholder="Search Futures coin — BTC, BANK, ZDC..."
                autocomplete="off"
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
                90%+ Scanner Confidence
            </option>

            <option value="95">
                95%+ Scanner Confidence
            </option>

            <option value="99">
                99%+ Scanner Confidence
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
            Analyze
        </button>


        <button
            class="btn-secondary"
            onclick="refreshAll()"
        >
            Refresh
        </button>

    </div>


    <!-- FULL SCAN STATUS -->

    <div class="section-title">

        <h2>
            Full Binance Futures Scan
        </h2>

        <span>
            Backend snapshot
        </span>

    </div>


    <section
        class="card status-card"
    >

        <div
            style="
                display:flex;
                justify-content:space-between;
                gap:10px;
                flex-wrap:wrap;
            "
        >

            <div>

                <strong
                    id="fullScanStatus"
                >
                    Starting full Futures scanner...
                </strong>

                <div
                    class="updated"
                    id="fullScanProgress"
                    style="
                        margin-top:4px;
                        color:#748198;
                        font-size:11px;
                    "
                >
                    0 / 0 scanned
                </div>

            </div>


            <div
                class="badge"
                id="fullScanDecisionSummary"
            >
                Execute 0 • Watch 0 • No Trade 0
            </div>

        </div>


        <div
            class="status-row"
            style="
                margin-top:14px;
            "
        >

            <div class="metric">

                <div class="metric-label">
                    Futures Universe
                </div>

                <div
                    id="fullUniverse"
                    class="metric-value"
                >
                    0
                </div>

            </div>


            <div class="metric">

                <div class="metric-label">
                    Completed
                </div>

                <div
                    id="fullCompleted"
                    class="metric-value"
                >
                    0
                </div>

            </div>


            <div class="metric">

                <div class="metric-label">
                    Completion
                </div>

                <div
                    id="fullCompletion"
                    class="metric-value"
                >
                    0%
                </div>

            </div>


            <div class="metric">

                <div class="metric-label">
                    Next Batch
                </div>

                <div
                    id="fullNextBatch"
                    class="metric-value"
                >
                    60s
                </div>

            </div>

        </div>

    </section>


    <!-- FULLY SCANNED SIGNALS -->

    <div class="section-title">

        <h2>
            Fully Scanned Signals
        </h2>

        <span>
            Only backend-completed results
        </span>

    </div>


    <section
        id="signals"
        class="signals"
    >

        <div class="card empty">

            Waiting for completed backend scans...

        </div>

    </section>


    <div
        id="signalError"
        style="
            margin-top:10px;
            color:#ff8a80;
            font-size:12px;
        "
    ></div>


    <!-- SELECTED ANALYSIS -->

    <div class="section-title">

        <h2>
            Selected Coin Analysis
        </h2>

        <span>
            5m • 15m • 1h • 4h
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

            Search a Futures coin to analyze it.

        </div>

    </section>


    <!-- TRADINGVIEW -->

    <div class="section-title">

        <h2>
            TradingView Chart
        </h2>

        <span>
            Drawing toolbar enabled
        </span>

    </div>


    <section
        class="card chart-shell"
    >

        <div
            class="chart-toolbar"
        >

            <button
                class="chart-btn active"
                onclick="
                    setChartInterval(
                        '5',
                        this
                    )
                "
            >
                5m
            </button>

            <button
                class="chart-btn"
                onclick="
                    setChartInterval(
                        '15',
                        this
                    )
                "
            >
                15m
            </button>

            <button
                class="chart-btn"
                onclick="
                    setChartInterval(
                        '60',
                        this
                    )
                "
            >
                1h
            </button>

            <button
                class="chart-btn"
                onclick="
                    setChartInterval(
                        '240',
                        this
                    )
                "
            >
                4h
            </button>

        </div>


        <div
            id="tradingviewChart"
            class="chart-container"
        ></div>

    </section>


    <!-- TRADE ENGINE STATUS -->

    <div class="section-title">

        <h2>
            Paper Trade Engine
        </h2>

        <span>
            Real execution is OFF
        </span>

    </div>


    <section
        id="tradeEngineStatus"
        class="card"
        style="
            padding:18px;
        "
    >

        <div class="empty">
            Loading trade engine...
        </div>

    </section>


    <!-- BINANCE POST -->

    <div class="section-title">

        <h2>
            Binance Community Post
        </h2>

        <span>
            Generate • Edit • Copy
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
                flex-wrap:wrap;
                gap:10px;
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
                style="
                    align-self:center;
                    color:#7c899e;
                    font-size:11px;
                "
            ></span>

        </div>


        <textarea
            id="binancePost"
            placeholder="
Generated Binance community post will appear here...
"
        ></textarea>

    </section>


</main>


<script>


// =========================================================
// STATE
// =========================================================

let allSignals = [];

let searchTimer = null;

let selectedCoin = "BTC";

let chartInterval = "5";


// =========================================================
// UTILS
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
        value ===
            null
        ||
        value ===
            undefined
    ) {

        return "-";

    }

    const n =
        Number(
            value
        );

    if (
        Number.isNaN(
            n
        )
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
        n >=
        1_000_000_000
    ) {

        return (
            n
            /
            1_000_000_000
        ).toFixed(
            2
        ) + "B";

    }

    if (
        n >=
        1_000_000
    ) {

        return (
            n
            /
            1_000_000
        ).toFixed(
            2
        ) + "M";

    }

    if (
        n >=
        1_000
    ) {

        return (
            n
            /
            1_000
        ).toFixed(
            2
        ) + "K";

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

    return (
        direction ===
        "LONG"
    )
        ? "direction-long"
        : "direction-short";
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
            !response.ok
            ||
            !data.success
        ) {

            throw new Error(
                data.detail
                ||
                "Search failed"
            );

        }

        const coins =
            data.coins
            ||
            [];

        if (
            coins.length ===
            0
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
            coins
                .map(
                    item => {

                        const coin =
                            escapeHtml(
                                item.coin
                                ||
                                String(
                                    item.symbol
                                    ||
                                    ""
                                )
                                .replace(
                                    /USDT$/i,
                                    ""
                                )
                            );

                        return `
                        <div
                            class="suggestion"
                            onclick="
                                selectSearchCoin(
                                    '${coin}'
                                )
                            "
                        >
                            <strong>
                                $${coin}
                            </strong>

                            <span
                                style="
                                    color:#748198;
                                    font-size:10px;
                                "
                            >
                                ${escapeHtml(
                                    item.symbol
                                    ||
                                    `${coin}USDT`
                                )}
                            </span>
                        </div>
                        `;

                    }
                )
                .join("");

        suggestions.style.display =
            "block";

    } catch (
        err
    ) {

        suggestions.innerHTML =
            `
            <div class="empty">
                ${escapeHtml(
                    err.message
                    ||
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
// SELECTED ANALYSIS
// =========================================================

async function analyzeSearchCoin() {

    const input =
        document.getElementById(
            "coinSearch"
        );

    const coin =
        String(
            input.value
            ||
            ""
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

    selectedCoin =
        coin;

    renderTradingView();

    const container =
        document.getElementById(
            "selectedAnalysis"
        );

    container.innerHTML =
        `
        <div class="empty">
            Loading ${escapeHtml(
                coin
            )} full analysis...
        </div>
        `;

    try {

        const response =
            await fetch(
                `/api/analyze?symbol=${encodeURIComponent(
                    coin
                )}&market=futures`
            );

        const result =
            await response.json();

        if (
            !response.ok
        ) {

            throw new Error(
                result.detail
                ||
                result.error
                ||
                "Analysis failed"
            );

        }

        const data =
            result.data
            ||
            result.analysis
            ||
            result;

        // -----------------------------------------
        // Pass the exact selected analysis through
        // the same backend trade gate endpoint.
        // -----------------------------------------

        let gated =
            null;

        try {

            const gateResponse =
                await fetch(
                    "/api/trade/evaluate",
                    {
                        method:
                            "POST",

                        headers: {
                            "Content-Type":
                                "application/json",
                        },

                        body:
                            JSON.stringify(
                                data
                            ),
                    }
                );

            const gateJson =
                await gateResponse.json();

            if (
                gateResponse.ok
                &&
                gateJson.success
            ) {

                gated =
                    gateJson.result;

            }

        } catch (
            _
        ) {
            gated = null;
        }

        if (
            gated
        ) {

            data.trade_score =
                number(
                    gated.trade_score
                );

            data.passed_confirmations =
                number(
                    gated.passed_confirmations
                );

            data.total_confirmations =
                number(
                    gated.total_confirmations
                )
                ||
                24;

            data.trade_decision =
                gated.decision
                ||
                "NO_TRADE";

            data.critical_failures =
                gated.critical_failures
                ||
                [];

        }

        renderSelectedAnalysis(
            data
        );

    } catch (
        err
    ) {

        container.innerHTML =
            `
            <div class="empty">
                ${escapeHtml(
                    err.message
                    ||
                    "Unable to analyze coin."
                )}
            </div>
            `;

    }
}


// =========================================================
// SELECTED ANALYSIS RENDER
// =========================================================

function renderSelectedAnalysis(
    data
) {

    const container =
        document.getElementById(
            "selectedAnalysis"
        );

    const timeframes =
        data.timeframes
        ||
        {};

    const order = [
        "5m",
        "15m",
        "1h",
        "4h",
    ];

    const cards =
        order
            .map(
                timeframe => {

                    const item =
                        timeframes[
                            timeframe
                        ];

                    if (
                        !item
                    ) {

                        return `
                        <div class="tf">

                            <strong>
                                ${timeframe}
                            </strong>

                            <div
                                style="
                                    margin-top:6px;
                                    color:#748198;
                                    font-size:11px;
                                "
                            >
                                No backend data
                            </div>

                        </div>
                        `;

                    }

                    const analysis =
                        item.analysis
                        ||
                        {};

                    const score =
                        item.score
                        ||
                        {};

                    const direction =
                        score.direction
                        ||
                        analysis.direction
                        ||
                        "NEUTRAL";

                    return `
                    <div class="tf">

                        <div
                            class="tf-head"
                        >

                            <strong>
                                ${timeframe}
                            </strong>

                            <span
                                class="${directionClass(
                                    direction
                                )}"
                            >
                                ${number(
                                    score.confidence
                                    ||
                                    0
                                ).toFixed(
                                    1
                                )}%
                            </span>

                        </div>

                        <div
                            class="${directionClass(
                                direction
                            )}"
                            style="
                                margin-top:5px;
                                font-size:12px;
                                font-weight:900;
                            "
                        >
                            ${escapeHtml(
                                direction
                            )}
                        </div>

                        <div
                            style="
                                display:flex;
                                justify-content:space-between;
                                margin-top:8px;
                                color:#7d899c;
                                font-size:10px;
                            "
                        >
                            <span>
                                Price
                            </span>

                            <span>
                                ${money(
                                    analysis.price
                                )}
                            </span>
                        </div>

                        <div
                            style="
                                display:flex;
                                justify-content:space-between;
                                margin-top:5px;
                                color:#7d899c;
                                font-size:10px;
                            "
                        >
                            <span>
                                EMA20
                            </span>

                            <span>
                                ${money(
                                    analysis.ema20
                                )}
                            </span>
                        </div>

                        <div
                            style="
                                display:flex;
                                justify-content:space-between;
                                margin-top:5px;
                                color:#7d899c;
                                font-size:10px;
                            "
                        >
                            <span>
                                EMA50
                            </span>

                            <span>
                                ${money(
                                    analysis.ema50
                                )}
                            </span>
                        </div>

                    </div>
                    `;

                }
            )
            .join("");

    const scannerConfidence =
        number(
            data.scanner_confidence
            ||
            data.confidence
        );

    const tradeScore =
        number(
            data.trade_score
        );

    const passed =
        number(
            data.passed_confirmations
        );

    const total =
        number(
            data.total_confirmations
        )
        ||
        24;

    const decision =
        data.trade_decision
        ||
        "NOT_EVALUATED";

    const direction =
        data.direction
        ||
        "NEUTRAL";


    container.innerHTML =
        `
        <div>

            <div
                class="badges"
            >

                <span class="badge">
                    $${escapeHtml(
                        data.coin
                        ||
                        data.symbol
                        ||
                        selectedCoin
                    )}
                </span>

                <span
                    class="${directionClass(
                        direction
                    )}"
                >
                    ${escapeHtml(
                        direction
                    )}
                </span>

                <span class="badge">
                    Scanner:
                    ${scannerConfidence.toFixed(
                        1
                    )}%
                </span>

                <span class="badge">
                    Trade Quality:
                    ${tradeScore.toFixed(
                        1
                    )}%
                </span>

                <span class="badge">
                    Confirmations:
                    ${passed}/${total}
                </span>

            </div>


            <div
                class="trade-gate"
            >

                <div class="gate-card">

                    <div class="gate-label">
                        Scanner Confidence
                    </div>

                    <div class="gate-value">
                        ${scannerConfidence.toFixed(
                            1
                        )}%
                    </div>

                </div>


                <div class="gate-card">

                    <div class="gate-label">
                        Trade Quality
                    </div>

                    <div class="gate-value">
                        ${tradeScore.toFixed(
                            1
                        )}%
                    </div>

                </div>


                <div class="gate-card">

                    <div class="gate-label">
                        24-Point Gate
                    </div>

                    <div class="gate-value">
                        ${passed}/${total}
                    </div>

                </div>


                <div class="gate-card">

                    <div class="gate-label">
                        Decision
                    </div>

                    <div class="gate-value">
                        ${escapeHtml(
                            decision
                        )}
                    </div>

                </div>

            </div>


            <div
                class="badges"
            >

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
                    TP1:
                    ${money(
                        data.tp1
                    )}
                </span>

                <span class="badge">
                    TP2:
                    ${money(
                        data.tp2
                    )}
                </span>

                <span class="badge">
                    TP3:
                    ${money(
                        data.tp3
                    )}
                </span>

            </div>


            <div
                class="timeframes"
            >

                ${cards}

            </div>


            ${
                (
                    data.critical_failures
                    ||
                    []
                ).length
                    ?
                    `
                    <div
                        class="badges"
                    >

                        <span
                            class="badge"
                            style="
                                color:#ff8a80;
                            "
                        >
                            Critical:
                            ${escapeHtml(
                                (
                                    data.critical_failures
                                    ||
                                    []
                                )
                                .join(
                                    ", "
                                )
                            )}
                        </span>

                    </div>
                    `
                    :
                    ""
            }

        </div>
        `;
}


// =========================================================
// SIGNALS FROM BACKEND ONLY
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
                        signal.scanner_confidence
                        ||
                        signal.confidence
                    );

                const direction =
                    signal.direction
                    ||
                    "NEUTRAL";

                return (
                    confidence
                    >=
                    threshold
                    &&
                    (
                        directionFilter
                        ===
                        "ALL"
                        ||
                        direction
                        ===
                        directionFilter
                    )
                );
            }
        );

    if (
        filtered.length ===
        0
    ) {

        container.innerHTML =
            `
            <div class="card empty">
                No completed backend scan
                currently matches the filter.
            </div>
            `;

        return;

    }


    container.innerHTML =
        filtered
            .map(
                signal => {

                    const scannerConfidence =
                        number(
                            signal.scanner_confidence
                            ||
                            signal.confidence
                        );

                    const tradeScore =
                        number(
                            signal.trade_score
                        );

                    const passed =
                        number(
                            signal.passed_confirmations
                        );

                    const total =
                        number(
                            signal.total_confirmations
                        )
                        ||
                        24;

                    const direction =
                        signal.direction
                        ||
                        "NEUTRAL";

                    const decision =
                        signal.trade_decision
                        ||
                        "NO_TRADE";

                    const cardClass =
                        direction ===
                        "LONG"
                            ? "long"
                            :
                            direction ===
                            "SHORT"
                                ? "short"
                                :
                                "";

                    return `
                    <div
                        class="
                            card
                            signal-card
                            ${cardClass}
                        "
                    >

                        <div
                            class="signal-header"
                        >

                            <div>

                                <div
                                    class="symbol"
                                >
                                    $${escapeHtml(
                                        signal.coin
                                        ||
                                        String(
                                            signal.symbol
                                            ||
                                            ""
                                        )
                                        .replace(
                                            /USDT$/i,
                                            ""
                                        )
                                    )}
                                </div>

                                <div
                                    class="${directionClass(
                                        direction
                                    )}"
                                >
                                    ${escapeHtml(
                                        direction
                                    )}
                                </div>

                            </div>


                            <div
                                class="score-box"
                            >
                                ${tradeScore.toFixed(
                                    1
                                )}%
                            </div>

                        </div>


                        <div
                            class="badges"
                        >

                            <span class="badge">
                                FULLY SCANNED
                            </span>

                            <span class="badge">
                                Scanner
                                ${scannerConfidence.toFixed(
                                    1
                                )}%
                            </span>

                            <span class="badge">
                                Gate
                                ${passed}/${total}
                            </span>

                            <span class="badge">
                                ${escapeHtml(
                                    decision
                                )}
                            </span>

                        </div>


                        <div
                            class="grid-4"
                        >

                            <div class="mini">

                                <div
                                    class="mini-label"
                                >
                                    Entry
                                </div>

                                <div
                                    class="mini-value"
                                >
                                    ${money(
                                        signal.entry
                                    )}
                                </div>

                            </div>


                            <div class="mini">

                                <div
                                    class="mini-label"
                                >
                                    SL
                                </div>

                                <div
                                    class="mini-value"
                                >
                                    ${money(
                                        signal.stop_loss
                                    )}
                                </div>

                            </div>


                            <div class="mini">

                                <div
                                    class="mini-label"
                                >
                                    TP1
                                </div>

                                <div
                                    class="mini-value"
                                >
                                    ${money(
                                        signal.tp1
                                    )}
                                </div>

                            </div>


                            <div class="mini">

                                <div
                                    class="mini-label"
                                >
                                    R:R
                                </div>

                                <div
                                    class="mini-value"
                                >
                                    ${
                                        number(
                                            signal.risk_reward
                                        ).toFixed(
                                            2
                                        )
                                    }R
                                </div>

                            </div>

                        </div>


                        <div
                            class="badges"
                        >

                            <button
                                class="btn-secondary"
                                onclick="
                                    inspectBackendCoin(
                                        '${escapeHtml(
                                            signal.coin
                                            ||
                                            String(
                                                signal.symbol
                                                ||
                                                ""
                                            )
                                            .replace(
                                                /USDT$/i,
                                                ""
                                            )
                                    )}'
                                "
                            >
                                Open Analysis
                            </button>

                        </div>

                    </div>
                    `;

                }
            )
            .join("");
}


// =========================================================
// OPEN BACKEND-SCANNED COIN
// =========================================================

function inspectBackendCoin(
    coin
) {

    const input =
        document.getElementById(
            "coinSearch"
        );

    input.value =
        String(
            coin
        )
        .toUpperCase()
        .replace(
            /USDT$/i,
            ""
        );

    analyzeSearchCoin();

}


// =========================================================
// FULL BACKEND SNAPSHOT
// =========================================================

async function refreshFullScan() {

    try {

        const response =
            await fetch(
                "/api/auto/results?min_confidence=90"
            );

        const data =
            await response.json();

        if (
            !response.ok
            ||
            !data.success
        ) {

            throw new Error(
                data.detail
                ||
                "Full scan unavailable."
            );

        }

        document.getElementById(
            "fullUniverse"
        ).textContent =
            data.universe_total
            ||
            0;

        document.getElementById(
            "fullCompleted"
        ).textContent =
            data.completed_symbols
            ||
            0;

        document.getElementById(
            "fullCompletion"
        ).textContent =
            `${number(
                data.completion_percent
            ).toFixed(
                2
            )}%`;

        document.getElementById(
            "fullNextBatch"
        ).textContent =
            `${data.next_scan_in_seconds || 0}s`;

        document.getElementById(
            "fullScanProgress"
        ).textContent =
            `${data.completed_symbols || 0} / ${data.universe_total || 0} scanned`;

        document.getElementById(
            "fullScanStatus"
        ).textContent =
            data.running
                ? "Full Futures scan is running..."
                : "Backend scan snapshot is live.";

        const gate =
            data.trade_gate
            ||
            {};

        document.getElementById(
            "fullScanDecisionSummary"
        ).textContent =
            `Execute ${gate.execute_candidates || 0} • Watch ${gate.watch || 0} • No Trade ${gate.no_trade || 0}`;

        allSignals =
            data.results
            ||
            [];

        renderSignals();

    } catch (
        err
    ) {

        document.getElementById(
            "fullScanStatus"
        ).textContent =
            err.message
            ||
            "Full scan unavailable.";

    }
}


// =========================================================
// TRADE ENGINE STATUS
// =========================================================

async function refreshTradeEngineStatus() {

    const container =
        document.getElementById(
            "tradeEngineStatus"
        );

    try {

        const response =
            await fetch(
                "/api/trade/status"
            );

        const data =
            await response.json();

        if (
            !response.ok
            ||
            !data.success
        ) {

            throw new Error(
                data.detail
                ||
                "Trade engine unavailable."
            );

        }

        const engine =
            data.engine
            ||
            {};

        const config =
            data.config
            ||
            {};

        container.innerHTML =
            `
            <div
                class="trade-gate"
            >

                <div class="gate-card">

                    <div class="gate-label">
                        Mode
                    </div>

                    <div class="gate-value">
                        ${escapeHtml(
                            engine.mode
                            ||
                            "paper"
                        )}
                    </div>

                </div>


                <div class="gate-card">

                    <div class="gate-label">
                        Balance
                    </div>

                    <div class="gate-value">
                        $${number(
                            engine.balance
                        ).toFixed(
                            2
                        )}
                    </div>

                </div>


                <div class="gate-card">

                    <div class="gate-label">
                        Execute Threshold
                    </div>

                    <div class="gate-value">
                        ${number(
                            config.execute_threshold
                        ).toFixed(
                            0
                        )}%
                    </div>

                </div>


                <div class="gate-card">

                    <div class="gate-label">
                        Risk / Trade
                    </div>

                    <div class="gate-value">
                        ${number(
                            config.risk_per_trade_percent
                        ).toFixed(
                            2
                        )}%
                    </div>

                </div>

            </div>
            `;

    } catch (
        err
    ) {

        container.innerHTML =
            `
            <div class="empty">
                ${escapeHtml(
                    err.message
                    ||
                    "Trade engine unavailable."
                )}
            </div>
            `;

    }
}


// =========================================================
// TRADINGVIEW
// =========================================================

function renderTradingView() {

    const container =
        document.getElementById(
            "tradingviewChart"
        );

    if (!container) {
        return;
    }

    container.innerHTML =
        "";

    const wrapper =
        document.createElement(
            "div"
        );

    wrapper.className =
        "tradingview-widget-container";

    wrapper.style.width =
        "100%";

    wrapper.style.height =
        "100%";


    const widget =
        document.createElement(
            "div"
        );

    widget.className =
        "tradingview-widget-container__widget";

    widget.style.width =
        "100%";

    widget.style.height =
        "100%";


    const script =
        document.createElement(
            "script"
        );

    script.type =
        "text/javascript";

    script.src =
        "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";

    script.async =
        true;

    script.textContent =
        JSON.stringify(
            {
                autosize:
                    true,

                symbol:
                    `BINANCE:${selectedCoin}USDT`,

                interval:
                    chartInterval,

                timezone:
                    "Etc/UTC",

                theme:
                    "dark",

                style:
                    "1",

                locale:
                    "en",

                allow_symbol_change:
                    false,

                hide_side_toolbar:
                    false,

                withdateranges:
                    true,

                hide_volume:
                    false,

                support_host:
                    "https://www.tradingview.com",
            }
        );


    wrapper.appendChild(
        widget
    );

    wrapper.appendChild(
        script
    );

    container.appendChild(
        wrapper
    );
}


function setChartInterval(
    interval,
    button
) {

    chartInterval =
        String(
            interval
        );

    document
        .querySelectorAll(
            ".chart-btn"
        )
        .forEach(
            btn => {
                btn.classList.remove(
                    "active"
                );
            }
        );

    if (button) {

        button.classList.add(
            "active"
        );

    }

    renderTradingView();
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
            input.value
            ||
            ""
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
                )}&market=futures`
            );

        const result =
            await response.json();

        if (
            !response.ok
        ) {

            throw new Error(
                result.detail
                ||
                result.error
                ||
                "Post generation failed."
            );

        }

        const generated =
            result.post
            ||
            {};

        postBox.value =
            generated.post
            ||
            "";

        status.textContent =
            `Generated for $${coin}`;

    } catch (
        err
    ) {

        status.textContent =
            err.message
            ||
            "Unable to generate post.";

    }
}


async function copyBinancePost() {

    const box =
        document.getElementById(
            "binancePost"
        );

    const status =
        document.getElementById(
            "postStatus"
        );

    const text =
        box.value
        ||
        "";

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

    } catch (
        _
    ) {

        box.select();

        document.execCommand(
            "copy"
        );

        status.textContent =
            "Post copied.";
    }
}


// =========================================================
// REFRESH ALL
// =========================================================

async function refreshAll() {

    await refreshFullScan();

    await refreshTradeEngineStatus();

}


// =========================================================
// EVENTS
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
                event.key
                ===
                "Enter"
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

            document.getElementById(
                "searchSuggestions"
            ).style.display =
                "none";

            refreshAll();

        }
    );


document.addEventListener(
    "click",
    event => {

        const wrap =
            document.querySelector(
                ".search-wrap"
            );

        if (
            wrap
            &&
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
// START DASHBOARD
// =========================================================

window.addEventListener(
    "load",
    () => {

        renderTradingView();

        refreshAll();

        setInterval(
            refreshAll,
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
        content=
            DASHBOARD_HTML
    )
