from __future__ import annotations

import asyncio
import json
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from fastapi import APIRouter, Query


# =========================================================
# RR TRADER — LIQUIDATION INTELLIGENCE ENGINE
# =========================================================

router = APIRouter(
    prefix="/liquidation",
    tags=["Liquidation Intelligence"],
)


BINANCE_FUTURES_API = "https://fapi.binance.com"


# =========================================================
# HTTP HELPER
# =========================================================

def _get_json(url: str, timeout: int = 10):

    request = Request(
        url,
        headers={
            "User-Agent": "RR-Trader-Liquidation-Engine/1.0",
            "Accept": "application/json",
        },
    )

    with urlopen(
        request,
        timeout=timeout,
    ) as response:

        raw = response.read().decode("utf-8")

        return json.loads(raw)


async def get_json(url: str):

    return await asyncio.to_thread(
        _get_json,
        url,
    )


# =========================================================
# SAFE NUMBER
# =========================================================

def safe_float(value, default=0.0):

    try:
        return float(value)

    except Exception:
        return default


# =========================================================
# SYMBOL NORMALIZER
# =========================================================

def normalize_symbol(symbol: str) -> str:

    symbol = (
        symbol
        .upper()
        .replace("/", "")
        .replace("-", "")
        .strip()
    )

    if not symbol.endswith("USDT"):

        symbol += "USDT"

    return symbol


# =========================================================
# ESTIMATED LIQUIDATION LEVEL
# =========================================================
#
# Important:
# Binance public APIs do NOT expose the complete
# position-by-position liquidation map used by CoinGlass.
#
# Therefore RR Trader creates an ESTIMATED liquidation
# intelligence model using:
#
# - current price
# - leverage bands
# - open interest
# - funding
# - market direction
#
# This is an intelligence estimate, NOT CoinGlass data.
# =========================================================

def estimated_liquidation_price(
    price: float,
    leverage: float,
    side: str,
):

    if price <= 0:
        return 0.0

    # Simplified liquidation approximation.
    #
    # Long positions are vulnerable below market.
    # Short positions are vulnerable above market.

    distance = 1.0 / leverage

    if side == "LONG":

        return price * (
            1.0 - distance
        )

    return price * (
        1.0 + distance
    )


# =========================================================
# BUILD LIQUIDATION LEVELS
# =========================================================

def build_liquidation_levels(
    price: float,
    open_interest: float,
):

    leverage_bands = [
        5,
        10,
        20,
        25,
        50,
        75,
        100,
    ]

    levels = []

    for leverage in leverage_bands:

        long_price = estimated_liquidation_price(
            price,
            leverage,
            "LONG",
        )

        short_price = estimated_liquidation_price(
            price,
            leverage,
            "SHORT",
        )

        # Higher leverage = more sensitive zone.
        #
        # This is only a relative intensity score.

        intensity = min(
            100.0,
            25.0
            + (
                leverage / 100.0
            )
            * 75.0,
        )

        levels.append(
            {
                "side": "LONG",
                "leverage": leverage,
                "price": round(
                    long_price,
                    8,
                ),
                "distance_percent": round(
                    abs(
                        (
                            long_price
                            - price
                        )
                        / price
                    )
                    * 100,
                    4,
                ),
                "intensity": round(
                    intensity,
                    2,
                ),
            }
        )

        levels.append(
            {
                "side": "SHORT",
                "leverage": leverage,
                "price": round(
                    short_price,
                    8,
                ),
                "distance_percent": round(
                    abs(
                        (
                            short_price
                            - price
                        )
                        / price
                    )
                    * 100,
                    4,
                ),
                "intensity": round(
                    intensity,
                    2,
                ),
            }
        )

    return levels


# =========================================================
# LIQUIDATION BIAS
# =========================================================

def calculate_liquidation_bias(
    price: float,
    levels: list,
    funding_rate: float,
):

    long_levels = [
        x
        for x in levels
        if x["side"] == "LONG"
    ]

    short_levels = [
        x
        for x in levels
        if x["side"] == "SHORT"
    ]

    nearest_long = min(
        long_levels,
        key=lambda x: x["distance_percent"],
    )

    nearest_short = min(
        short_levels,
        key=lambda x: x["distance_percent"],
    )

    # Funding interpretation
    #
    # Positive funding:
    # more pressure on longs
    #
    # Negative funding:
    # more pressure on shorts.

    if funding_rate > 0:

        funding_bias = "LONG_LIQUIDATION_RISK"

    elif funding_rate < 0:

        funding_bias = "SHORT_LIQUIDATION_RISK"

    else:

        funding_bias = "NEUTRAL"

    if (
        funding_bias
        == "LONG_LIQUIDATION_RISK"
    ):

        directional_bias = "DOWN"

    elif (
        funding_bias
        == "SHORT_LIQUIDATION_RISK"
    ):

        directional_bias = "UP"

    else:

        directional_bias = "NEUTRAL"

    return {
        "direction": directional_bias,
        "funding_bias": funding_bias,
        "nearest_long_liquidation": nearest_long,
        "nearest_short_liquidation": nearest_short,
    }


