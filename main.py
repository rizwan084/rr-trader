from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
import requests
import statistics
import math
import os
import time
from datetime import datetime, timezone

app = FastAPI(title="RR Trader Live Crypto Scanner", version="3.0")

BINANCE_URL = "https://fapi.binance.com"

session = requests.Session()
session.headers.update({
    "User-Agent": "RR-Trader/3.0"
})

# ============================================================
# SETTINGS
# ============================================================

SCAN_LIMIT = 100
MIN_CONFIDENCE = 85

# Telegram is optional.
# Add these in Render Environment Variables:
# TELEGRAM_BOT_TOKEN
# TELEGRAM_CHAT_ID

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Prevent repeated Telegram alerts for the same setup.
last_alerts = {}

# ============================================================
# BINANCE HELPERS
# ============================================================

def get_json(path, params=None):
    response = session.get(
        BINANCE_URL + path,
        params=params,
        timeout=15
    )
    response.raise_for_status()
    return response.json()


def candles(symbol, interval="15m", limit=150):
    data = get_json(
        "/fapi/v1/klines",
        {
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }
    )

    result = []

    for x in data:
        result.append({
            "time": int(x[0]),
            "open": float(x[1]),
            "high": float(x[2]),
            "low": float(x[3]),
            "close": float(x[4]),
            "volume": float(x[5]),
            "quote_volume": float(x[7]),
            "taker_buy_volume": float(x[9])
        })

    return result


def market_extra(symbol):
    result = {
        "open_interest": None,
        "funding_rate": None,
        "mark_price": None
    }

    try:
        oi = get_json(
            "/fapi/v1/openInterest",
            {"symbol": symbol}
        )
        result["open_interest"] = float(oi["openInterest"])
    except Exception:
        pass

    try:
        funding = get_json(
            "/fapi/v1/premiumIndex",
            {"symbol": symbol}
        )

        result["funding_rate"] = float(
            funding.get("lastFundingRate", 0)
        )

        result["mark_price"] = float(
            funding.get("markPrice", 0)
        )
    except Exception:
        pass

    return result


# ============================================================
# INDICATORS
# ============================================================

def ema(values, period):
    if len(values) < period:
        return None

    multiplier = 2 / (period + 1)

    current = sum(values[:period]) / period

    for price in values[period:]:
        current = (
            (price - current) * multiplier
        ) + current

    return current


def rsi(values, period=14):
    if len(values) < period + 1:
        return None

    gains = []
    losses = []

    for i in range(1, len(values)):
        change = values[i] - values[i - 1]

        if change >= 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (
            (avg_gain * (period - 1)) + gains[i]
        ) / period

        avg_loss = (
            (avg_loss * (period - 1)) + losses[i]
        ) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss

    return 100 - (100 / (1 + rs))


def macd(values):
    if len(values) < 35:
        return None, None, None

    ema12_values = []
    ema26_values = []

    # Build rolling EMA series.
    for i in range(26, len(values) + 1):
        ema12 = ema(values[:i], 12)
        ema26 = ema(values[:i], 26)

        if ema12 is not None and ema26 is not None:
            ema12_values.append(ema12)
            ema26_values.append(ema26)

    if not ema12_values or not ema26_values:
        return None, None, None

    macd_line = ema12_values[-1] - ema26_values[-1]

    macd_history = []

    for i in range(26, len(values) + 1):
        e12 = ema(values[:i], 12)
        e26 = ema(values[:i], 26)

        if e12 is not None and e26 is not None:
            macd_history.append(e12 - e26)

    if len(macd_history) < 9:
        return macd_line, None, None

    signal_line = ema(macd_history, 9)

    if signal_line is None:
        return macd_line, None, None

    histogram = macd_line - signal_line

    return macd_line, signal_line, histogram


