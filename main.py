from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
import requests
import statistics
import time
import os
import threading
from datetime import datetime, timezone


# ============================================================
# RR TRADER LIVE SCANNER
# Version 5.0
# ============================================================

app = FastAPI(
    title="RR Trader Live Scanner",
    version="5.0"
)

BINANCE_FUTURES = "https://fapi.binance.com"
BINANCE_SPOT = "https://api.binance.com"

session = requests.Session()
session.headers.update({
    "User-Agent": "RR-Trader-Live-Scanner/5.0"
})


# ============================================================
# SETTINGS
# ============================================================

MIN_CONFIDENCE = 85

AUTO_SCAN_INTERVAL = 60

AUTO_SCAN_COINS = 6

CACHE_SECONDS = 20

TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN"
)

TELEGRAM_CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID"
)


# ============================================================
# CACHE
# ============================================================

cache = {}

last_alerts = {}

scanner_state = {
    "running": True,
    "last_scan": None,
    "signals": [],
    "error": None
}


# ============================================================
# SAFE HTTP REQUEST
# ============================================================

def request_json(
    base_url,
    endpoint,
    params=None,
    retries=3
):

    cache_key = (
        base_url,
        endpoint,
        tuple(
            sorted(
                (params or {}).items()
            )
        )
    )

    now = time.time()

    if cache_key in cache:

        saved_time, saved_data = cache[
            cache_key
        ]

        if now - saved_time < CACHE_SECONDS:
            return saved_data

    last_error = None

    for attempt in range(retries):

        try:

            response = session.get(
                base_url + endpoint,
                params=params,
                timeout=15
            )

            # Binance temporary rate-limit
            if response.status_code in (
                418,
                429
            ):

                wait_time = min(
                    10,
                    2 ** attempt
                )

                time.sleep(wait_time)

                last_error = Exception(
                    f"Binance rate limit: "
                    f"{response.status_code}"
                )

                continue

            response.raise_for_status()

            data = response.json()

            cache[cache_key] = (
                now,
                data
            )

            return data

        except Exception as error:

            last_error = error

            if attempt < retries - 1:

                time.sleep(
                    1.5 * (attempt + 1)
                )

    raise last_error


# ============================================================
# SYMBOL HELPERS
# ============================================================

def clean_coin(value):

    value = (
        value
        .strip()
        .upper()
        .replace("/", "")
        .replace("-", "")
        .replace(" ", "")
    )

    if value.endswith("USDT"):
        value = value[:-4]

    return value


def futures_exchange_info():

    return request_json(
        BINANCE_FUTURES,
        "/fapi/v1/exchangeInfo"
    )


def spot_exchange_info():

    return request_json(
        BINANCE_SPOT,
        "/api/v3/exchangeInfo"
    )


def find_symbol(
    coin,
    market
):

    base = clean_coin(coin)

    if market == "futures":

        data = futures_exchange_info()

    else:

        data = spot_exchange_info()

    for item in data.get(
        "symbols",
        []
    ):

        if (
            item.get("status") == "TRADING"
            and item.get("quoteAsset") == "USDT"
            and item.get("baseAsset") == base
        ):

            return item["symbol"]

    return None


# ============================================================
# COIN SEARCH
# ============================================================

def search_coins(query):

    query = clean_coin(query)

    if not query:
        return []

    results = {}

    try:

        data = futures_exchange_info()

        for item in data.get(
            "symbols",
            []
        ):

            if (
                item.get("status") == "TRADING"
                and item.get("quoteAsset") == "USDT"
            ):

                base = item.get(
                    "baseAsset",
                    ""
                )

                if (
                    query in base
                    or query in item["symbol"]
                ):

                    results.setdefault(
                        base,
                        {
                            "coin": base,
                            "spot": False,
                            "futures": False
                        }
                    )

                    results[
                        base
                    ]["futures"] = True

    except Exception:
        pass

    try:

        data = spot_exchange_info()

        for item in data.get(
            "symbols",
            []
        ):

            if (
                item.get("status") == "TRADING"
                and item.get("quoteAsset") == "USDT"
            ):

                base = item.get(
                    "baseAsset",
                    ""
                )

                if (
                    query in base
                    or query in item["symbol"]
                ):

                    results.setdefault(
                        base,
                        {
                            "coin": base,
                            "spot": False,
                            "futures": False
                        }
                    )

                    results[
                        base
                    ]["spot"] = True

    except Exception:
        pass

    return sorted(
        results.values(),
        key=lambda x: x["coin"]
    )[:30]


# ============================================================
# KLINES
# ============================================================

def get_klines(
    symbol,
    market,
    interval,
    limit=150
):

    if market == "futures":

        return request_json(
            BINANCE_FUTURES,
            "/fapi/v1/klines",
            {
                "symbol": symbol,
                "interval": interval,
                "limit": limit
            }
        )

    return request_json(
        BINANCE_SPOT,
        "/api/v3/klines",
        {
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }
    )


def parse_klines(data):

    result = []

    for candle in data:

        result.append({

            "time": int(
                candle[0] / 1000
            ),

            "open": float(
                candle[1]
            ),

            "high": float(
                candle[2]
            ),

            "low": float(
                candle[3]
            ),

            "close": float(
                candle[4]
            ),

            "volume": float(
                candle[5]
            )

        })

    return result