# =========================================================
# HEATMAP DATA
# =========================================================

def build_heatmap(
    price: float,
    levels: list,
):

    # Sort levels around current price.

    sorted_levels = sorted(
        levels,
        key=lambda x: x["price"],
    )

    return {
        "current_price": price,
        "levels": sorted_levels,
        "lower_side": [
            x
            for x in sorted_levels
            if x["price"] < price
        ],
        "upper_side": [
            x
            for x in sorted_levels
            if x["price"] > price
        ],
    }


# =========================================================
# STATUS
# =========================================================

@router.get("/status")
async def liquidation_status():

    return {
        "success": True,
        "engine": "RR Trader Liquidation Intelligence",
        "status": "online",
        "mode": "estimated",
        "source": "Binance public futures market data",
        "coinglass_api_required": False,
        "note": (
            "RR Trader estimates liquidation zones "
            "from public market data. It does not "
            "replicate CoinGlass private liquidation "
            "heatmap data."
        ),
    }


# =========================================================
# ANALYZE COIN
# =========================================================

@router.get("/analyze")
async def analyze_liquidation(
    symbol: str = Query(
        "BTCUSDT",
        min_length=3,
        max_length=30,
    )
):

    symbol = normalize_symbol(
        symbol
    )

    try:

        ticker_url = (
            f"{BINANCE_FUTURES_API}"
            f"/fapi/v1/ticker/24hr"
            f"?symbol={symbol}"
        )

        oi_url = (
            f"{BINANCE_FUTURES_API}"
            f"/fapi/v1/openInterest"
            f"?symbol={symbol}"
        )

        funding_url = (
            f"{BINANCE_FUTURES_API}"
            f"/fapi/v1/premiumIndex"
            f"?symbol={symbol}"
        )

        ticker, oi_data, funding = (
            await asyncio.gather(
                get_json(ticker_url),
                get_json(oi_url),
                get_json(funding_url),
            )
        )

        price = safe_float(
            ticker.get("lastPrice")
        )

        volume = safe_float(
            ticker.get("quoteVolume")
        )

        change_24h = safe_float(
            ticker.get("priceChangePercent")
        )

        open_interest = safe_float(
            oi_data.get("openInterest")
        )

        funding_rate = safe_float(
            funding.get("lastFundingRate")
        )

        if price <= 0:

            return {
                "success": False,
                "error": (
                    "Unable to obtain "
                    "current market price."
                ),
            }

        levels = build_liquidation_levels(
            price=price,
            open_interest=open_interest,
        )

        bias = calculate_liquidation_bias(
            price=price,
            levels=levels,
            funding_rate=funding_rate,
        )

        heatmap = build_heatmap(
            price=price,
            levels=levels,
        )

        return {
            "success": True,

            "symbol": symbol,

            "engine": {
                "name": (
                    "RR Trader "
                    "Liquidation Intelligence"
                ),
                "mode": "estimated",
                "source": (
                    "Binance public futures API"
                ),
            },

            "market": {
                "price": price,
                "change_24h_percent": change_24h,
                "volume_24h_usdt": volume,
                "open_interest": open_interest,
                "funding_rate": funding_rate,
            },

            "liquidation": {
                "bias": bias,
                "heatmap": heatmap,
                "levels": levels,
            },

            "timestamp": int(
                time.time() * 1000
            ),
        }

    except HTTPError as exc:

        return {
            "success": False,
            "error": (
                "Binance API HTTP error."
            ),
            "status_code": exc.code,
            "symbol": symbol,
        }

    except URLError as exc:

        return {
            "success": False,
            "error": (
                "Unable to connect "
                "to Binance."
            ),
            "detail": str(exc),
            "symbol": symbol,
        }

    except Exception as exc:

        return {
            "success": False,
            "error": (
                "Liquidation engine error."
            ),
            "detail": str(exc),
            "symbol": symbol,
        }


# =========================================================
# HEATMAP
# =========================================================

@router.get("/heatmap")
async def liquidation_heatmap(
    symbol: str = Query(
        "BTCUSDT",
        min_length=3,
        max_length=30,
    )
):

    result = await analyze_liquidation(
        symbol=symbol
    )

    if not result.get("success"):

        return result

    return {
        "success": True,
        "symbol": result["symbol"],
        "current_price": (
            result["market"]["price"]
        ),
        "heatmap": (
            result["liquidation"]["heatmap"]
        ),
        "bias": (
            result["liquidation"]["bias"]
        ),
        "timestamp": result["timestamp"],
    }