def atr(data, period=14):
    if len(data) < period + 1:
        return None

    true_ranges = []

    for i in range(1, len(data)):
        high = data[i]["high"]
        low = data[i]["low"]
        previous_close = data[i - 1]["close"]

        tr = max(
            high - low,
            abs(high - previous_close),
            abs(low - previous_close)
        )

        true_ranges.append(tr)

    if len(true_ranges) < period:
        return None

    return sum(true_ranges[-period:]) / period


def round_price(price):
    if price >= 1000:
        return round(price, 2)
    if price >= 1:
        return round(price, 4)
    if price >= 0.01:
        return round(price, 6)
    return round(price, 8)


# ============================================================
# TIMEFRAME ANALYSIS
# ============================================================

def timeframe_analysis(symbol, interval):
    data = candles(symbol, interval, 150)

    if len(data) < 60:
        raise Exception(
            f"Not enough {interval} candle data"
        )

    closes = [x["close"] for x in data]
    volumes = [x["volume"] for x in data]

    price = closes[-1]

    ema20 = ema(closes, 20)
    ema50 = ema(closes, 50)

    current_rsi = rsi(closes, 14)

    macd_line, signal_line, histogram = macd(closes)

    avg_volume = statistics.mean(volumes[-20:])

    volume_ratio = (
        volumes[-1] / avg_volume
        if avg_volume > 0 else 0
    )

    bullish = 0
    bearish = 0
    reasons = []

    if ema20 is not None and ema50 is not None:

        if price > ema20:
            bullish += 2
            reasons.append(
                f"{interval}: price above EMA20"
            )
        else:
            bearish += 2
            reasons.append(
                f"{interval}: price below EMA20"
            )

        if ema20 > ema50:
            bullish += 3
            reasons.append(
                f"{interval}: EMA20 above EMA50"
            )
        else:
            bearish += 3
            reasons.append(
                f"{interval}: EMA20 below EMA50"
            )

    if current_rsi is not None:

        if 52 <= current_rsi <= 70:
            bullish += 2
            reasons.append(
                f"{interval}: bullish RSI"
            )

        elif 30 <= current_rsi < 48:
            bearish += 2
            reasons.append(
                f"{interval}: bearish RSI"
            )

        elif current_rsi > 70:
            bearish += 1
            reasons.append(
                f"{interval}: RSI overbought"
            )

        elif current_rsi < 30:
            bullish += 1
            reasons.append(
                f"{interval}: RSI oversold"
            )

    if macd_line is not None and signal_line is not None:

        if macd_line > signal_line:
            bullish += 2
            reasons.append(
                f"{interval}: MACD bullish"
            )
        else:
            bearish += 2
            reasons.append(
                f"{interval}: MACD bearish"
            )

    if volume_ratio >= 1.5:

        if closes[-1] > closes[-2]:
            bullish += 2
            reasons.append(
                f"{interval}: strong bullish volume"
            )
        else:
            bearish += 2
            reasons.append(
                f"{interval}: strong bearish volume"
            )

    total = bullish + bearish

    if total == 0:
        confidence = 0
    else:
        confidence = (
            max(bullish, bearish) / total
        ) * 100

    if bullish > bearish:
        direction = "LONG"
    elif bearish > bullish:
        direction = "SHORT"
    else:
        direction = "WAIT"

    return {
        "interval": interval,
        "price": price,
        "ema20": ema20,
        "ema50": ema50,
        "rsi": current_rsi,
        "macd": macd_line,
        "macd_signal": signal_line,
        "macd_histogram": histogram,
        "volume_ratio": volume_ratio,
        "bullish_score": bullish,
        "bearish_score": bearish,
        "confidence": confidence,
        "direction": direction,
        "reasons": reasons,
        "data": data
    }


# ============================================================
# SUPPORT / RESISTANCE
# ============================================================

def support_resistance(data):
    recent = data[-50:]

    lows = [x["low"] for x in recent]
    highs = [x["high"] for x in recent]

    support = min(lows)
    resistance = max(highs)

    return support, resistance


# ============================================================
# COMPLETE TRADE ANALYSIS
# ============================================================

