from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from app.services.scanner import MarketScanner


router = APIRouter()


def _serialize(value: Any) -> Any:
    """Convert common Python objects into API-safe data."""
    if value is None:
        return None

    if hasattr(value, "model_dump"):
        return value.model_dump()

    if hasattr(value, "dict"):
        return value.dict()

    if isinstance(value, dict):
        return {str(k): _serialize(v) for k, v in value.items()}

    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value]

    return value


def _run_scanner(
    symbol: Optional[str] = None,
    market: str = "futures",
) -> Any:
    """
    Run the RR Trader market scanner.

    Supports both Binance Futures and Binance Spot.
    """

    scanner = MarketScanner()

    # Prefer a symbol-specific scan when available.
    if symbol:
        for method_name in (
            "scan_symbol",
            "analyze_symbol",
            "scan_market",
            "analyze",
            "scan",
        ):
            method = getattr(scanner, method_name, None)

            if callable(method):
                try:
                    return method(
                        symbol=symbol.upper(),
                        market=market.lower(),
                    )
                except TypeError:
                    try:
                        return method(
                            symbol.upper(),
                            market.lower(),
                        )
                    except TypeError:
                        continue

    # Otherwise run the general market scanner.
    for method_name in (
        "scan",
        "scan_market",
        "scan_markets",
        "run",
        "execute",
    ):
        method = getattr(scanner, method_name, None)

        if callable(method):
            try:
                return method(market=market.lower())
            except TypeError:
                try:
                    return method(market.lower())
                except TypeError:
                    return method()

    raise RuntimeError(
        "MarketScanner does not expose a supported scan method."
    )


@router.get("/")
async def api_root() -> dict[str, Any]:
    """RR Trader API information."""
    return {
        "app": "RR Trader",
        "status": "online",
        "version": "1.0",
        "markets": ["futures", "spot"],
        "message": "RR Trader API is running",
    }


@router.get("/health")
async def health() -> dict[str, Any]:
    """Health check endpoint."""
    return {
        "success": True,
        "status": "healthy",
        "service": "rr-trader-api",
    }


@router.get("/scan")
async def scan_market(
    market: str = Query(
        default="futures",
        description="Binance market: futures or spot",
    ),
    symbol: Optional[str] = Query(
        default=None,
        description="Optional symbol, for example BTCUSDT",
    ),
) -> dict[str, Any]:
    """
    Scan Binance market data.

    Examples:
    /api/scan?market=futures
    /api/scan?market=spot
    /api/scan?market=futures&symbol=BTCUSDT
    """

    market = market.lower().strip()

    if market not in {"futures", "spot"}:
        raise HTTPException(
            status_code=400,
            detail="market must be either 'futures' or 'spot'",
        )

    if symbol:
        symbol = symbol.upper().replace("/", "").strip()

    try:
        result = _run_scanner(
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
            detail=f"Scanner error: {str(exc)}",
        ) from exc


@router.get("/analyze")
async def analyze_symbol(
    symbol: str = Query(
        ...,
        description="Trading symbol, for example BTCUSDT",
    ),
    market: str = Query(
        default="futures",
        description="Binance market: futures or spot",
    ),
) -> dict[str, Any]:
    """
    Analyze a single coin on the selected Binance market.
    """

    market = market.lower().strip()
    symbol = symbol.upper().replace("/", "").strip()

    if market not in {"futures", "spot"}:
        raise HTTPException(
            status_code=400,
            detail="market must be either 'futures' or 'spot'",
        )

    if not symbol.endswith("USDT"):
        raise HTTPException(
            status_code=400,
            detail="Only USDT trading pairs are currently supported.",
        )

    try:
        result = _run_scanner(
            symbol=symbol,
            market=market,
        )

        return {
            "success": True,
            "symbol": symbol,
            "market": market,
            "data": _serialize(result),
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Analysis error: {str(exc)}",
        ) from exc


@router.get("/markets")
async def supported_markets() -> dict[str, Any]:
    """Return supported Binance markets."""
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
