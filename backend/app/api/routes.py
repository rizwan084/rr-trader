from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings
from app.services.market_data import market_data_service
from app.services.market_scanner import (
    MarketScanner,
)
from app.services.signal_engine import (
    signal_engine,
)
from app.services.signal_memory import (
    signal_memory,
)


router = APIRouter()

market_scanner = MarketScanner(
    market_data_service
)


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

    clean_market = (
        str(market)
        .lower()
        .strip()
    )

    if clean_market not in {
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

    clean = (
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

    if not clean:

        return {
            "success": True,
            "market": clean_market,
            "coins": [],
        }

    target_symbol = (
        f"{clean}USDT"
    )

    # -----------------------------------------------------
    # Verify the symbol against Binance exchange info.
    # -----------------------------------------------------

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

    matches: list[
        dict[str, Any]
    ] = []

    for item in symbols:

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

        if symbol != target_symbol:
            continue

        status = str(
            item.get(
                "status",
                "TRADING",
            )
        ).upper()

        if status != "TRADING":
            continue

        matches.append(
            {
                "symbol": symbol,
                "coin": clean,
                "market": clean_market,
                "base_asset": item.get(
                    "baseAsset"
                ),
                "quote_asset": item.get(
                    "quoteAsset"
                ),
                "status": status,
            }
        )

    return {
        "success": True,
        "market": clean_market,
        "query": clean,
        "coins": matches,
    }


# =========================================================
# ANALYZE SINGLE SYMBOL
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

    clean_market = (
        str(market)
        .lower()
        .strip()
    )

    if clean_market not in {
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

    clean_symbol = (
        str(symbol)
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

    if not clean_symbol:

        raise HTTPException(
            status_code=400,
            detail="symbol is required",
        )

    if not clean_symbol.endswith(
        "USDT"
    ):

        clean_symbol = (
            f"{clean_symbol}USDT"
        )

    try:

        result = await (
            signal_engine.analyze_symbol(
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

    # -----------------------------------------------------
    # Store only useful directional signals.
    # -----------------------------------------------------

    if result.get(
        "direction"
    ) in {
        "LONG",
        "SHORT",
    }:

        signal_memory.add(
            {
                "symbol": clean_symbol,
                "market": clean_market,
                "direction": result.get(
                    "direction"
                ),
                "confidence": result.get(
                    "confidence",
                    0,
                ),
                "publishable": result.get(
                    "publishable",
                    False,
                ),
                "multi_timeframe": result.get(
                    "multi_timeframe",
                    {},
                ),
                "reasons": result.get(
                    "reasons",
                    [],
                ),
                "timeframes": result.get(
                    "timeframes",
                    {},
                ),
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
        le=50,
    ),
    candle_limit: int = Query(
        default=120,
        ge=50,
        le=300,
    ),
) -> dict[str, Any]:

    clean_market = (
        str(market)
        .lower()
        .strip()
    )

    if clean_market not in {
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

    try:

        # -------------------------------------------------
        # Full-market cheap screening
        # -------------------------------------------------

        universe_result = (
            await market_scanner
            .top_candidates(
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

    candidates = (
        universe_result.get(
            "candidates",
            [],
        )
    )

    # -----------------------------------------------------
    # Deep analysis
    # -----------------------------------------------------

    async def analyze_candidate(
        item: dict[str, Any],
    ) -> dict[str, Any]:

        candidate_symbol = str(
            item.get(
                "symbol",
                "",
            )
        ).upper()

        try:

            result = await (
                signal_engine.analyze_symbol(
                    symbol=candidate_symbol,
                    market=clean_market,
                    candle_limit=candle_limit,
                )
            )

            return {
                "success": True,
                "candidate": item,
                "analysis": result,
            }

        except Exception as exc:

            return {
                "success": False,
                "candidate": item,
                "analysis": None,
                "error": str(exc),
            }

    deep_results = await __import__(
        "asyncio"
    ).gather(
        *[
            analyze_candidate(
                item
            )
            for item in candidates
        ],
        return_exceptions=False,
    )

    publishable = []
    ranked = []

    for item in deep_results:

        analysis = item.get(
            "analysis"
        )

        if not isinstance(
            analysis,
            dict,
        ):
            continue

        ranked.append(
            analysis
        )

        if analysis.get(
            "publishable",
            False,
        ):

            publishable.append(
                analysis
            )

    ranked.sort(
        key=lambda x: float(
            x.get(
                "confidence",
                0,
            )
            or 0
        ),
        reverse=True,
    )

    return {
        "success": True,
        "market": clean_market,
        "universe_mode": (
            "FULL_MARKET"
        ),
        "scanned_universe": (
            universe_result.get(
                "eligible_markets",
                0,
            )
        ),
        "candidate_count": len(
            candidates
        ),
        "deep_analyzed": len(
            ranked
        ),
        "publishable_count": len(
            publishable
        ),
        "core_timeframes": list(
            settings.core_timeframes
        ),
        "candidates": candidates,
        "analyses": ranked,
        "publishable_signals": (
            publishable
        ),
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
        "signals": (
            signal_memory.latest(
                limit
            )
        ),
        "stats": (
            signal_memory.stats()
        ),
    }