def build_trade(symbol):

    intervals = ["5m", "15m", "1h", "4h"]

    analyses = {}

    for interval in intervals:
        analyses[interval] = timeframe_analysis(
            symbol,
            interval
        )

    five = analyses["5m"]
    fifteen = analyses["15m"]
    one_hour = analyses["1h"]
    four_hour = analyses["4h"]

    price = fifteen["price"]

    # --------------------------------------------------------
    # Multi-timeframe direction
    # --------------------------------------------------------

    long_votes = 0
    short_votes = 0

    for analysis in analyses.values():

        if analysis["direction"] == "LONG":
            long_votes += 1

        elif analysis["direction"] == "SHORT":
            short_votes += 1

    if long_votes >= 3 and long_votes > short_votes:
        direction = "LONG"

    elif short_votes >= 3 and short_votes > long_votes:
        direction = "SHORT"

    else:
        direction = "WAIT"

    # --------------------------------------------------------
    # Base confidence
    # --------------------------------------------------------

    weighted_confidence = (
        five["confidence"] * 0.10 +
        fifteen["confidence"] * 0.30 +
        one_hour["confidence"] * 0.30 +
        four_hour["confidence"] * 0.30
    )

    confidence = weighted_confidence

    reasons = []

    reasons.extend(
        fifteen["reasons"][-3:]
    )

    reasons.extend(
        one_hour["reasons"][-3:]
    )

    reasons.extend(
        four_hour["reasons"][-3:]
    )

    # --------------------------------------------------------
    # Higher timeframe agreement bonus
    # --------------------------------------------------------

    if direction == "LONG":

        if one_hour["direction"] == "LONG":
            confidence += 4

        if four_hour["direction"] == "LONG":
            confidence += 5

        if five["direction"] == "LONG":
            confidence += 2

    elif direction == "SHORT":

        if one_hour["direction"] == "SHORT":
            confidence += 4

        if four_hour["direction"] == "SHORT":
            confidence += 5

        if five["direction"] == "SHORT":
            confidence += 2

    # --------------------------------------------------------
    # Derivatives
    # --------------------------------------------------------

    extra = market_extra(symbol)

    funding = extra["funding_rate"]

    if funding is not None:

        if direction == "LONG" and funding > 0.001:

            confidence -= 4

            reasons.append(
                "positive funding indicates crowded longs"
            )

        elif direction == "SHORT" and funding < -0.001:

            confidence -= 4

            reasons.append(
                "negative funding indicates crowded shorts"
            )

        elif direction == "LONG" and funding < 0:

            confidence += 2

            reasons.append(
                "negative funding supports long setup"
            )

        elif direction == "SHORT" and funding > 0:

            confidence += 2

            reasons.append(
                "positive funding supports short setup"
            )

    # --------------------------------------------------------
    # Support / resistance
    # --------------------------------------------------------

    support, resistance = support_resistance(
        fifteen["data"]
    )

    current_atr = atr(
        fifteen["data"],
        14
    )

    if current_atr is None:
        current_atr = price * 0.01

    # --------------------------------------------------------
    # Entry / SL / TP
    # --------------------------------------------------------

    if direction == "LONG":

        entry = price

        stop_loss = min(
            support,
            entry - current_atr * 1.2
        )

        risk = entry - stop_loss

        if risk <= 0:
            risk = current_atr

            stop_loss = entry - risk

        tp1 = entry + risk * 1.5
        tp2 = entry + risk * 2.5
        tp3 = entry + risk * 3.5

    elif direction == "SHORT":

        entry = price

        stop_loss = max(
            resistance,
            entry + current_atr * 1.2
        )

        risk = stop_loss - entry

        if risk <= 0:
            risk = current_atr

            stop_loss = entry + risk

        tp1 = entry - risk * 1.5
        tp2 = entry - risk * 2.5
        tp3 = entry - risk * 3.5

    else:

        entry = price
        stop_loss = None
        tp1 = None
        tp2 = None
        tp3 = None
        risk = None

    # --------------------------------------------------------
    # R:R
    # --------------------------------------------------------

    if direction in ("LONG", "SHORT") and risk > 0:

        reward = (
            abs(tp2 - entry)
        )

        risk_reward = reward / risk

    else:
        risk_reward = 0

    # R:R quality bonus
    if risk_reward >= 3:
        confidence += 4
        reasons.append(
            "excellent risk/reward structure"
        )

    elif risk_reward >= 2:
        confidence += 2
        reasons.append(
            "good risk/reward structure"
        )

    confidence = max(
        0,
        min(
            round(confidence, 2),
            100
        )
    )

    # --------------------------------------------------------
    # Final signal
    # --------------------------------------------------------

    if direction == "WAIT":
        signal = "WAIT"

    elif confidence >= 85:
        signal = direction

    else:
        signal = "WATCH"

    return {
        "symbol": symbol,
        "signal": signal,
        "direction": direction,
        "confidence": confidence,
        "price": round_price(price),

        "entry": (
            round_price(entry)
            if entry is not None else None
        ),

        "stop_loss": (
            round_price(stop_loss)
            if stop_loss is not None else None
        ),

        "tp1": (
            round_price(tp1)
            if tp1 is not None else None
        ),

        "tp2": (
            round_price(tp2)
            if tp2 is not None else None
        ),

        "tp3": (
            round_price(tp3)
            if tp3 is not None else None
        ),

        "risk_reward": round(
            risk_reward,
            2
        ),

        "support": round_price(support),
        "resistance": round_price(resistance),

        "atr": round_price(current_atr),

        "funding_rate": funding,
        "open_interest": extra["open_interest"],
        "mark_price": extra["mark_price"],

        "timeframes": {
            "5m": five["direction"],
            "15m": fifteen["direction"],
            "1h": one_hour["direction"],
            "4h": four_hour["direction"]
        },

        "indicators": {
            "5m": {
                "rsi": five["rsi"],
                "volume_ratio": five["volume_ratio"]
            },
            "15m": {
                "rsi": fifteen["rsi"],
                "volume_ratio": fifteen["volume_ratio"],
                "ema20": fifteen["ema20"],
                "ema50": fifteen["ema50"]
            },
            "1h": {
                "rsi": one_hour["rsi"],
                "volume_ratio": one_hour["volume_ratio"],
                "ema20": one_hour["ema20"],
                "ema50": one_hour["ema50"]
            },
            "4h": {
                "rsi": four_hour["rsi"],
                "volume_ratio": four_hour["volume_ratio"],
                "ema20": four_hour["ema20"],
                "ema50": four_hour["ema50"]
            }
        },

        "reasons": list(dict.fromkeys(reasons)),

        "generated_at": datetime.now(
            timezone.utc
        ).isoformat()
    }


