from fastapi import FastAPI
import requests
import statistics
from datetime import datetime, timezone

app = FastAPI(title="RR Trader Live Crypto Scanner")

BINANCE_URL = "https://fapi.binance.com"

session = requests.Session()
session.headers.update({
    "User-Agent": "RR-Trader/1.0"
})


def get_json(path, params=None):
    r = session.get(
        BINANCE_URL + path,
        params=params,
        timeout=15
    )
    r.raise_for_status()
    return r.json()


def candles(symbol, interval="15m", limit=100):
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
            "time": x[0],
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


def technical_analysis(symbol, interval="15m"):
    data = candles(symbol, interval, 100)

    if len(data) < 30:
        raise Exception("Not enough candle data")

    closes = [x["close"] for x in data]
    volumes = [x["volume"] for x in data]

    current = data[-1]
    previous = data[-2]

    price = current["close"]

    # Moving averages
    ma20 = statistics.mean(closes[-20:])
    ma50 = statistics.mean(closes[-50:])

    # Average volume
    avg_volume = statistics.mean(volumes[-20:])
    volume_ratio = (
        current["volume"] / avg_volume
        if avg_volume > 0 else 0
    )

    # Momentum
    change_5 = (
        (price - closes[-6]) / closes[-6] * 100
        if closes[-6] else 0
    )

    change_20 = (
        (price - closes[-21]) / closes[-21] * 100
        if closes[-21] else 0
    )

    bullish = 0
    bearish = 0
    reasons = []

    # Trend
    if price > ma20:
        bullish += 1
        reasons.append("price above MA20")
    else:
        bearish += 1
        reasons.append("price below MA20")

    if ma20 > ma50:
        bullish += 2
        reasons.append("MA20 above MA50")
    else:
        bearish += 2
        reasons.append("MA20 below MA50")

    # Momentum
    if change_5 > 0:
        bullish += 1
        reasons.append("short-term momentum positive")
    else:
        bearish += 1
        reasons.append("short-term momentum negative")

    if change_20 > 0:
        bullish += 1
        reasons.append("20-candle momentum positive")
    else:
        bearish += 1
        reasons.append("20-candle momentum negative")

    # Volume
    if volume_ratio >= 1.5:
        if change_5 > 0:
            bullish += 2
            reasons.append("strong buying volume")
        else:
            bearish += 2
            reasons.append("strong selling volume")
    elif volume_ratio >= 1.1:
        if change_5 > 0:
            bullish += 1
        else:
            bearish += 1

    # Candle direction
    if current["close"] > current["open"]:
        bullish += 1
    else:
        bearish += 1

    # Previous/current momentum
    if current["close"] > previous["close"]:
        bullish += 1
    else:
        bearish += 1

    total = bullish + bearish

    if total == 0:
        confidence = 0
    else:
        confidence = round(
            max(bullish, bearish) / total * 100,
            2
        )

    if bullish > bearish:
        direction = "LONG"
    elif bearish > bullish:
        direction = "SHORT"
    else:
        direction = "WAIT"

    # Strong signal requires more confirmation
    if confidence < 65:
        signal = "WAIT"
    elif confidence >= 80:
        signal = direction
    else:
        signal = "WATCH"

    recent_lows = [x["low"] for x in data[-20:]]
    recent_highs = [x["high"] for x in data[-20:]]

    support = min(recent_lows)
    resistance = max(recent_highs)

    return {
        "price": price,
        "signal": signal,
        "direction": direction,
        "confidence": confidence,
        "bullish_score": bullish,
        "bearish_score": bearish,
        "ma20": ma20,
        "ma50": ma50,
        "volume_ratio": round(volume_ratio, 2),
        "momentum_5": round(change_5, 2),
        "momentum_20": round(change_20, 2),
        "support": support,
        "resistance": resistance,
        "reasons": reasons,
        "candles": data[-10:]
    }


@app.get("/")
def home():
    return {
        "app": "RR Trader Live Scanner",
        "status": "online",
        "version": "2.0",
        "message": "RR Trader backend is working"
    }


