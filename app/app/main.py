from __future__ import annotations

from typing import Any, Dict, List

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

from app.app.api.routes import router as api_router
from app.app.services.scanner import MarketScanner


app = FastAPI(
    title="RR Trader Live Scanner",
    description="AI-powered Binance Spot and Futures market scanner",
    version="3.0.0",
)


# =========================================================
# HELPERS
# =========================================================

def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _confidence_level(confidence: float) -> str:
    if confidence >= 99:
        return "EXTREME"
    if confidence >= 95:
        return "VERY HIGH"
    if confidence >= 90:
        return "HIGH"
    if confidence >= 85:
        return "WATCH"
    return "LOW"


def _signal_sort_key(item: Dict[str, Any]):
    return _safe_float(
        item.get("confidence", 0)
    )


# =========================================================
# HIGH CONFIDENCE SIGNAL API
# =========================================================

@app.get("/api/signals")
async def high_confidence_signals(
    market: str = Query(
        default="futures",
        description="futures or spot",
    ),
    min_confidence: float = Query(
        default=90,
        ge=0,
        le=100,
        description="Minimum confidence",
    ),
    max_candidates: int = Query(
        default=30,
        ge=1,
        le=50,
        description="Number of coins to scan",
    ),
) -> Dict[str, Any]:

    market = market.lower().strip()

    if market not in {"futures", "spot"}:
        return {
            "success": False,
            "detail": (
                "market must be either "
                "'futures' or 'spot'"
            ),
        }

    scanner = MarketScanner()

    result = await scanner.scan(
        market=market,
        max_candidates=max_candidates,
    )

    candidates = result.get(
        "candidates",
        [],
    )

    signals: List[
        Dict[str, Any]
    ] = []

    for item in candidates:

        if not item.get(
            "success",
            False,
        ):
            continue

        confidence = _safe_float(
            item.get(
                "confidence",
                0,
            )
        )

        direction = item.get(
            "direction",
            "NEUTRAL",
        )

        if (
            confidence >= min_confidence
            and direction in {
                "LONG",
                "SHORT",
            }
        ):

            enriched = dict(item)

            enriched[
                "confidence_level"
            ] = _confidence_level(
                confidence
            )

            signals.append(
                enriched
            )

    signals.sort(
        key=_signal_sort_key,
        reverse=True,
    )

    return {
        "success": True,
        "market": market,
        "min_confidence": min_confidence,
        "scanned": len(candidates),
        "signals_count": len(signals),
        "signals": signals,
    }


# =========================================================
# ROOT
# =========================================================