# ============================================================
# MARKET CANDIDATES
# ============================================================

def get_candidates():

    data = get_json(
        "/fapi/v1/ticker/24hr"
    )

    candidates = []

    for item in data:

        symbol = item.get("symbol", "")

        if not symbol.endswith("USDT"):
            continue

        # Avoid some non-standard symbols.
        if "_" in symbol:
            continue

        try:

            price = float(
                item["lastPrice"]
            )

            change = float(
                item["priceChangePercent"]
            )

            volume = float(
                item["quoteVolume"]
            )

            high = float(
                item["highPrice"]
            )

            low = float(
                item["lowPrice"]
            )

            if volume <= 0 or price <= 0:
                continue

            movement_score = min(
                abs(change),
                30
            )

            volume_score = min(
                volume / 100000000,
                10
            )

            activity_score = (
                movement_score * 0.35 +
                volume_score * 0.65
            )

            candidates.append({
                "symbol": symbol,
                "price": price,
                "change_24h": change,
                "volume_24h": volume,
                "high_24h": high,
                "low_24h": low,
                "activity_score": round(
                    activity_score,
                    2
                )
            })

        except (
            ValueError,
            TypeError,
            KeyError
        ):
            continue

    candidates.sort(
        key=lambda x: x["activity_score"],
        reverse=True
    )

    return candidates[:SCAN_LIMIT]


