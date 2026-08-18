from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.app.api.routes import router as api_router


app = FastAPI(
    title="RR Trader Live Scanner",
    description="AI-powered Binance Spot and Futures market scanner",
    version="2.0.0",
)


# =========================================================
# DASHBOARD HTML
# =========================================================

DASHBOARD_HTML = """
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
            font-family:
                Inter,
                system-ui,
                -apple-system,
                BlinkMacSystemFont,
                "Segoe UI",
                sans-serif;

            background:
                radial-gradient(
                    circle at top left,
                    #16213d 0%,
                    #080b13 42%,
                    #05070b 100%
                );

            color: #f5f7fb;
            min-height: 100vh;
        }

        .topbar {
            position: sticky;
            top: 0;
            z-index: 20;

            display: flex;
            justify-content: space-between;
            align-items: center;

            padding: 18px 26px;

            background:
                rgba(7, 10, 18, 0.88);

            backdrop-filter: blur(18px);

            border-bottom:
                1px solid rgba(255,255,255,0.08);
        }

        .brand {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .logo {
            width: 42px;
            height: 42px;

            border-radius: 12px;

            display: grid;
            place-items: center;

            font-weight: 900;
            font-size: 17px;

            background:
                linear-gradient(
                    135deg,
                    #00e5ff,
                    #7c4dff
                );

            color: #061018;

            box-shadow:
                0 0 25px
                rgba(0,229,255,0.25);
        }

        .brand h1 {
            margin: 0;
            font-size: 19px;
        }

        .brand span {
            color: #8d98aa;
            font-size: 12px;
        }

        .status {
            display: flex;
            align-items: center;
            gap: 8px;

            color: #9eaabd;
            font-size: 13px;
        }

        .dot {
            width: 9px;
            height: 9px;
            border-radius: 50%;

            background: #00e676;

            box-shadow:
                0 0 12px
                rgba(0,230,118,0.8);
        }

        .container {
            max-width: 1450px;
            margin: 0 auto;
            padding: 28px 22px 60px;
        }

        .toolbar {
            display: flex;
            flex-wrap: wrap;
            gap: 12px;

            margin-bottom: 22px;
        }

        select,
        input,
        button {
            border: 1px solid
                rgba(255,255,255,0.10);

            background: rgba(255,255,255,0.05);

            color: #fff;

            border-radius: 11px;

            padding: 11px 14px;

            font-size: 14px;

            outline: none;
        }

        select,
        input {
            min-width: 150px;
        }

        button {
            cursor: pointer;

            background:
                linear-gradient(
                    135deg,
                    #00c6ff,
                    #635bff
                );

            border: none;

            font-weight: 700;

            box-shadow:
                0 8px 25px
                rgba(70,80,255,0.20);
        }

        button:hover {
            transform: translateY(-1px);
        }

        .hero {
            display: grid;

            grid-template-columns:
                1.4fr
                1fr
                1fr;

            gap: 16px;

            margin-bottom: 18px;
        }

        .card {
            background:
                linear-gradient(
                    180deg,
                    rgba(255,255,255,0.07),
                    rgba(255,255,255,0.035)
                );

            border:
                1px solid
                rgba(255,255,255,0.08);

            border-radius: 18px;

            padding: 20px;

            backdrop-filter: blur(15px);

            box-shadow:
                0 15px 40px
                rgba(0,0,0,0.22);
        }

        .hero-main {
            min-height: 180px;
        }

        .label {
            color: #8490a3;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }

        .price {
            font-size: 34px;
            font-weight: 800;
            margin: 8px 0;
        }

        .direction {
            font-size: 19px;
            font-weight: 800;
        }

        .long {
            color: #00e676;
        }

        .short {
            color: #ff5252;
        }

        .neutral {
            color: #9eaabd;
        }

        .confidence {
            font-size: 30px;
            font-weight: 800;
            margin-top: 6px;
        }

        .meter {
            width: 100%;
            height: 8px;

            background:
                rgba(255,255,255,0.08);

            border-radius: 99px;

            overflow: hidden;

            margin-top: 12px;
        }

        .meter-fill {
            height: 100%;
            width: 0%;

            border-radius: 99px;

            background:
                linear-gradient(
                    90deg,
                    #00e676,
                    #00c6ff
                );
        }

        .stats {
            display: grid;

            grid-template-columns:
                repeat(4, 1fr);

            gap: 14px;

            margin-bottom: 18px;
        }

        .stat-value {
            margin-top: 8px;
            font-size: 23px;
            font-weight: 800;
        }

        .section-title {
            margin: 28px 0 12px;

            font-size: 16px;
            font-weight: 800;
        }

        .timeframes {
            display: grid;

            grid-template-columns:
                repeat(3, 1fr);

            gap: 12px;
        }

        .tf {
            padding: 15px;

            border-radius: 15px;

            background:
                rgba(255,255,255,0.045);

            border:
                1px solid
                rgba(255,255,255,0.07);
        }

        .tf-head {
            display: flex;
            justify-content: space-between;

            margin-bottom: 10px;
        }

        .tf-name {
            font-weight: 800;
        }

        .tf-confidence {
            font-weight: 800;
        }

        .tf-row {
            display: flex;
            justify-content: space-between;

            color: #8f9aad;

            font-size: 12px;

            margin-top: 5px;
        }

        .levels {
            display: grid;

            grid-template-columns:
                repeat(5, 1fr);

            gap: 12px;
        }

        .level-value {
            margin-top: 8px;
            font-size: 18px;
            font-weight: 800;
        }

        .reasons {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }

        .reason {
            padding: 8px 11px;

            border-radius: 999px;

            background:
                rgba(255,255,255,0.06);

            color: #c4ccd9;

            font-size: 12px;
        }

        .footer {
            margin-top: 30px;

            color: #687388;

            text-align: center;

            font-size: 12px;
        }

        .error {
            color: #ff8a80;
            margin-top: 12px;
        }

        @media (max-width: 950px) {

            .hero {
                grid-template-columns: 1fr;
            }

            .stats {
                grid-template-columns:
                    repeat(2, 1fr);
            }

            .timeframes {
                grid-template-columns:
                    repeat(2, 1fr);
            }

            .levels {
                grid-template-columns:
                    repeat(2, 1fr);
            }
        }

        @media (max-width: 600px) {

            .topbar {
                padding: 15px;
            }

            .container {
                padding: 18px 14px 40px;
            }

            .stats,
            .timeframes,
            .levels {
                grid-template-columns: 1fr;
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
            <h1>RR Trader</h1>
            <span>Live Crypto Intelligence Dashboard</span>
        </div>

    </div>

    <div class="status">
        <span class="dot"></span>
        Backend Online
    </div>

</header>


<main class="container">

    <div class="toolbar">

        <select id="market">
            <option value="futures">
                Binance Futures
            </option>

            <option value="spot">
                Binance Spot
            </option>
        </select>

        <input
            id="symbol"
            value="BTCUSDT"
            placeholder="BTCUSDT"
        >

        <button onclick="analyze()">
            Analyze
        </button>

        <button onclick="scanMarket()">
            Scan Market
        </button>

    </div>


    <section class="hero">

        <div class="card hero-main">

            <div class="label">
                Symbol
            </div>

            <div
                id="symbolView"
                class="price"
            >
                BTCUSDT
            </div>

            <div
                id="direction"
                class="direction neutral"
            >
                WAIT
            </div>

            <div
                id="reasons"
                class="reasons"
            ></div>

        </div>


        <div class="card">

            <div class="label">
                Confidence
            </div>

            <div
                id="confidence"
                class="confidence"
            >
                0%
            </div>

            <div class="meter">
                <div
                    id="meterFill"
                    class="meter-fill"
                ></div>
            </div>

            <div
                id="publishable"
                class="label"
                style="margin-top:14px;"
            >
                Waiting
            </div>

        </div>


        <div class="card">

            <div class="label">
                Current Price
            </div>

            <div
                id="price"
                class="price"
            >
                -
            </div>

            <div
                id="change24"
                class="label"
            >
                24H: -
            </div>

        </div>

    </section>


    <section class="stats">

        <div class="card">
            <div class="label">
                24H Volume
            </div>

            <div
                id="volume24"
                class="stat-value"
            >
                -
            </div>
        </div>


        <div class="card">
            <div class="label">
                Entry
            </div>

            <div
                id="entry"
                class="stat-value"
            >
                -
            </div>
        </div>


        <div class="card">
            <div class="label">
                Risk / Reward
            </div>

            <div
                id="rr"
                class="stat-value"
            >
                -
            </div>
        </div>


        <div class="card">
            <div class="label">
                Liquidity
            </div>

            <div
                id="liquidity"
                class="stat-value"
            >
                -
            </div>
        </div>

    </section>


    <div class="section-title">
        Multi-Timeframe Analysis
    </div>

    <section
        id="timeframes"
        class="timeframes"
    >
    </section>


    <div class="section-title">
        Trade Levels
    </div>

    <section class="levels">

        <div class="card">
            <div class="label">
                Entry
            </div>

            <div
                id="entry2"
                class="level-value"
            >
                -
            </div>
        </div>

        <div class="card">
            <div class="label">
                Stop Loss
            </div>

            <div
                id="sl"
                class="level-value"
            >
                -
            </div>
        </div>

        <div class="card">
            <div class="label">
                TP1
            </div>

            <div
                id="tp1"
                class="level-value"
            >
                -
            </div>
        </div>

        <div class="card">
            <div class="label">
                TP2
            </div>

            <div
                id="tp2"
                class="level-value"
            >
                -
            </div>
        </div>

        <div class="card">
            <div class="label">
                TP3
            </div>

            <div
                id="tp3"
                class="level-value"
            >
                -
            </div>
        </div>

    </section>


    <div
        id="error"
        class="error"
    ></div>


    <div class="footer">
        RR Trader Live Scanner
    </div>

</main>


<script>

function money(value) {

    if (
        value === null ||
        value === undefined ||
        value === ""
    ) {
        return "-";
    }

    const number = Number(value);

    if (Number.isNaN(number)) {
        return "-";
    }

    return number.toLocaleString(
        undefined,
        {
            maximumFractionDigits: 4
        }
    );
}


function volume(value) {

    if (!value) {
        return "-";
    }

    const number = Number(value);

    if (number >= 1_000_000_000) {
        return (
            (number / 1_000_000_000).toFixed(2)
            + "B"
        );
    }

    if (number >= 1_000_000) {
        return (
            (number / 1_000_000).toFixed(2)
            + "M"
        );
    }

    if (number >= 1_000) {
        return (
            (number / 1_000).toFixed(2)
            + "K"
        );
    }

    return number.toFixed(2);
}


function directionClass(direction) {

    if (direction === "LONG") {
        return "long";
    }

    if (direction === "SHORT") {
        return "short";
    }

    return "neutral";
}


function renderTimeframes(
    timeframes
) {

    const container =
        document.getElementById(
            "timeframes"
        );

    container.innerHTML = "";

    const order = [
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

    for (
        const timeframe
        of order
    ) {

        const item =
            timeframes?.[timeframe];

        if (!item) {
            continue;
        }

        const analysis =
            item.analysis || {};

        const score =
            item.score || {};

        const direction =
            score.direction ||
            analysis.direction ||
            "NEUTRAL";

        const confidence =
            Number(
                score.confidence || 0
            );

        const volumeRatio =
            Number(
                analysis.volume_ratio || 0
            );

        const momentum =
            Number(
                analysis.momentum || 0
            );

        const card =
            document.createElement(
                "div"
            );

        card.className = "tf";

        card.innerHTML = `
            <div class="tf-head">
                <div class="tf-name">
                    ${timeframe}
                </div>

                <div class="${directionClass(direction)} tf-confidence">
                    ${confidence.toFixed(0)}%
                </div>
            </div>

            <div class="${directionClass(direction)} direction">
                ${direction}
            </div>

            <div class="tf-row">
                <span>Price</span>
                <span>${money(analysis.price)}</span>
            </div>

            <div class="tf-row">
                <span>EMA20</span>
                <span>${money(analysis.ema20)}</span>
            </div>

            <div class="tf-row">
                <span>EMA50</span>
                <span>${money(analysis.ema50)}</span>
            </div>

            <div class="tf-row">
                <span>Momentum</span>
                <span>${momentum.toFixed(4)}%</span>
            </div>

            <div class="tf-row">
                <span>Volume Ratio</span>
                <span>${volumeRatio.toFixed(2)}x</span>
            </div>
        `;

        container.appendChild(
            card
        );
    }
}


function renderData(
    result
) {

    const data =
        result?.data || result;

    const direction =
        data.direction || "NEUTRAL";

    const confidence =
        Number(
            data.confidence || 0
        );

    document.getElementById(
        "symbolView"
    ).textContent =
        data.symbol || "-";

    const directionElement =
        document.getElementById(
            "direction"
        );

    directionElement.textContent =
        direction;

    directionElement.className =
        "direction "
        + directionClass(
            direction
        );

    document.getElementById(
        "confidence"
    ).textContent =
        confidence.toFixed(1)
        + "%";

    document.getElementById(
        "meterFill"
    ).style.width =
        Math.max(
            0,
            Math.min(
                confidence,
                100
            )
        ) + "%";

    document.getElementById(
        "price"
    ).textContent =
        money(data.price);

    document.getElementById(
        "change24"
    ).textContent =
        "24H: "
        + Number(
            data.price_change_24h || 0
        ).toFixed(2)
        + "%";

    document.getElementById(
        "volume24"
    ).textContent =
        volume(
            data.quote_volume_24h
        );

    document.getElementById(
        "entry"
    ).textContent =
        money(data.entry);

    document.getElementById(
        "entry2"
    ).textContent =
        money(data.entry);

    document.getElementById(
        "sl"
    ).textContent =
        money(data.stop_loss);

    document.getElementById(
        "tp1"
    ).textContent =
        money(data.tp1);

    document.getElementById(
        "tp2"
    ).textContent =
        money(data.tp2);

    document.getElementById(
        "tp3"
    ).textContent =
        money(data.tp3);

    document.getElementById(
        "rr"
    ).textContent =
        data.risk_reward
        !== undefined
        ? Number(
            data.risk_reward
        ).toFixed(2) + "R"
        : "-";

    document.getElementById(
        "liquidity"
    ).textContent =
        data.market_24h?.liquidity
        || "-";

    const publishable =
        document.getElementById(
            "publishable"
        );

    publishable.textContent =
        data.publishable
        ? "HIGH CONFIDENCE SIGNAL"
        : "Not publishable";

    const reasonContainer =
        document.getElementById(
            "reasons"
        );

    reasonContainer.innerHTML = "";

    const reasons =
        data.reasons || [];

    for (
        const reason
        of reasons
    ) {

        const badge =
            document.createElement(
                "div"
            );

        badge.className =
            "reason";

        badge.textContent =
            reason;

        reasonContainer.appendChild(
            badge
        );
    }

    renderTimeframes(
        data.timeframes
    );
}


async function analyze() {

    const symbol =
        document.getElementById(
            "symbol"
        ).value.trim();

    const market =
        document.getElementById(
            "market"
        ).value;

    const error =
        document.getElementById(
            "error"
        );

    error.textContent = "";

    if (!symbol) {
        error.textContent =
            "Enter a symbol.";
        return;
    }

    try {

        const response =
            await fetch(
                `/api/analyze?symbol=${
                    encodeURIComponent(symbol)
                }&market=${
                    encodeURIComponent(market)
                }`
            );

        const result =
            await response.json();

        if (!response.ok) {
            throw new Error(
                result.detail
                || "Analysis failed"
            );
        }

        renderData(
            result
        );

    } catch (err) {

        error.textContent =
            err.message
            || "Request failed.";
    }
}


async function scanMarket() {

    const market =
        document.getElementById(
            "market"
        ).value;

    const error =
        document.getElementById(
            "error"
        );

    error.textContent = "";

    try {

        const response =
            await fetch(
                `/api/scan?market=${
                    encodeURIComponent(
                        market
                    )
                }`
            );

        const result =
            await response.json();

        if (!response.ok) {
            throw new Error(
                result.detail
                || "Market scan failed"
            );
        }

        /*
            For general scan the backend returns:
            data.top_signals
            data.candidates

            Show the first top signal on the dashboard.
        */

        const topSignals =
            result?.data?.top_signals
            || [];

        if (
            topSignals.length > 0
        ) {

            renderData(
                topSignals[0]
            );

        } else {

            error.textContent =
                "No publishable signals found right now.";
        }

    } catch (err) {

        error.textContent =
            err.message
            || "Market scan failed.";
    }
}


// Load BTC immediately.
window.addEventListener(
    "load",
    () => {
        analyze();
    }
);

</script>

</body>
</html>
"""


# =========================================================
# ROOT
# =========================================================

@app.get("/")
async def root():
    return {
        "app": "RR Trader Live Scanner",
        "status": "online",
        "version": "2.0.0",
        "markets": [
            "futures",
            "spot",
        ],
        "dashboard": "/dashboard",
        "message": "RR Trader backend is working",
    }


# =========================================================
# DASHBOARD
# =========================================================

@app.get(
    "/dashboard",
    response_class=HTMLResponse,
)
async def dashboard():
    return HTMLResponse(
        content=DASHBOARD_HTML
    )


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