def candles(
    symbol,
    market,
    interval,
    limit=150
):

    return parse_klines(
        get_klines(
            symbol,
            market,
            interval,
            limit
        )
    )


# ============================================================
# EMA
# ============================================================

def calculate_ema(
    values,
    period
):

    if len(values) < period:
        return None

    multiplier = 2 / (
        period + 1
    )

    ema_value = (
        sum(values[:period])
        / period
    )

    for value in values[period:]:

        ema_value = (
            (
                value
                - ema_value
            )
            * multiplier
        ) + ema_value

    return ema_value


# ============================================================
# RSI
# ============================================================

def calculate_rsi(
    values,
    period=14
):

    if len(values) <= period:
        return None

    gains = []
    losses = []

    for i in range(
        1,
        len(values)
    ):

        change = (
            values[i]
            - values[i - 1]
        )

        if change >= 0:

            gains.append(change)
            losses.append(0)

        else:

            gains.append(0)
            losses.append(
                abs(change)
            )

    average_gain = (
        sum(gains[:period])
        / period
    )

    average_loss = (
        sum(losses[:period])
        / period
    )

    for i in range(
        period,
        len(gains)
    ):

        average_gain = (
            (
                average_gain
                * (period - 1)
            )
            + gains[i]
        ) / period

        average_loss = (
            (
                average_loss
                * (period - 1)
            )
            + losses[i]
        ) / period

    if average_loss == 0:
        return 100

    rs = (
        average_gain
        / average_loss
    )

    return (
        100
        - (
            100
            / (1 + rs)
        )
    )


# ============================================================
# MACD
# ============================================================

def calculate_macd(
    values
):

    if len(values) < 40:

        return {
            "macd": None,
            "signal": None,
            "histogram": None
        }

    macd_values = []

    for i in range(
        26,
        len(values) + 1
    ):

        fast = calculate_ema(
            values[:i],
            12
        )

        slow = calculate_ema(
            values[:i],
            26
        )

        if (
            fast is not None
            and slow is not None
        ):

            macd_values.append(
                fast - slow
            )

    if len(macd_values) < 9:

        return {
            "macd": None,
            "signal": None,
            "histogram": None
        }

    signal = calculate_ema(
        macd_values,
        9
    )

    macd_value = macd_values[-1]

    histogram = (
        macd_value - signal
        if signal is not None
        else None
    )

    return {
        "macd": macd_value,
        "signal": signal,
        "histogram": histogram
    }


# ============================================================
# ATR
# ============================================================

def calculate_atr(
    data,
    period=14
):

    if len(data) < period + 1:
        return None

    true_ranges = []

    for i in range(
        1,
        len(data)
    ):

        high = data[i]["high"]

        low = data[i]["low"]

        previous_close = (
            data[i - 1]["close"]
        )

        tr = max(
            high - low,
            abs(
                high
                - previous_close
            ),
            abs(
                low
                - previous_close
            )
        )

        true_ranges.append(tr)

    return (
        sum(
            true_ranges[-period:]
        )
        / period
    )


# ============================================================
# SINGLE TIMEFRAME ANALYSIS
# ============================================================

