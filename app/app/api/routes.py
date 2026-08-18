from typing import Dict

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from app.app.services.scanner import MarketScanner


router = APIRouter()


# =========================================================
# SERIALIZER
# =========================================================

def _serialize(value: Any) -> Any:
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
# MARKET / SYMBOL HELPERS
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


def _normalize_symbol(
    symbol: str,
) -> str:
    """
    Accept either:
        BTC
        BTCUSDT
        BTC/USDT
        BTC-USDT

    and normalize to:
        BTCUSDT
    """

    cleaned = (
        symbol
        .upper()
        .replace("/", "")
        .replace("-", "")
        .strip()
    )

    if not cleaned:
        raise HTTPException(
            status_code=400,
            detail="Symbol is required.",
        )

    if not cleaned.endswith("USDT"):
        cleaned = (
            f"{cleaned}USDT"
        )

    return cleaned


# =========================================================
# SCANNER RUNNER
# =========================================================

async def _run_scanner(
    symbol: Optional[str] = None,
    market: str = "futures",
    max_candidates: Optional[int] = None,
) -> Any:

    market = _validate_market(
        market
    )

    scanner = MarketScanner()

    if symbol:

        symbol = _normalize_symbol(
            symbol
        )

        return await scanner.scan_symbol(
            symbol=symbol,
            market=market,
        )

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

    return await scanner.scan(
        market=market,
        max_candidates=safe_max_candidates,
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
        "version": "4.0.0",
        "markets": [
            "futures",
            "spot",
        ],
        "timeframes": [
            "5m",
            "15m",
            "1h",
            "4h",
        ],
        "endpoints": [
            "/api/health",
            "/api/markets",
            "/api/scan",
            "/api/analyze",
            "/api/signals",
            "/api/search",
            "/api/auto/status",
            "/api/auto/signals",
            "/api/auto/candidates",
        ],
        "message": (
            "RR Trader API is running"
        ),
    }


# =========================================================
# HEALTH
# =========================================================

@router.get("/health")
async def health() -> dict[str, Any]:

    return {
        "success": True,
        "status": "healthy",
        "service": "rr-trader-api",
    }


# =========================================================
# MARKETS
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
# SCAN
# =========================================================

@router.get("/scan")
async def scan_market(
    market: str = Query(
        default="futures",
    ),
    symbol: Optional[str] = Query(
        default=None,
    ),
    max_candidates: int = Query(
        default=5,
        ge=1,
        le=5,
    ),
) -> dict[str, Any]:

    market = _validate_market(
        market
    )

    normalized_symbol = None

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
# ANALYZE
# =========================================================

@router.get("/analyze")
async def analyze_symbol(
    symbol: str = Query(
        ...,
        description=(
            "Coin name or USDT pair, "
            "for example BTC or BTCUSDT"
        ),
    ),
    market: str = Query(
        default="futures",
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
            "coin": symbol[:-4],
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
# HIGH CONFIDENCE SIGNALS
# =========================================================

@router.get("/signals")
async def high_confidence_signals(
    market: str = Query(
        default="futures",
    ),
    min_confidence: float = Query(
        default=90.0,
        ge=0.0,
        le=100.0,
    ),
    max_candidates: int = Query(
        default=5,
        ge=1,
        le=5,
    ),
) -> dict[str, Any]:

    market = _validate_market(
        market
    )

    try:

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

        signals: list[
            Dict[str, Any]
        ] = []

        for item in candidates:

            if not isinstance(
                item,
                dict,
            ):
                continue

            if not item.get(
                "success",
                False,
            ):
                continue

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

            direction = item.get(
                "direction",
                "NEUTRAL",
            )

            if (
                confidence >= min_confidence
                and direction in {
                    "LONG",
                    "SHORT",
                }
            ):

                enriched = dict(
                    item
                )

                if (
                    "coin"
                    not in enriched
                ):

                    enriched[
                        "coin"
                    ] = str(
                        enriched.get(
                            "symbol",
                            "",
                        )
                    ).removesuffix(
                        "USDT"
                    )

                signals.append(
                    enriched
                )

        signals.sort(
            key=lambda item: float(
                item.get(
                    "confidence",
                    0,
                )
            ),
            reverse=True,
        )

        return {
            "success": True,
            "market": market,
            "min_confidence": min_confidence,
            "requested_candidates": max_candidates,
            "safe_max_candidates": 5,
            "scanned": len(
                candidates
            ),
            "signals_count": len(
                signals
            ),
            "signals_90_plus": sum(
                1
                for item in signals
                if float(
                    item.get(
                        "confidence",
                        0,
                    )
                ) >= 90
            ),
            "signals_95_plus": sum(
                1
                for item in signals
                if float(
                    item.get(
                        "confidence",
                        0,
                    )
                ) >= 95
            ),
            "signals_99_plus": sum(
                1
                for item in signals
                if float(
                    item.get(
                        "confidence",
                        0,
                    )
                ) >= 99
            ),
            "signals": _serialize(
                signals
            ),
            "top_signals": _serialize(
                signals[:5]
            ),
        }

    except HTTPException:
        raise

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=(
                f"Signal scan error: {str(exc)}"
            ),
        ) from exc


__all__ = [
    "router",
]