@app.get("/market/scan")
def market_scan():
    try:
        data = get_json("/fapi/v1/ticker/24hr")

        candidates = []

        for item in data:
            symbol = item.get("symbol", "")

            if not symbol.endswith("USDT"):
                continue

            try:
                price = float(item["lastPrice"])
                change = float(item["priceChangePercent"])
                volume = float(item["quoteVolume"])
                high = float(item["highPrice"])
                low = float(item["lowPrice"])

                if volume <= 0:
                    continue

                # Activity score
                movement = min(abs(change), 30)
                volume_score = min(volume / 100000000, 10)

                activity = round(
                    movement * 0.35 +
                    volume_score * 0.65,
                    2
                )

                candidates.append({
                    "symbol": symbol,
                    "price": price,
                    "change_24h": change,
                    "volume_24h": volume,
                    "high_24h": high,
                    "low_24h": low,
                    "activity_score": activity
                })

            except (ValueError, TypeError, KeyError):
                continue

        candidates.sort(
            key=lambda x: x["activity_score"],
            reverse=True
        )

        return {
            "success": True,
            "total_coins": len(candidates),
            "top_candidates": candidates[:30]
        }

    except Exception as error:
        return {
            "success": False,
            "error": str(error)
        }


@app.get("/analysis/{symbol}")
def analysis(symbol: str):
    symbol = symbol.upper()

    try:
        technical = technical_analysis(symbol)
        extra = market_extra(symbol)

        return {
            "success": True,
            "symbol": symbol,
            "timeframe": "15m",
            "technical": technical,
            "derivatives": extra
        }

    except Exception as error:
        return {
            "success": False,
            "symbol": symbol,
            "error": str(error)
        }


@app.get("/signal/{symbol}")
def signal(symbol: str):
    symbol = symbol.upper()

    try:
        technical = technical_analysis(symbol)
        extra = market_extra(symbol)

        reasons = technical["reasons"].copy()

        funding = extra.get("funding_rate")

        if funding is not None:

            if funding > 0.001:
                reasons.append(
                    "high positive funding may indicate crowded longs"
                )

                if technical["signal"] == "LONG":
                    technical["confidence"] = max(
                        0,
                        technical["confidence"] - 5
                    )

            elif funding < -0.001:
                reasons.append(
                    "negative funding may indicate short pressure"
                )

        return {
            "success": True,
            "symbol": symbol,
            "signal": technical["signal"],
            "direction": technical["direction"],
            "confidence": technical["confidence"],
            "price": technical["price"],
            "support": technical["support"],
            "resistance": technical["resistance"],
            "volume_ratio": technical["volume_ratio"],
            "momentum_5": technical["momentum_5"],
            "momentum_20": technical["momentum_20"],
            "open_interest": extra["open_interest"],
            "funding_rate": extra["funding_rate"],
            "mark_price": extra["mark_price"],
            "reasons": reasons,
            "generated_at": datetime.now(
                timezone.utc
            ).isoformat()
        }

    except Exception as error:
        return {
            "success": False,
            "symbol": symbol,
            "error": str(error)
        }


@app.get("/explain/{symbol}")
def explain(symbol: str):
    symbol = symbol.upper()

    try:
        technical = technical_analysis(symbol)
        extra = market_extra(symbol)

        signal_value = technical["signal"]

        if signal_value == "LONG":
            explanation = (
                "Bullish conditions are stronger. "
                "Price trend, momentum and volume are "
                "supporting the long direction."
            )

        elif signal_value == "SHORT":
            explanation = (
                "Bearish conditions are stronger. "
                "Price trend, momentum and volume are "
                "supporting the short direction."
            )

        elif signal_value == "WATCH":
            explanation = (
                "The market has some directional confirmation "
                "but not enough strength for a high-confidence signal."
            )

        else:
            explanation = (
                "There is no strong directional confirmation. "
                "Waiting is safer until more confirmation appears."
            )

        return {
            "success": True,
            "symbol": symbol,
            "signal": signal_value,
            "confidence": technical["confidence"],
            "explanation": explanation,
            "technical_reasons": technical["reasons"],
            "funding_rate": extra["funding_rate"],
            "open_interest": extra["open_interest"],
            "warning": "This is an analytical model, not a guaranteed prediction."
        }

    except Exception as error:
        return {
            "success": False,
            "symbol": symbol,
            "error": str(error)
        }