def analyze_timeframe(
    symbol,
    market,
    interval
):

    data = candles(
        symbol,
        market,
        interval,
        150
    )

    if len(data) < 60:

        raise Exception(
            "Not enough candle data"
        )

    closes = [
        x["close"]
        for x in data
    ]

    volumes = [
        x["volume"]
        for x in data
    ]

    price = closes[-1]

    ema20 = calculate_ema(
        closes,
        20
    )

    ema50 = calculate_ema(
        closes,
        50
    )

    ema100 = calculate_ema(
        closes,
        100
    )

    rsi = calculate_rsi(
        closes
    )

    macd = calculate_macd(
        closes
    )

    average_volume = (
        statistics.mean(
            volumes[-20:]
        )
    )

    volume_ratio = (
        volumes[-1]
        / average_volume
        if average_volume > 0
        else 0
    )

    bullish = 0

    bearish = 0

    reasons = []

    # -----------------------------
    # EMA TREND
    # -----------------------------

    if (
        ema20 is not None
        and price > ema20
    ):

        bullish += 2

        reasons.append(
            f"{interval}: price is above EMA20"
        )

    elif ema20 is not None:

        bearish += 2

        reasons.append(
            f"{interval}: price is below EMA20"
        )

    if (
        ema20 is not None
        and ema50 is not None
    ):

        if ema20 > ema50:

            bullish += 3

            reasons.append(
                f"{interval}: EMA20 is above EMA50"
            )

        else:

            bearish += 3

            reasons.append(
                f"{interval}: EMA20 is below EMA50"
            )

    if (
        ema50 is not None
        and ema100 is not None
    ):

        if ema50 > ema100:

            bullish += 2

            reasons.append(
                f"{interval}: medium trend is bullish"
            )

        else:

            bearish += 2

            reasons.append(
                f"{interval}: medium trend is bearish"
            )

    # -----------------------------
    # RSI
    # -----------------------------

    if rsi is not None:

        if 52 <= rsi <= 68:

            bullish += 2

            reasons.append(
                f"{interval}: RSI supports bullish momentum"
            )

        elif 32 <= rsi <= 48:

            bearish += 2

            reasons.append(
                f"{interval}: RSI supports bearish momentum"
            )

        elif rsi > 72:

            bearish += 1

            reasons.append(
                f"{interval}: RSI is overbought"
            )

        elif rsi < 28:

            bullish += 1

            reasons.append(
                f"{interval}: RSI is oversold"
            )

    # -----------------------------
    # MACD
    # -----------------------------

    if (
        macd["macd"] is not None
        and macd["signal"] is not None
    ):

        if (
            macd["macd"]
            > macd["signal"]
        ):

            bullish += 2

            reasons.append(
                f"{interval}: MACD is bullish"
            )

        else:

            bearish += 2

            reasons.append(
                f"{interval}: MACD is bearish"
            )

    # -----------------------------
    # VOLUME
    # -----------------------------

    if volume_ratio >= 1.4:

        if closes[-1] > closes[-2]:

            bullish += 2

            reasons.append(
                f"{interval}: buying volume expansion"
            )

        else:

            bearish += 2

            reasons.append(
                f"{interval}: selling volume expansion"
            )

    elif volume_ratio >= 1.1:

        if closes[-1] > closes[-2]:

            bullish += 1

        else:

            bearish += 1

    # -----------------------------
    # MOMENTUM
    # -----------------------------

    change_5 = (
        (
            price
            - closes[-6]
        )
        / closes[-6]
        * 100
    )

    change_20 = (
        (
            price
            - closes[-21]
        )
        / closes[-21]
        * 100
    )

    if change_5 > 0:

        bullish += 1

        reasons.append(
            f"{interval}: short-term momentum is positive"
        )

    else:

        bearish += 1

        reasons.append(
            f"{interval}: short-term momentum is negative"
        )

    if change_20 > 0:

        bullish += 1

    else:

        bearish += 1

    total = (
        bullish
        + bearish
    )

    if total == 0:

        direction = "WAIT"

        confidence = 0

    elif bullish > bearish:

        direction = "LONG"

        confidence = (
            bullish
            / total
            * 100
        )

    elif bearish > bullish:

        direction = "SHORT"

        confidence = (
            bearish
            / total
            * 100
        )

    else:

        direction = "WAIT"

        confidence = 50

    return {

        "interval": interval,

        "price": price,

        "ema20": ema20,

        "ema50": ema50,

        "ema100": ema100,

        "rsi": rsi,

        "macd": macd,

        "volume_ratio": volume_ratio,

        "momentum_5": change_5,

        "momentum_20": change_20,

        "bullish_score": bullish,

        "bearish_score": bearish,

        "direction": direction,

        "confidence": confidence,

        "reasons": reasons,

        "data": data

    }


# ============================================================
# FUTURES DATA
# ============================================================

def futures_extra(
    symbol
):

    result = {

        "open_interest": None,

        "funding_rate": None,

        "mark_price": None

    }

    try:

        oi = request_json(
            BINANCE_FUTURES,
            "/fapi/v1/openInterest",
            {
                "symbol": symbol
            }
        )

        result[
            "open_interest"
        ] = float(
            oi["openInterest"]
        )

    except Exception:
        pass

    try:

        funding = request_json(
            BINANCE_FUTURES,
            "/fapi/v1/premiumIndex",
            {
                "symbol": symbol
            }
        )

        result[
            "funding_rate"
        ] = float(
            funding.get(
                "lastFundingRate",
                0
            )
        )

        result[
            "mark_price"
        ] = float(
            funding.get(
                "markPrice",
                0
            )
        )

    except Exception:
        pass

    return result


# ============================================================
# COMPLETE TRADE ANALYSIS
# ============================================================