@app.get("/")
async def root():
    return {
        "app": "RR Trader Live Scanner",
        "status": "online",
        "version": "3.0.0",
        "markets": [
            "futures",
            "spot",
        ],
        "dashboard": "/dashboard",
        "high_confidence_api": "/api/signals",
        "message": "RR Trader backend is working",
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
    tags=["RR Trader API"],
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

    <title>RR Trader Dashboard</title>

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
                rgba(4, 7, 14, 0.90);

            border-bottom:
                1px solid rgba(255,255,255,0.08);

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
                rgba(0, 229, 255, 0.25);
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
                rgba(0, 230, 118, 0.9);
        }

        .container {

            width: min(
                1500px,
                calc(100% - 32px)
            );

            margin: 0 auto;

            padding: 24px 0 60px;
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
                rgba(255,255,255,0.09);

            color: #fff;

            background:
                rgba(255,255,255,0.055);

            padding: 11px 13px;

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
                rgba(63, 84, 255, 0.22);
        }

        button:hover {
            transform: translateY(-1px);
        }

        .btn-secondary {
            background:
                rgba(255,255,255,0.07);
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

            letter-spacing: 0.01em;
        }

        .section-title span {

            color: #748198;
            font-size: 11px;
        }

        .card {

            background:
                linear-gradient(
                    180deg,
                    rgba(255,255,255,0.065),
                    rgba(255,255,255,0.028)
                );

            border:
                1px solid
                rgba(255,255,255,0.075);

            border-radius: 17px;

            box-shadow:
                0 16px 42px
                rgba(0,0,0,0.23);

            backdrop-filter:
                blur(14px);
        }

        .overview {

            display: grid;

            grid-template-columns:
                repeat(4, 1fr);

            gap: 13px;
        }

        .overview-card {
            padding: 17px;
        }

        .label {

            color: #77849b;

            text-transform: uppercase;

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
                repeat(2, 1fr);

            gap: 13px;
        }

        .signal-card {

            position: relative;

            padding: 17px;

            overflow: hidden;
        }

        .signal-card.long {
            border-left:
                3px solid #00e676;
        }

        .signal-card.short {
            border-left:
                3px solid #ff5252;
        }

        .signal-top {

            display: flex;

            justify-content:
                space-between;

            align-items: flex-start;

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

            padding: 7px 10px;

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
                repeat(4, 1fr);

            gap: 8px;

            margin-top: 15px;
        }

        .mini {

            padding: 9px;

            border-radius: 10px;

            background:
                rgba(255,255,255,0.04);
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

            padding: 6px 9px;

            color: #aeb8c7;

            background:
                rgba(255,255,255,0.055);

            font-size: 10px;
        }

        .empty {

            padding: 35px 18px;

            text-align: center;

            color: #758197;
        }

        .timeframes {

            display: grid;

            grid-template-columns:
                repeat(3, 1fr);

            gap: 10px;
        }

        .tf-card {

            padding: 13px;

            border-radius: 13px;

            background:
                rgba(255,255,255,0.04);

            border:
                1px solid
                rgba(255,255,255,0.065);
        }

        .tf-head {

            display: flex;

            justify-content:
                space-between;
        }

        .tf-name {

            font-weight: 900;
        }

        .tf-dir {
            font-weight: 900;
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

            margin-top: 12px;

            color: #ff8a80;

            font-size: 12px;
        }

        .updated {

            color: #69768b;

            font-size: 10px;
        }

        @media (max-width: 1000px) {

            .overview {
                grid-template-columns:
                    repeat(2, 1fr);
            }

            .signals {
                grid-template-columns: 1fr;
            }

            .timeframes {
                grid-template-columns:
                    repeat(2, 1fr);
            }
        }

        @media (max-width: 620px) {

            .container {
                width:
                    calc(100% - 20px);
            }

            .overview,
            .timeframes {
                grid-template-columns: 1fr;
            }

            .signal-grid {
                grid-template-columns:
                    repeat(2, 1fr);
            }

            .toolbar {
                flex-direction: column;
            }

            select,
            input,
            button {
                width: 100%;
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


    <!-- TOOLBAR -->

    <div class="toolbar">

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


        <button onclick="scanSignals()">
            Scan Market
        </button>


        <button
            class="btn-secondary"
            onclick="analyzeSelected()"
        >
            Analyze BTC
        </button>

    </div>


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
            Click "Scan Market" to find 90%+ signals.
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
            1m → 4h
        </span>

    </div>


    <section
        id="selectedAnalysis"
        class="card"
        style="padding:18px;"
    >

        <div class="empty">
            Analyze a symbol to see its full analysis.
        </div>

    </section>


</main>


<script>


let allSignals = [];


function number(value) {

    const parsed =
        Number(value);

    if (
        Number.isNaN(parsed)
    ) {
        return 0;
    }

    return parsed;
}


function money(value) {

    if (
        value === null ||
        value === undefined
    ) {
        return "-";
    }

    const n =
        Number(value);

    if (
        Number.isNaN(n)
    ) {
        return "-";
    }

    return n.toLocaleString(
        undefined,
        {
            maximumFractionDigits: 6
        }
    );
}


function compact(value) {

    const n =
        number(value);

    if (
        n >= 1_000_000_000
    ) {
        return (
            n / 1_000_000_000
        ).toFixed(2) + "B";
    }

    if (
        n >= 1_000_000
    ) {
        return (
            n / 1_000_000
        ).toFixed(2) + "M";
    }

    if (
        n >= 1_000
    ) {
        return (
            n / 1_000
        ).toFixed(2) + "K";
    }

    return n.toFixed(2);
}


function directionClass(
    direction
) {

    return direction === "LONG"
        ? "long-text"
        : "short-text";
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
                    confidence >= threshold
                    &&
                    (
                        directionFilter === "ALL"
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

        container.innerHTML = `
            <div class="card empty">
                No matching ${threshold}%+
                signals right now.
            </div>
        `;

        return;
    }


    container.innerHTML =
        filtered.map(
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
                    direction === "LONG"
                    ? "long"
                    : "short";


                const level =
                    signal.confidence_level
                    ||
                    (
                        confidence >= 99
                        ? "EXTREME"
                        :
                        confidence >= 95
                        ? "VERY HIGH"
                        :
                        "HIGH"
                    );


                const reasons =
                    (
                        signal.reasons
                        || []
                    )
                    .slice(0, 4)
                    .map(
                        reason =>
                            `<span class="badge">${reason}</span>`
                    )
                    .join("");


                return `

                <div
                    class="card signal-card ${dClass}"
                >

                    <div class="signal-top">

                        <div>

                            <div class="symbol">
                                ${signal.symbol}
                            </div>

                            <div
                                class="
                                direction
                                ${direction === "LONG"
                                    ? "long-text"
                                    : "short-text"}
                                "
                            >
                                ${direction}
                            </div>

                        </div>


                        <div
                            class="
                            confidence
                            ${cClass}
                            "
                        >
                            ${confidence.toFixed(1)}%
                        </div>

                    </div>


                    <div class="signal-footer">

                        <span class="badge">
                            ${level}
                        </span>

                        <span class="badge">
                            ${signal.market}
                        </span>

                    </div>


                    <div class="signal-grid">

                        <div class="mini">

                            <div class="mini-label">
                                Price
                            </div>

                            <div class="mini-value">
                                ${money(signal.price)}
                            </div>

                        </div>


                        <div class="mini">

                            <div class="mini-label">
                                Entry
                            </div>

                            <div class="mini-value">
                                ${money(signal.entry)}
                            </div>

                        </div>


                        <div class="mini">

                            <div class="mini-label">
                                Stop Loss
                            </div>

                            <div class="mini-value">
                                ${money(signal.stop_loss)}
                            </div>

                        </div>


                        <div class="mini">

                            <div class="mini-label">
                                R:R
                            </div>

                            <div class="mini-value">
                                ${number(
                                    signal.risk_reward
                                ).toFixed(2)}R
                            </div>

                        </div>


                        <div class="mini">

                            <div class="mini-label">
                                TP1
                            </div>

                            <div class="mini-value">
                                ${money(signal.tp1)}
                            </div>

                        </div>


                        <div class="mini">

                            <div class="mini-label">
                                TP2
                            </div>

                            <div class="mini-value">
                                ${money(signal.tp2)}
                            </div>

                        </div>


                        <div class="mini">

                            <div class="mini-label">
                                TP3
                            </div>

                            <div class="mini-value">
                                ${money(signal.tp3)}
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
        ).join("");
}


async function scanSignals() {

    const market =
        document.getElementById(
            "market"
        ).value;

    const error =
        document.getElementById(
            "signalError"
        );

    error.textContent = "";


    const container =
        document.getElementById(
            "signals"
        );

    container.innerHTML = `
        <div class="card empty">
            Scanning market...
        </div>
    `;


    try {

        const response =
            await fetch(
                `/api/signals?market=${
                    encodeURIComponent(
                        market
                    )
                }&min_confidence=90&max_candidates=30`
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
                "Signal scan failed"
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
                x => number(
                    x.confidence
                ) >= 90
            ).length;


        document.getElementById(
            "count95"
        ).textContent =
            allSignals.filter(
                x => number(
                    x.confidence
                ) >= 95
            ).length;


        document.getElementById(
            "count99"
        ).textContent =
            allSignals.filter(
                x => number(
                    x.confidence
                ) >= 99
            ).length;


        document.getElementById(
            "lastUpdated"
        ).textContent =
            "Updated "
            + new Date().toLocaleTimeString();


        renderSignals();


    } catch (err) {

        error.textContent =
            err.message
            ||
            "Unable to scan signals.";

        container.innerHTML = `
            <div class="card empty">
                Signal scan failed.
            </div>
        `;
    }
}


async function analyzeSelected() {

    const container =
        document.getElementById(
            "selectedAnalysis"
        );

    container.innerHTML = `
        <div class="empty">
            Loading BTCUSDT analysis...
        </div>
    `;


    try {

        const market =
            document.getElementById(
                "market"
            ).value;


        const response =
            await fetch(
                `/api/analyze?symbol=BTCUSDT&market=${market}`
            );


        const result =
            await response.json();


        if (
            !response.ok
        ) {

            throw new Error(
                result.detail
                ||
                "Analysis failed"
            );
        }


        const data =
            result.data || result;


        const timeframes =
            data.timeframes || {};


        const timeframeOrder = [
            "1m",
            "2m",
            "3m",
            "5m",
            "15m",
            "30m",
            "45m",
            "1h",
            "4h"
        ];


        const cards =
            timeframeOrder
            .map(
                tf => {

                    const item =
                        timeframes[tf];


                    if (!item) {
                        return "";
                    }


                    const a =
                        item.analysis || {};

                    const s =
                        item.score || {};


                    const direction =
                        s.direction
                        ||
                        a.direction
                        ||
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
                                    s.confidence
                                    || 0
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
                        >
                            ${direction}
                        </div>


                        <div class="tf-row">
                            <span>
                                Price
                            </span>

                            <span>
                                ${money(a.price)}
                            </span>
                        </div>


                        <div class="tf-row">
                            <span>
                                EMA20
                            </span>

                            <span>
                                ${money(a.ema20)}
                            </span>
                        </div>


                        <div class="tf-row">
                            <span>
                                EMA50
                            </span>

                            <span>
                                ${money(a.ema50)}
                            </span>
                        </div>


                        <div class="tf-row">
                            <span>
                                Momentum
                            </span>

                            <span>
                                ${number(
                                    a.momentum
                                ).toFixed(4)}%
                            </span>
                        </div>


                        <div class="tf-row">
                            <span>
                                Volume
                            </span>

                            <span>
                                ${number(
                                    a.volume_ratio
                                ).toFixed(2)}x
                            </span>
                        </div>

                    </div>

                    `;
                }
            )
            .join("");


        container.innerHTML = `

            <div style="
                display:grid;
                grid-template-columns:
                    repeat(3, 1fr);
                gap:10px;
            ">

                ${cards}

            </div>

        `;


    } catch (err) {

        container.innerHTML = `
            <div class="empty">
                ${err.message}
            </div>
        `;
    }
}


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
        "market"
    )
    .addEventListener(
        "change",
        () => {
            allSignals = [];
            scanSignals();
        }
    );


// =========================================================
// AUTO SCAN
// =========================================================

window.addEventListener(
    "load",
    () => {

        scanSignals();

        setInterval(
            scanSignals,
            60_000
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