# ============================================================
# TELEGRAM
# ============================================================

def telegram_message(trade):

    direction = trade["direction"]

    if direction == "LONG":
        title = "RR TRADER HIGH-CONFIDENCE LONG"
    else:
        title = "RR TRADER HIGH-CONFIDENCE SHORT"

    message = (
        f"{title}\n\n"
        f"${trade['symbol']}\n"
        f"Confidence: {trade['confidence']}%\n"
        f"Entry: {trade['entry']}\n"
        f"SL: {trade['stop_loss']}\n"
        f"TP1: {trade['tp1']}\n"
        f"TP2: {trade['tp2']}\n"
        f"TP3: {trade['tp3']}\n"
        f"Risk/Reward: {trade['risk_reward']}R\n\n"
        f"5m: {trade['timeframes']['5m']}\n"
        f"15m: {trade['timeframes']['15m']}\n"
        f"1h: {trade['timeframes']['1h']}\n"
        f"4h: {trade['timeframes']['4h']}\n\n"
        f"Generated: {trade['generated_at']}"
    )

    return message


def send_telegram(text):

    if not TELEGRAM_BOT_TOKEN:
        return {
            "sent": False,
            "reason": "TELEGRAM_BOT_TOKEN not configured"
        }

    if not TELEGRAM_CHAT_ID:
        return {
            "sent": False,
            "reason": "TELEGRAM_CHAT_ID not configured"
        }

    try:

        response = requests.post(
            f"https://api.telegram.org/bot"
            f"{TELEGRAM_BOT_TOKEN}/sendMessage",

            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text
            },

            timeout=15
        )

        response.raise_for_status()

        return {
            "sent": True
        }

    except Exception as error:

        return {
            "sent": False,
            "error": str(error)
        }