def build_analysis(
    coin,
    market="futures"
):

    symbol = find_symbol(
        coin,
        market
    )

    if not symbol:

        raise Exception(
            f"{clean_coin(coin)} is not available "
            f"as active USDT {market}"
        )

    timeframes = {}

    for interval in (
        "5m",
        "15m",
        "1h",
        "4h"
    ):

        timeframes[
            interval
        ] = analyze_timeframe(
            symbol,
            market,
            interval
        )

    directions = [
        timeframes[x]["direction"]
        for x in (
            "5m",
            "15m",
            "1h",
            "4h"
        )
    ]

    long_votes = directions.count(
        "LONG"
    )

    short_votes = directions.count(
        "SHORT"
    )

    # Higher timeframes have more weight
    weighted_long = (
        (
            1
            if directions[0] == "LONG"
            else 0
        )
        * 10
        +
        (
            1
            if directions[1] == "LONG"
            else 0
        )
        * 25
        +
        (
            1
            if directions[2] == "LONG"
            else 0
        )
        * 30
        +
        (
            1
            if directions[3] == "LONG"
            else 0
        )
        * 35
    )

    weighted_short = (
        (
            1
            if directions[0] == "SHORT"
            else 0
        )
        * 10
        +
        (
            1
            if directions[1] == "SHORT"
            else 0
        )
        * 25
        +
        (
            1
            if directions[2] == "SHORT"
            else 0
        )
        * 30
        +
        (
            1
            if directions[3] == "SHORT"
            else 0
        )
        * 35
    )

    if (
        weighted_long
        >= 70
        and long_votes >= 3
    ):

        direction = "LONG"

    elif (
        weighted_short
        >= 70
        and short_votes >= 3
    ):

        direction = "SHORT"

    else:

        direction = "WAIT"

    weighted_confidence = (
        max(
            weighted_long,
            weighted_short
        )
    )

    # Average technical confidence
    technical_confidence = sum(
        timeframes[x]["confidence"]
        for x in (
            "5m",
            "15m",
            "1h",
            "4h"
        )
    ) / 4

    confidence = (
        weighted_confidence * 0.55
        +
        technical_confidence * 0.45
    )

    reasons = []

    for interval in (
        "15m",
        "1h",
        "4h"
    ):

        reasons.extend(
            timeframes[
                interval
            ]["reasons"][:4]
        )

    # -----------------------------
    # DERIVATIVES
    # -----------------------------

    if market == "futures":

        extra = futures_extra(
            symbol
        )

        funding = extra[
            "funding_rate"
        ]

        if funding is not None:

            if (
                direction == "LONG"
                and funding < 0
            ):

                confidence += 2

                reasons.append(
                    "Negative funding supports the long idea"
                )

            elif (
                direction == "SHORT"
                and funding > 0
            ):

                confidence += 2

                reasons.append(
                    "Positive funding supports the short idea"
                )

            elif (
                direction == "LONG"
                and funding > 0.001
            ):

                confidence -= 4

                reasons.append(
                    "High positive funding shows crowded longs"
                )

            elif (
                direction == "SHORT"
                and funding < -0.001
            ):

                confidence -= 4

                reasons.append(
                    "Negative funding shows crowded shorts"
                )

    else:

        extra = {

            "open_interest": None,

            "funding_rate": None,

            "mark_price": None

        }

    # -----------------------------
    # PRICE STRUCTURE
    # -----------------------------

    base_data = timeframes[
        "15m"
    ]["data"]

    recent = base_data[-50:]

    support = min(
        x["low"]
        for x in recent
    )

    resistance = max(
        x["high"]
        for x in recent
    )

    price = (
        timeframes[
            "15m"
        ]["price"]
    )

    atr = calculate_atr(
        base_data
    )

    if atr is None:

        atr = price * 0.01

    # -----------------------------
    # TRADE LEVELS
    # -----------------------------

    if direction == "LONG":

        entry = price

        stop_loss = min(
            support,
            entry - (
                atr * 1.2
            )
        )

        risk = (
            entry
            - stop_loss
        )

        if risk <= 0:

            risk = atr

            stop_loss = (
                entry - risk
            )

        tp1 = (
            entry
            + risk * 1.5
        )

        tp2 = (
            entry
            + risk * 2.5
        )

        tp3 = (
            entry
            + risk * 3.5
        )

    elif direction == "SHORT":

        entry = price

        stop_loss = max(
            resistance,
            entry + (
                atr * 1.2
            )
        )

        risk = (
            stop_loss
            - entry
        )

        if risk <= 0:

            risk = atr

            stop_loss = (
                entry + risk
            )

        tp1 = (
            entry
            - risk * 1.5
        )

        tp2 = (
            entry
            - risk * 2.5
        )

        tp3 = (
            entry
            - risk * 3.5
        )

    else:

        entry = None
        stop_loss = None
        tp1 = None
        tp2 = None
        tp3 = None
        risk = 0

    if risk > 0:

        risk_reward = (
            abs(
                tp2 - entry
            )
            / risk
        )

    else:

        risk_reward = 0

    if risk_reward >= 3:

        confidence += 4

        reasons.append(
            "Risk/reward is above 1:3"
        )

    elif risk_reward >= 2:

        confidence += 2

        reasons.append(
            "Risk/reward is above 1:2"
        )

    confidence = round(
        max(
            0,
            min(
                confidence,
                100
            )
        ),
        2
    )

    # IMPORTANT:
    # 85%+ is model confidence,
    # NOT a guaranteed win.

    if (
        direction in (
            "LONG",
            "SHORT"
        )
        and confidence >= MIN_CONFIDENCE
    ):

        signal = direction

    elif direction in (
        "LONG",
        "SHORT"
    ):

        signal = "WATCH"

    else:

        signal = "WAIT"

    # -----------------------------
    # HUMAN EXPLANATION
    # -----------------------------

    if direction == "LONG":

        thesis = (
            "LONG because the higher timeframes "
            "are aligned bullish and the technical "
            "momentum is supporting upside continuation."
        )

    elif direction == "SHORT":

        thesis = (
            "SHORT because the higher timeframes "
            "are aligned bearish and the technical "
            "momentum is supporting downside continuation."
        )

    else:

        thesis = (
            "WAIT because the timeframes are not "
            "aligned strongly enough for a high-confidence setup."
        )

    return {

        "symbol": clean_coin(coin),

        "pair": symbol,

        "market": market,

        "signal": signal,

        "direction": direction,

        "confidence": confidence,

        "price": round(
            price,
            8
        ),

        "entry": (
            round(entry, 8)
            if entry is not None
            else None
        ),

        "stop_loss": (
            round(
                stop_loss,
                8
            )
            if stop_loss is not None
            else None
        ),

        "tp1": (
            round(
                tp1,
                8
            )
            if tp1 is not None
            else None
        ),

        "tp2": (
            round(
                tp2,
                8
            )
            if tp2 is not None
            else None
        ),

        "tp3": (
            round(
                tp3,
                8
            )
            if tp3 is not None
            else None
        ),

        "risk_reward": round(
            risk_reward,
            2
        ),

        "support": round(
            support,
            8
        ),

        "resistance": round(
            resistance,
            8
        ),

        "funding_rate":
            extra["funding_rate"],

        "open_interest":
            extra["open_interest"],

        "mark_price":
            extra["mark_price"],

        "timeframes": {

            x: timeframes[x][
                "direction"
            ]

            for x in (
                "5m",
                "15m",
                "1h",
                "4h"
            )

        },

        "indicators": {

            x: {

                "rsi": round(
                    timeframes[x]["rsi"],
                    2
                )
                if timeframes[x][
                    "rsi"
                ] is not None
                else None,

                "volume_ratio": round(
                    timeframes[x][
                        "volume_ratio"
                    ],
                    2
                ),

                "ema20": round(
                    timeframes[x]["ema20"],
                    8
                )
                if timeframes[x][
                    "ema20"
                ] is not None
                else None,

                "ema50": round(
                    timeframes[x]["ema50"],
                    8
                )
                if timeframes[x][
                    "ema50"
                ] is not None
                else None

            }

            for x in (
                "5m",
                "15m",
                "1h",
                "4h"
            )

        },

        "reasons": list(
            dict.fromkeys(
                reasons
            )
        )[:15],

        "thesis": thesis,

        "generated_at":
            datetime.now(
                timezone.utc
            ).isoformat()

    }


