from fastapi import FastAPI
import requests
import time

app = FastAPI(title="RR Trader Live Scanner")

BINANCE_URL = "https://fapi.binance.com"


@app.get("/")
def home():
    return {
        "app": "RR Trader Live Scanner",
        "status": "online",
        "message": "RR Trader backend is working"
    }


@app.get("/market/scan")
def market_scan():

    url = f"{BINANCE_URL}/fapi/v1/ticker/24hr"

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()

    except Exception as error:
        return {
            "success": False,
            "error": str(error)
        }

    coins = []

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

        except (ValueError, TypeError, KeyError):
            continue

        if volume <= 0 or price <= 0:
            continue

        price_movement_score = min(abs(change), 10)
        volume_score = min(volume / 100_000_000, 10)

        activity_score = (
            price_movement_score +
            volume_score
        )

        coins.append({
            "symbol": symbol,
            "price": price,
            "change_24h": round(change, 2),
            "volume_24h": round(volume, 2),
            "high_24h": high,
            "low_24h": low,
            "activity_score": round(activity_score, 2)
        })

    coins.sort(
        key=lambda coin: coin["activity_score"],
        reverse=True
    )

    return {
        "success": True,
        "total_coins": len(coins),
        "top_candidates": coins[:20],
        "timestamp": int(time.time())
    }