def notify_if_needed(trade):

    if trade["signal"] not in (
        "LONG",
        "SHORT"
    ):
        return {
            "sent": False,
            "reason": "No high-confidence signal"
        }

    if trade["confidence"] < MIN_CONFIDENCE:
        return {
            "sent": False,
            "reason": "Confidence below threshold"
        }

    symbol = trade["symbol"]

    # Alert key changes if direction or confidence changes.
    alert_key = (
        trade["direction"],
        int(trade["confidence"] // 2)
    )

    previous = last_alerts.get(symbol)

    if previous == alert_key:
        return {
            "sent": False,
            "reason": "Duplicate alert blocked"
        }

    result = send_telegram(
        telegram_message(trade)
    )

    if result.get("sent"):
        last_alerts[symbol] = alert_key

    return result


# ============================================================
# API ROUTES
# ============================================================

@app.get("/")
def home():

    return {
        "app": "RR Trader Live Scanner",
        "status": "online",
        "version": "3.0",
        "message": "RR Trader v3 backend is working",
        "minimum_signal_confidence": MIN_CONFIDENCE
    }


@app.get("/market/scan")
def market_scan():

    try:

        candidates = get_candidates()

        return {
            "success": True,
            "total_coins": len(candidates),
            "top_candidates": candidates
        }

    except Exception as error:

        return {
            "success": False,
            "error": str(error)
        }


@app.get("/signal/{symbol}")
def signal(symbol: str):

    symbol = symbol.upper()

    try:

        trade = build_trade(symbol)

        return {
            "success": True,
            **trade
        }

    except Exception as error:

        return {
            "success": False,
            "symbol": symbol,
            "error": str(error)
        }


@app.get("/analysis/{symbol}")
def analysis(symbol: str):

    symbol = symbol.upper()

    try:

        trade = build_trade(symbol)

        return {
            "success": True,
            "symbol": symbol,
            "analysis": trade
        }

    except Exception as error:

        return {
            "success": False,
            "symbol": symbol,
            "error": str(error)
        }


@app.get("/scan/signals")
def scan_signals(
    limit: int = Query(
        default=10,
        ge=1,
        le=20
    ),
    notify: bool = False
):

    try:

        candidates = get_candidates()

        results = []

        for candidate in candidates:

            symbol = candidate["symbol"]

            try:

                trade = build_trade(symbol)

                if trade["signal"] in (
                    "LONG",
                    "SHORT"
                ) and trade["confidence"] >= MIN_CONFIDENCE:

                    results.append(trade)

                    if notify:
                        notify_if_needed(trade)

            except Exception:
                continue

        results.sort(
            key=lambda x: (
                x["confidence"],
                x["risk_reward"]
            ),
            reverse=True
        )

        return {
            "success": True,
            "minimum_confidence": MIN_CONFIDENCE,
            "signals_found": len(results),
            "signals": results[:limit],
            "generated_at": datetime.now(
                timezone.utc
            ).isoformat()
        }

    except Exception as error:

        return {
            "success": False,
            "error": str(error)
        }


@app.get("/notify/{symbol}")
def notify_symbol(symbol: str):

    symbol = symbol.upper()

    try:

        trade = build_trade(symbol)

        result = notify_if_needed(
            trade
        )

        return {
            "success": True,
            "trade": trade,
            "notification": result
        }

    except Exception as error:

        return {
            "success": False,
            "symbol": symbol,
            "error": str(error)
        }


# ============================================================
# LIVE DASHBOARD
# ============================================================

DASHBOARD = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RR Trader Live Scanner</title>

<script src="https://cdn.jsdelivr.net/npm/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.min.js"></script>

<style>

body {
    margin: 0;
    font-family: Arial, sans-serif;
    background: #07111f;
    color: white;
}

.header {
    padding: 18px;
    background: #0b1728;
    border-bottom: 1px solid #20334d;
}

.title {
    font-size: 24px;
    font-weight: bold;
}

.status {
    color: #35e69a;
    margin-top: 5px;
}

.controls {
    padding: 15px;
    display: flex;
    gap: 8px;
}

input, button {
    padding: 12px;
    border-radius: 8px;
    border: 1px solid #31445f;
    background: #0e1c30;
    color: white;
}

button {
    cursor: pointer;
}

.container {
    padding: 15px;
}

.card {
    background: #0d1b2e;
    border: 1px solid #20344f;
    border-radius: 12px;
    padding: 15px;
    margin-bottom: 12px;
}

.long {
    border-left: 5px solid #27e39b;
}

.short {
    border-left: 5px solid #ff5d6c;
}

.symbol {
    font-size: 20px;
    font-weight: bold;
}

.confidence {
    font-size: 25px;
    font-weight: bold;
}

.grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
    margin-top: 10px;
}

.box {
    background: #081525;
    padding: 9px;
    border-radius: 8px;
}

.chart {
    width: 100%;
    height: 420px;
    margin-top: 15px;
}

.small {
    color: #9eb0c8;
    font-size: 13px;
}

</style>
</head>

<body>

<div class="header">
    <div class="title">RR Trader Live Scanner</div>
    <div class="status">● LIVE BINANCE FUTURES</div>
</div>

<div class="controls">
    <input id="symbol" value="BTCUSDT">
    <button onclick="loadCoin()">Analyze</button>
    <button onclick="loadSignals()">Scan</button>
</div>

<div class="container">

<div id="results"></div>

<div class="card">
    <div id="chart" class="chart"></div>
</div>

</div>

<script>

let chart;
let candleSeries;

function createChart() {

    const container =
        document.getElementById("chart");

    container.innerHTML = "";

    chart =
        LightweightCharts.createChart(
            container,
            {
                layout: {
                    background: {
                        color: "#07111f"
                    },
                    textColor: "#d8e2ef"
                },

                grid: {
                    vertLines: {
                        color: "#102238"
                    },
                    horzLines: {
                        color: "#102238"
                    }
                },

                width: container.clientWidth,
                height: 420
            }
        );

    candleSeries =
        chart.addCandlestickSeries();

}