# ============================================================
# MARKET CANDIDATES
# ============================================================

def get_market_candidates(
    limit=6
):

    data = request_json(
        BINANCE_FUTURES,
        "/fapi/v1/ticker/24hr"
    )

    candidates = []

    for item in data:

        symbol = item.get(
            "symbol",
            ""
        )

        if (
            not symbol.endswith(
                "USDT"
            )
            or "_" in symbol
        ):
            continue

        try:

            change = abs(
                float(
                    item[
                        "priceChangePercent"
                    ]
                )
            )

            volume = float(
                item[
                    "quoteVolume"
                ]
            )

            movement_score = min(
                change,
                30
            )

            volume_score = min(
                volume
                / 100000000,
                10
            )

            activity_score = (
                movement_score
                * 0.35
                +
                volume_score
                * 0.65
            )

            candidates.append(
                (
                    activity_score,
                    symbol
                )
            )

        except Exception:
            continue

    candidates.sort(
        reverse=True
    )

    return [
        symbol
        for score, symbol
        in candidates[:limit]
    ]


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(
    message
):

    if (
        not TELEGRAM_BOT_TOKEN
        or not TELEGRAM_CHAT_ID
    ):

        return False

    try:

        response = session.post(
            "https://api.telegram.org/bot"
            + TELEGRAM_BOT_TOKEN
            + "/sendMessage",

            json={
                "chat_id":
                    TELEGRAM_CHAT_ID,

                "text":
                    message
            },

            timeout=10
        )

        return response.ok

    except Exception:

        return False


def alert_message(
    trade
):

    return (
        "RR TRADER HIGH CONFIDENCE SIGNAL\n\n"

        f"${trade['symbol']} "
        f"{trade['direction']}\n"

        f"Confidence: "
        f"{trade['confidence']}%\n\n"

        f"Entry: {trade['entry']}\n"

        f"SL: {trade['stop_loss']}\n"

        f"TP1: {trade['tp1']}\n"

        f"TP2: {trade['tp2']}\n"

        f"TP3: {trade['tp3']}\n\n"

        f"Risk/Reward: "
        f"{trade['risk_reward']}R\n\n"

        "WHY:\n"

        f"{trade['thesis']}\n\n"

        + "\n".join(
            "• " + reason
            for reason
            in trade["reasons"][:8]
        )

    )


# ============================================================
# AUTOMATIC MARKET SCANNER
# ============================================================

def automatic_scanner():

    while True:

        try:

            symbols = (
                get_market_candidates(
                    AUTO_SCAN_COINS
                )
            )

            signals = []

            for symbol in symbols:

                try:

                    analysis = build_analysis(
                        symbol,
                        "futures"
                    )

                    if (
                        analysis["signal"]
                        in (
                            "LONG",
                            "SHORT"
                        )
                        and
                        analysis[
                            "confidence"
                        ]
                        >= MIN_CONFIDENCE
                    ):

                        signals.append(
                            analysis
                        )

                        # Prevent duplicate alerts
                        alert_key = (
                            analysis[
                                "direction"
                            ],
                            round(
                                analysis[
                                    "confidence"
                                ] / 2
                            )
                        )

                        if (
                            last_alerts.get(
                                symbol
                            )
                            != alert_key
                        ):

                            sent = (
                                send_telegram(
                                    alert_message(
                                        analysis
                                    )
                                )
                            )

                            if sent:

                                last_alerts[
                                    symbol
                                ] = alert_key

                    # small delay protects API
                    time.sleep(
                        0.5
                    )

                except Exception:

                    continue

            signals.sort(
                key=lambda x: (
                    x["confidence"],
                    x["risk_reward"]
                ),
                reverse=True
            )

            scanner_state[
                "signals"
            ] = signals[:10]

            scanner_state[
                "last_scan"
            ] = datetime.now(
                timezone.utc
            ).isoformat()

            scanner_state[
                "error"
            ] = None

        except Exception as error:

            scanner_state[
                "error"
            ] = str(error)

        time.sleep(
            AUTO_SCAN_INTERVAL
        )


