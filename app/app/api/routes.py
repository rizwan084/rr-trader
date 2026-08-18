from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from app.app.services.scanner import MarketScanner


router = APIRouter()


# =========================================================
# SERIALIZER
# =========================================================

def _serialize(value: Any) -> Any:
    """
    Convert Pydantic models, dictionaries, lists and tuples
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
# MARKET VALIDATION
# =========================================================

def _validate_market(
    market: str,
) -> str:

    market = (
        market
        .lower()
        .strip()
    )

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

    return market


# =========================================================
# SYMBOL NORMALIZATION
# =========================================================

def _normalize_symbol(
    symbol: str,
) -> str:

    symbol = (
        symbol
        .upper()
        .replace("/", "")
        .replace("-", "")
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

    return symbol


# =========================================================
# SCANNER RUNNER
# =========================================================

async def _run_scanner(
    symbol: Optional[str] = None,
    market: str = "futures",
    max_candidates: Optional[int] = None,
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

    market = _validate_market(
        market
    )

    # -----------------------------------------------------
    # SINGLE SYMBOL ANALYSIS
    # -----------------------------------------------------

    if symbol:

        symbol = _normalize_symbol(
            symbol
        )

        result = await scanner.scan_symbol(
            symbol=symbol,
            market=market,
        )

        return result

    # -----------------------------------------------------
    # GENERAL MARKET SCAN
    # -----------------------------------------------------

    # -----------------------------------------------------
    # IMPORTANT MEMORY PROTECTION
    #
    # Render has previously killed the process with
    # status 137 when too much scanning work was requested.
    #
    # The scanner is now limited to a maximum of 5 symbols
    # through the API layer.
    # -----------------------------------------------------

    safe_max_candidates = (
        5
        if max_candidates is None
        else max(
            1,
            min(
                int(max_candidates),
                5,
            ),
        )
    )

    result = await scanner.scan(
        market=market,
        max_candidates=safe_max_candidates,
    )

    return result


# =========================================================
# API ROOT
# =========================================================

@router.get("/")
async def api_root() -> dict[str, Any]:

    return {
        "success": True,
        "app": "RR Trader",
        "status": "online",
        "version": "2.1.0",
        "markets": [
            "futures",
            "spot",
        ],
        "endpoints": [
            "/api/health",
            "/api/markets",
            "/api/scan",
            "/api/analyze",
            "/api/signals",
        ],
        "timeframes": [
            "5m",
            "15m",
            "1h",
            "4h",
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
    max_candidates: int = Query(
        default=5,
        ge=1,
        le=5,
        description=(
            "Maximum number of coins to scan. "
            "Hard limited to 5 for Render memory safety."
        ),
    ),
) -> dict[str, Any]:

    market = _validate_market(
        market
    )

    normalized_symbol: Optional[str] = None

    if symbol:
        normalized_symbol = (
            _normalize_symbol(
                symbol
            )
        )

    try:

        result = await _run_scanner(
            symbol=normalized_symbol,
            market=market,
            max_candidates=(
                max_candidates
                if normalized_symbol is None
                else None
            ),
        )

        return {
            "success": True,
            "market": market,
            "symbol": normalized_symbol,
            "data": _serialize(
                result
            ),
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

    market = _validate_market(
        market
    )

    symbol = _normalize_symbol(
        symbol
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
            "data": _serialize(
                result
            ),
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


# =========================================================
# HIGH-CONFIDENCE SIGNALS
# =========================================================

@router.get("/signals")
async def high_confidence_signals(
    market: str = Query(
        default="futures",
        description=(
            "Binance market: futures or spot"
        ),
    ),
    min_confidence: float = Query(
        default=90.0,
        ge=0.0,
        le=100.0,
        description=(
            "Minimum confidence percentage."
        ),
    ),
    max_candidates: int = Query(
        default=5,
        ge=1,
        le=5,
        description=(
            "Maximum coins to scan. "
            "Hard limited to 5 for memory safety."
        ),
) -> dict[str, Any]:

    market = _validate_market(
        market
    )

    try:

        # -----------------------------------------------------
        # Run a memory-safe market scan.
        #
        # Even if the frontend sends 30, the API never allows
        # more than 5 candidates in one request.
        # -----------------------------------------------------

        result = await _run_scanner(
            market=market,
            max_candidates=max_candidates,
        )

        if not isinstance(
            result,
            dict,
        ):
            raise RuntimeError(
                "Scanner returned an invalid response."
            )

        candidates = result.get(
            "candidates",
            [],
        )

        if not isinstance(
            candidates,
            list,
        ):
            candidates = []

        # -----------------------------------------------------
        # Filter by requested confidence.
        # -----------------------------------------------------

        filtered = []

        for item in candidates:

            if not isinstance(
                item,
                dict,
            ):
                continue

            confidence = 0.0

            try:
                confidence = float(
                    item.get(
                        "confidence",
                        0,
                    )
                )
            except (
                TypeError,
                ValueError,
            ):
                confidence = 0.0

            if confidence >= min_confidence:

                filtered.append(
                    item
                )

        # -----------------------------------------------------
        # Sort strongest signals first.
        # -----------------------------------------------------

        filtered.sort(
            key=lambda item: float(
                item.get(
                    "confidence",
                    0,
                )
            ),
            reverse=True,
        )

        # -----------------------------------------------------
        # Separate LONG and SHORT.
        # -----------------------------------------------------

        long_signals = [
            item
            for item in filtered
            if item.get(
                "direction"
            ) == "LONG"
        ]

        short_signals = [
            item
            for item in filtered
            if item.get(
                "direction"
            ) == "SHORT"
        ]

        # -----------------------------------------------------
        # Count confidence tiers.
        # -----------------------------------------------------

        signals_90_plus = [
            item
            for item in filtered
            if float(
                item.get(
                    "confidence",
                    0,
                )
            ) >= 90
        ]

        signals_95_plus = [
            item
            for item in filtered
            if float(
                item.get(
                    "confidence",
                    0,
                )
            ) >= 95
        ]

        signals_99_plus = [
            item
            for item in filtered
            if float(
                item.get(
                    "confidence",
                    0,
                )
            ) >= 99
        ]

        return {
            "success": True,
            "market": market,
            "min_confidence": (
                min_confidence
            ),
            "requested_candidates": (
                max_candidates
            ),
            "safe_max_candidates": 5,
            "scanned": len(
                candidates
            ),
            "signals_found": len(
                filtered
            ),
            "signals_90_plus": len(
                signals_90_plus
            ),
            "signals_95_plus": len(
                signals_95_plus
            ),
            "signals_99_plus": len(
                signals_99_plus
            ),
            "long_signals": len(
                long_signals
            ),
            "short_signals": len(
                short_signals
            ),
            "signals": _serialize(
                filtered
            ),
            "top_signals": _serialize(
                filtered[
                    :5
                ]
            ),
        }

    except HTTPException:
        raise

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=(
                f"Signal scan error: "
                f"{str(exc)}"
            ),
        ) from exc


# =========================================================
# API EXPORT
# =========================================================

__all__ = [
    "router",
]
