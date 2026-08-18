from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.api.trade_routes import router as trade_router
from app.core.config import settings


app = FastAPI(
    title="RR Trader",
    description=(
        "AI-powered Binance Spot and Futures "
        "trading intelligence platform."
    ),
    version=settings.app_version,
)


# =========================================================
# CORS
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# API ROUTES
# =========================================================

app.include_router(
    api_router,
    prefix="/api",
    tags=["RR Trader API"],
)

app.include_router(
    trade_router,
    prefix="/api",
    tags=["Trade Engine"],
)


# =========================================================
# ROOT
# =========================================================

@app.get("/")
async def root() -> dict:
    return {
        "app": settings.app_name,
        "status": "online",
        "version": settings.app_version,
        "markets": [
            "futures",
            "spot",
        ],
        "core_timeframes": list(
            settings.core_timeframes
        ),
        "dashboard": "/dashboard",
        "message": "RR Trader backend is working",
    }


# =========================================================
# DASHBOARD PLACEHOLDER
# =========================================================

@app.get("/dashboard")
async def dashboard() -> dict:
    return {
        "success": True,
        "status": "dashboard_foundation_ready",
        "message": (
            "RR Trader dashboard will be "
            "built in the frontend phase."
        ),
    }
