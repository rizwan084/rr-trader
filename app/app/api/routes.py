from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

# IMPORTANT:
# Project structure:
# app/
#   app/
#     services/
#       scanner.py
#
# Therefore the correct import is:
from app.app.services.scanner import MarketScanner


router = APIRouter()


# =========================================================
# SERIALIZER
# =========================================================

def _serialize(value: Any) -> Any:
    """
    Convert Pydantic models, dictionaries and lists
    into JSON-compatible data.
    """

    if value is None:
        return None

    if hasattr(value, "model_dump"):
        return value.model_dump()

    if hasattr(value, "dict"):
        return value.dict()

    if isinstance(value, dict):
        return {
            str(key): _serialize(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [
            _serialize(item)
            for item in value
        ]

    return value


# =========================================================
# SCANNER RUNNER
# =========================================================

async def _run_scanner(
    symbol: Optional[str] = None,
    market: str = "futures",
) -> Any:
    """
    Run RR Trader MarketScanner.

    Supports:
    - Binance Futures
    - Binance Spot
    - Symbol analysis
    - General market scanning
    """

    scanner = MarketScanner()

    market = market.lower().strip()

    # -----------------------------------------------------
    # SYMBOL ANALYSIS
    # -----------------------------------------------------

    if symbol:

        symbol = (
            symbol
            .upper()
            .replace("/", "")
            .strip()
        )

        symbol_methods = (
            "scan_symbol",
            "analyze_symbol",
            "scan_market",
            "analyze",
        )

        for method_name in symbol_methods:

            method = getattr(
                scanner,
                method_name,
                None,
            )

            if not callable(method):
                continue

            # Try keyword arguments first
            try:

                result = method(
                    symbol=symbol,
                    market=market,
                )

                if hasattr(
                    result,
                    "__await__",
                ):
                    result = await result

                return result

            except TypeError:
                pass

            # Try positional arguments
            try:

                result = method(
                    symbol,
                    market,
                )

                if hasattr(
                    result,
                    "__await__",
                ):
                    result = await result

                return result

            except TypeError:
                continue

    # -----------------------------------------------------
    # GENERAL MARKET SCAN
    # -----------------------------------------------------

    scan_methods = (
        "scan",
        "scan_market",
        "scan_markets",
        "run",
        "execute",
    )

    for method_name in scan_methods:

        method = getattr(
            scanner,
            method_name,
            None,
        )

        if not callable(method):
            continue

        # Try keyword market
        try:

            result = method(
                market=market,
            )

            if hasattr(
                result,
                "__await__",
            ):
                result = await result

            return result

        except TypeError:
            pass

        # Try positional market
        try:

            result = method(
                market,
            )

            if hasattr(
                result,
                "__await__",
            ):
                result = await result

            return result

        except TypeError:
            pass

        # Try without arguments
        try:

            result = method()

            if hasattr(
                result,
                "__await__",
            ):
                result = await result

            return result

        except TypeError:
            continue

    raise RuntimeError(
        "MarketScanner does not expose a supported scan method."
    )


# =========================================================
# API ROOT
# =========================================================

@router.get("/")
async def api_root() -> dict[str, Any]:

    return {
        "success": True,
        "app": "RR Trader",
        "status": "online",
        "version": "2.0.0",
        "markets": [
            "futures",
            "spot",
        ],
        "endpoints": [
            "/api/health",
            "/api/markets",
            "/api/scan",
            "/api/analyze",
        ],
        "message": "RR Trader API is running",
    }


# =========================================================
# API HEALTH
# =========================================================

@router.get("/health")
async def health() -> dict[str, Any]:

    return {
        "success": True,
        "status": "healthy",
        "service": "rr-trader-api",
    }


# =========================================================
# SUPPORTED MARKETS
# =========================================================

@router.get("/markets")
async def supported_markets() -> dict[str, Any]:

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
# MARKET SCAN
# =========================================================

@router.get("/scan")
async def scan_market(
    market: str = Query(
        default="futures",
        description=(
            "Binance market: futures or spot"
        ),
    ),
    symbol: Optional[str] = Query(
        default=None,
        description=(
            "Optional symbol, for example BTCUSDT"
        ),
    ),
) -> dict[str, Any]:

    market = market.lower().strip()

    if market not in {
        "futures",
        "spot",
    }:

        raise HTTPException(
            status_code=400,
            detail=(
                "market must be either "
                "'futures' or 'spot'"
            ),
        )

    if symbol:

        symbol = (
            symbol
            .upper()
            .replace("/", "")
            .strip()
        )

        if not symbol.endswith("USDT"):

            raise HTTPException(
                status_code=400,
                detail=(
                    "Only USDT trading pairs "
                    "are currently supported."
                ),
            )

    try:

        result = await _run_scanner(
            symbol=symbol,
            market=market,
        )

        return {
            "success": True,
            "market": market,
            "symbol": symbol,
            "data": _serialize(result),
        }

    except HTTPException:
        raise

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=(
                f"Scanner error: {str(exc)}"
            ),
        ) from exc


# =========================================================
# SYMBOL ANALYSIS
# =========================================================

@router.get("/analyze")
async def analyze_symbol(
    symbol: str = Query(
        ...,
        description=(
            "Trading symbol, for example BTCUSDT"
        ),
    ),
    market: str = Query(
        default="futures",
        description=(
            "Binance market: futures or spot"
        ),
    ),
) -> dict[str, Any]:

    market = market.lower().strip()

    symbol = (
        symbol
        .upper()
        .replace("/", "")
        .strip()
    )

    # Validate market
    if market not in {
        "futures",
        "spot",
    }:

        raise HTTPException(
            status_code=400,
            detail=(
                "market must be either "
                "'futures' or 'spot'"
            ),
        )

    # Validate symbol
    if not symbol.endswith("USDT"):

        raise HTTPException(
            status_code=400,
            detail=(
                "Only USDT trading pairs "
                "are currently supported."
            ),
        )

    try:

        result = await _run_scanner(
            symbol=symbol,
            market=market,
        )

        return {
            "success": True,
            "symbol": symbol,
            "market": market,
            "data": _serialize(result),
        }

    except HTTPException:
        raise

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=(
                f"Analysis error: {str(exc)}"
            ),
        ) from exc


__all__ = [
    "router",
]