async function loadCoin() {

    const symbol =
        document.getElementById(
            "symbol"
        ).value.toUpperCase();

    const response =
        await fetch(
            "/signal/" + symbol
        );

    const data =
        await response.json();

    if (!data.success) {

        document.getElementById(
            "results"
        ).innerHTML =
            "<div class='card'>" +
            data.error +
            "</div>";

        return;
    }

    renderTrade(data);

    await loadChart(symbol);
}


function renderTrade(data) {

    const cls =
        data.direction === "LONG"
        ? "long"
        : "short";

    document.getElementById(
        "results"
    ).innerHTML = `

        <div class="card ${cls}">

            <div class="symbol">
                $${data.symbol}
            </div>

            <div class="confidence">
                ${data.confidence}%
            </div>

            <div>
                ${data.signal}
                ${data.direction}
            </div>

            <div class="grid">

                <div class="box">
                    Entry<br>
                    ${data.entry}
                </div>

                <div class="box">
                    Stop Loss<br>
                    ${data.stop_loss}
                </div>

                <div class="box">
                    TP1<br>
                    ${data.tp1}
                </div>

                <div class="box">
                    TP2<br>
                    ${data.tp2}
                </div>

                <div class="box">
                    TP3<br>
                    ${data.tp3}
                </div>

                <div class="box">
                    R:R<br>
                    ${data.risk_reward}R
                </div>

            </div>

            <p class="small">
                5m: ${data.timeframes["5m"]}
                |
                15m: ${data.timeframes["15m"]}
                |
                1h: ${data.timeframes["1h"]}
                |
                4h: ${data.timeframes["4h"]}
            </p>

        </div>
    `;
}


async function loadSignals() {

    const response =
        await fetch(
            "/scan/signals?limit=10"
        );

    const data =
        await response.json();

    if (!data.success) {
        return;
    }

    let html = "";

    data.signals.forEach(
        trade => {

            const cls =
                trade.direction === "LONG"
                ? "long"
                : "short";

            html += `

            <div class="card ${cls}">

                <div class="symbol">
                    $${trade.symbol}
                </div>

                <div class="confidence">
                    ${trade.confidence}%
                </div>

                <div>
                    ${trade.direction}
                    |
                    R:R ${trade.risk_reward}R
                </div>

                <div class="grid">

                    <div class="box">
                        Entry<br>
                        ${trade.entry}
                    </div>

                    <div class="box">
                        SL<br>
                        ${trade.stop_loss}
                    </div>

                    <div class="box">
                        TP1<br>
                        ${trade.tp1}
                    </div>

                    <div class="box">
                        TP2<br>
                        ${trade.tp2}
                    </div>

                </div>

            </div>
            `;
        }
    );

    document.getElementById(
        "results"
    ).innerHTML = html;
}


async function loadChart(symbol) {

    createChart();

    try {

        const response =
            await fetch(
                "/chart-data/" + symbol
            );

        const data =
            await response.json();

        if (!data.success) {
            return;
        }

        candleSeries.setData(
            data.candles
        );

        chart.timeScale().fitContent();

    } catch (error) {

        console.log(error);

    }
}


createChart();

loadCoin();

setInterval(
    () => {

        loadCoin();

    },
    30000
);

</script>

</body>
</html>
"""


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return DASHBOARD


# ============================================================
# CHART DATA
# ============================================================

@app.get("/chart-data/{symbol}")
def chart_data(symbol: str):

    symbol = symbol.upper()

    try:

        data = candles(
            symbol,
            "15m",
            150
        )

        formatted = []

        for candle in data:

            formatted.append({
                "time": int(
                    candle["time"] / 1000
                ),
                "open": candle["open"],
                "high": candle["high"],
                "low": candle["low"],
                "close": candle["close"]
            })

        return {
            "success": True,
            "symbol": symbol,
            "interval": "15m",
            "candles": formatted
        }

    except Exception as error:

        return {
            "success": False,
            "error": str(error)
        }