# Start scanner
threading.Thread(
    target=automatic_scanner,
    daemon=True
).start()


# ============================================================
# API ROUTES
# ============================================================

@app.get("/")
def home():

    return {

        "app":
            "RR Trader Live Scanner",

        "status":
            "online",

        "version":
            "5.0",

        "message":
            "RR Trader backend is working"

    }


@app.get(
    "/dashboard",
    response_class=HTMLResponse
)
def dashboard():

    return HTMLResponse(
        DASHBOARD_HTML
    )


@app.get("/search")
def search(
    q: str = Query(
        "",
        max_length=30
    )
):

    return {

        "success":
            True,

        "coins":
            search_coins(q)

    }


@app.get(
    "/analyze/{market}/{coin}"
)
def analyze(
    market: str,
    coin: str
):

    market = market.lower()

    if market not in (
        "spot",
        "futures"
    ):

        return {

            "success":
                False,

            "error":
                "Market must be spot or futures"

        }

    try:

        result = build_analysis(
            coin,
            market
        )

        return {

            "success":
                True,

            "analysis":
                result

        }

    except Exception as error:

        return {

            "success":
                False,

            "error":
                str(error)

        }


@app.get("/auto")
def auto_scanner_status():

    return {

        "success":
            True,

        "running":
            scanner_state[
                "running"
            ],

        "last_scan":
            scanner_state[
                "last_scan"
            ],

        "signals":
            scanner_state[
                "signals"
            ],

        "error":
            scanner_state[
                "error"
            ]

    }


@app.get(
    "/chart/{market}/{coin}"
)
def chart(
    market: str,
    coin: str
):

    try:

        symbol = find_symbol(
            coin,
            market
        )

        if not symbol:

            raise Exception(
                "Coin is not available"
            )

        data = candles(
            symbol,
            market,
            "15m",
            150
        )

        return {

            "success":
                True,

            "symbol":
                symbol,

            "market":
                market,

            "candles":
                data

        }

    except Exception as error:

        return {

            "success":
                False,

            "error":
                str(error)

        }


# ============================================================
# ANALYST BOT
# ============================================================

@app.get("/bot")
def analyst_bot(
    q: str = Query(
        ...,
        max_length=200
    )
):

    words = (
        q.upper()
        .replace(
            "?",
            " "
        )
        .replace(
            "/",
            " "
        )
        .split()
    )

    ignore = {
        "WHY",
        "IS",
        "THE",
        "A",
        "AN",
        "SHORT",
        "LONG",
        "BUY",
        "SELL",
        "OF",
        "FOR",
        "ME",
        "THIS",
        "COIN",
        "GIVE",
        "REASON",
        "REASONS",
        "ANALYZE"
    }

    coin = None

    for word in words:

        if (
            word.isalpha()
            and 2 <= len(word) <= 15
            and word not in ignore
        ):

            coin = word

            break

    if not coin:

        return {

            "success":
                False,

            "answer":
                "Ask something like: Why is ZEC short?"

        }

    try:

        analysis = build_analysis(
            coin,
            "futures"
        )

        answer = (

            f"${analysis['symbol']} "
            f"is currently "
            f"{analysis['direction']} "
            f"with "
            f"{analysis['confidence']}% "
            f"model confidence.\n\n"

            f"WHY:\n"
            f"{analysis['thesis']}\n\n"

            "Main reasons:\n"

            + "\n".join(
                "• " + reason
                for reason
                in analysis[
                    "reasons"
                ][:10]
            )

            + "\n\n"

            "Timeframe confirmation:\n"

            f"5m: "
            f"{analysis['timeframes']['5m']}\n"

            f"15m: "
            f"{analysis['timeframes']['15m']}\n"

            f"1h: "
            f"{analysis['timeframes']['1h']}\n"

            f"4h: "
            f"{analysis['timeframes']['4h']}\n\n"

            f"Entry: "
            f"{analysis['entry']}\n"

            f"SL: "
            f"{analysis['stop_loss']}\n"

            f"TP1: "
            f"{analysis['tp1']}\n"

            f"TP2: "
            f"{analysis['tp2']}\n"

            f"TP3: "
            f"{analysis['tp3']}\n"

            f"R:R: "
            f"{analysis['risk_reward']}R"

        )

        return {

            "success":
                True,

            "answer":
                answer,

            "analysis":
                analysis

        }

    except Exception as error:

        return {

            "success":
                False,

            "answer":
                str(error)

        }


# ============================================================
# MANUAL TELEGRAM ALERT
# ============================================================

