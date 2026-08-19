rom __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.services.liquidation_engine import liquidation_engine


router = APIRouter(
    prefix="/liquidation",
    tags=["Liquidation Intelligence"],
)


@router.get("/status")
async def liquidation_status() -> dict[str, Any]:
    return {
        "success": True,
        "service": "RR Liquidation Intelligence",
        **liquidation_engine.snapshot(),
    }


@router.get("/heatmap")
async def liquidation_heatmap(
    symbol: str = Query(
        default="BTCUSDT",
        min_length=2,
        max_length=30,
    ),
    current_price: float = Query(
        default=0.0,
        ge=0.0,
    ),
    hours: int = Query(
        default=24,
        ge=1,
        le=72,
    ),
    bins: int = Query(
        default=80,
        ge=20,
        le=160,
    ),
) -> dict[str, Any]:

    try:
        clean_symbol = liquidation_engine.normalize_symbol(
            symbol
        )

        if not liquidation_engine.snapshot()["running"]:
            await liquidation_engine.start()

        result = await liquidation_engine.analyze(
            symbol=clean_symbol,
            current_price=current_price,
            hours=hours,
            bin_count=bins,
        )

        return result

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Liquidation heatmap failed: {exc}",
        ) from exc