@app.post(
    "/telegram/send/{coin}"
)
def manual_telegram(
    coin: str
):

    try:

        analysis = build_analysis(
            coin,
            "futures"
        )

        if (
            analysis["signal"]
            not in (
                "LONG",
                "SHORT"
            )
            or
            analysis[
                "confidence"
            ] < MIN_CONFIDENCE
        ):

            return {

                "success":
                    True,

                "sent":
                    False,

                "reason":
                    "No 85%+ high-confidence setup",

                "analysis":
                    analysis

            }

        sent = send_telegram(
            alert_message(
                analysis
            )
        )

        return {

            "success":
                True,

            "sent":
                sent,

            "analysis":
                analysis

        }

    except Exception as error:

        return {

            "success":
                False,

            "error":
                str(error)

        }


# ============================================================
# DASHBOARD
# ============================================================

DASHBOARD_HTML = r"""
<!DOCTYPE html>

<html>

<head>

<meta name="viewport"
content="width=device-width,initial-scale=1">

<title>RR Trader Live Scanner</title>

<script src=
"https://cdn.jsdelivr.net/npm/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.min.js">
</script>

<style>

*{
box-sizing:border-box;
}

body{

margin:0;

background:#06101c;

color:#eaf3ff;

font-family:
Arial,
sans-serif;

}

.header{

padding:20px;

background:#0a1726;

border-bottom:
1px solid #20334a;

position:sticky;

top:0;

z-index:10;

}

.header h1{

margin:0;

font-size:24px;

}

.live{

margin-top:6px;

color:#32e6a1;

font-size:13px;

}

.container{

max-width:1150px;

margin:auto;

padding:15px;

}

.card{

background:#0b1a2b;

border:
1px solid #1e354e;

border-radius:14px;

padding:16px;

margin-bottom:14px;

}

.search{

display:flex;

gap:8px;

}

input{

width:100%;

background:#071321;

color:white;

border:
1px solid #29435f;

border-radius:9px;

padding:12px;

outline:none;

}

button{

background:#10263e;

color:white;

border:
1px solid #31516f;

border-radius:9px;

padding:11px 15px;

cursor:pointer;

}

button:hover{

border-color:#36e6a3;

}

.coins{

display:flex;

flex-wrap:wrap;

gap:8px;

margin-top:12px;

}

.coin{

background:#10263d;

border-radius:9px;

padding:10px 14px;

cursor:pointer;

}

.coin:hover{

background:#163652;

}

.market-buttons{

display:flex;

gap:8px;

margin-top:12px;

}

.active{

border-color:#36e6a3;

}

.muted{

color:#8fa5bc;

}

.trade{

border-left:
5px solid #6e8298;

}

.long{

border-left-color:
#32e6a1;

}

.short{

border-left-color:
#ff5e73;

}

.confidence{

font-size:30px;

font-weight:bold;

margin:8px 0;

}

.grid{

display:grid;

grid-template-columns:
repeat(3,1fr);

gap:8px;

}

.box{

background:#071321;

padding:11px;

border-radius:8px;

}

.reason{

margin:5px 0;

}

.signals{

display:grid;

grid-template-columns:
repeat(
auto-fit,
minmax(240px,1fr)
);

gap:10px;

}

.signal{

padding:13px;

background:#071321;

border-radius:10px;

}

#chart{

width:100%;

height:430px;

}

pre{

white-space:pre-wrap;

font-family:Arial;

line-height:1.5;

}

@media(max-width:600px){

.grid{

grid-template-columns:
repeat(2,1fr);

}

#chart{

height:350px;

}

}

</style>

</head>

<body>

<div class="header">

<h1>
RR Trader Live Scanner
</h1>

<div class="live">
● LIVE BINANCE MARKET
</div>

</div>


<div class="container">


<div class="card">

<h2>
Coin Search
</h2>

<div class="search">

<input
id="search"
placeholder=
"Search coin: BTC, ETH, ZEC, SOL..."
oninput="searchCoins()">

<button onclick="searchCoins()">
Search
</button>

</div>

<div
id="coins"
class="coins">
</div>

<div
id="selected"
class="muted"
style="margin-top:12px">

No coin selected

</div>

<div
class="market-buttons">

<button
id="spotButton"
onclick="selectMarket('spot')">

SPOT

</button>

<button
id="futureButton"
class="active"
onclick="selectMarket('futures')">

FUTURES

</button>

<button
onclick="runAnalysis()">

ANALYZE

</button>

</div>

</div>


<div id="manual">
</div>


<div class="card">

<h2>
Automatic Market Analyzer
</h2>

<div class="muted">

Independent scanner.
Only 85%+ high-confidence
model signals are displayed.

</div>

<div
id="automatic"
class="signals"
style="margin-top:12px">

Loading scanner...

</div>

</div>


<div class="card">

<h2>
Analyst Bot
</h2>

<div class="muted">

Ask why the scanner is LONG,
SHORT or WAIT.

</div>

<div
class="search"
style="margin-top:10px">

<input
id="question"
placeholder=
"Why is ZEC short?">

<button
onclick="askBot()">

Ask

</button>

</div>

<pre
id="botAnswer">
</pre>

</div>


<div class="card">

<h2>
Live 15m Chart
</h2>

<div id="chart">
</div>

</div>


</div>


<script>

let selectedCoin = "";

let market = "futures";

let chart = null;

let candleSeries = null;


function selectMarket(value){

market = value;

document
.getElementById(
"spotButton"
)
.classList
.toggle(
"active",
value === "spot"
);

document
.getElementById(
"futureButton"
)
.classList
.toggle(
"active",
value === "futures"
);

}


async function searchCoins(){

const query =
document
.getElementById(
"search"
)
.value
.trim();

if(!query){

document
.getElementById(
"coins"
)
.innerHTML = "";

return;

}

try{

const response =
await fetch(
"/search?q="
+
encodeURIComponent(
query
)
);

const data =
await response.json();

const html =
data.coins
.map(
coin => `

<div
class="coin"
onclick=
"selectCoin('${coin.coin}')">

$${coin.coin}

</div>

`
)
.join("");

document
.getElementById(
"coins"
)
.innerHTML = html;

}

catch(error){

console.log(error);

}

}


function selectCoin(coin){

selectedCoin = coin;

document
.getElementById(
"selected"
)
.innerText =
"Selected: $"
+
coin;

runAnalysis();

}


async function runAnalysis(){

if(!selectedCoin){

return;

}

const box =
document
.getElementById(
"manual"
);

box.innerHTML =
'<div class="card">Analyzing...</div>';

try{

const response =
await fetch(
"/analyze/"
+
market
+
"/"
+
selectedCoin
);

const data =
await response.json();

if(!data.success){

box.innerHTML =
`
<div class="card">
${data.error}
</div>
`;

return;

}

renderAnalysis(
data.analysis
);

loadChart();

}

catch(error){

box.innerHTML =
`
<div class="card">
${error}
</div>
`;

}

}


function renderAnalysis(t){

const className =
t.direction === "LONG"
? "long"
: t.direction === "SHORT"
? "short"
: "";

let reasons =
t.reasons
.map(
x =>
`
<div class="reason">
• ${x}
</div>
`
)
.join("");

document
.getElementById(
"manual"
)
.innerHTML =

`

<div
class="card trade ${className}">

<h2>

$${t.symbol}
${t.direction}

</h2>

<div class="confidence">

${t.confidence}%

</div>

<div class="muted">

${t.market.toUpperCase()}
|
5m ${t.timeframes["5m"]}
|
15m ${t.timeframes["15m"]}
|
1h ${t.timeframes["1h"]}
|
4h ${t.timeframes["4h"]}

</div>

<br>

<div class="grid">

<div class="box">
Entry<br>
<b>${t.entry}</b>
</div>

<div class="box">
Stop Loss<br>
<b>${t.stop_loss}</b>
</div>

<div class="box">
TP1<br>
<b>${t.tp1}</b>
</div>

<div class="box">
TP2<br>
<b>${t.tp2}</b>
</div>

<div class="box">
TP3<br>
<b>${t.tp3}</b>
</div>

<div class="box">
R:R<br>
<b>${t.risk_reward}R</b>
</div>

</div>

<br>

<b>
WHY ${t.direction}?
</b>

<p>
${t.thesis}
</p>

${reasons}

</div>

`;

}


async function loadAutomatic(){

try{

const response =
await fetch(
"/auto"
);

const data =
await response.json();

const container =
document
.getElementById(
"automatic"
);

if(
!data.signals
||
data.signals.length === 0
){

container.innerHTML =
`

<div class="muted">

No 85%+ setup yet.
Scanner is continuously
monitoring the market.

</div>

`;

return;

}

container.innerHTML =
data.signals
.map(
t => `

<div
class="signal">

<b>
$${t.symbol}
</b>

<div
class="confidence">

${t.confidence}%

</div>

<b>
${t.direction}
</b>

<br><br>

Entry:
${t.entry}

<br>

SL:
${t.stop_loss}

<br>

TP2:
${t.tp2}

<br>

R:R:
${t.risk_reward}R

</div>

`
)
.join("");

}

catch(error){

console.log(error);

}

}


async function askBot(){

const question =
document
.getElementById(
"question"
)
.value
.trim();

if(!question){

return;

}

document
.getElementById(
"botAnswer"
)
.innerText =
"Analyzing market data...";

try{

const response =
await fetch(
"/bot?q="
+
encodeURIComponent(
question
)
);

const data =
await response.json();

document
.getElementById(
"botAnswer"
)
.innerText =
data.answer
||
"No answer available.";

}

catch(error){

document
.getElementById(
"botAnswer"
)
.innerText =
"Unable to analyze right now.";

}

}


async function loadChart(){

if(!selectedCoin){

return;

}

try{

const response =
await fetch(
"/chart/"
+
market
+
"/"
+
selectedCoin
);

const data =
await response.json();

if(!data.success){

return;

}

const element =
document
.getElementById(
"chart"
);

element.innerHTML = "";

chart =
LightweightCharts
.createChart(
element,
{

width:
element.clientWidth,

height:430,

layout:{

background:{
color:"#06101c"
},

textColor:"#b9cbe0"

},

grid:{

vertLines:{
color:"#122337"
},

horzLines:{
color:"#122337"
}

}

}
);

candleSeries =
chart.addCandlestickSeries();

candleSeries.setData(
data.candles
);

chart
.timeScale()
.fitContent();

}

catch(error){

console.log(error);

}

}


setInterval(
loadAutomatic,
15000
);

loadAutomatic();

</script>

</body>

</html>
"""


# ============================================================
# END
# ============================================================
