from __future__ import annotations

from fastapi import FastAPI

from app.api.routes import router as main_router
from app.api.trade_routes import router as trade_router
from app.api.ai_routes import router as ai_router
from app.api.dashboard_routes import router as dashboard_router


# =========================================================
# RR TRADER APPLICATION
# =========================================================

app = FastAPI(
    title="RR Trader Live Crypto Trading Scanner",
    description=(
        "AI-powered crypto market scanner and trading analysis platform."
    ),
    version="1.0.0",
)


# =========================================================
# ROOT
# =========================================================

@app.get("/")
async def root():
    return {
        "success": True,
        "app": "RR Trader",
        "status": "online",
        "version": "1.0.0",
    }


# =========================================================
# HEALTH
# =========================================================

@app.get("/health")
async def health():
    return {
        "success": True,
        "app": "RR Trader",
        "status": "healthy",
    }


# =========================================================
# API ROUTES
# =========================================================

app.include_router(
    main_router,
    prefix="/api",
)


app.include_router(
    trade_router,
    prefix="/api",
)


app.include_router(
    ai_router,
    prefix="/api",
)


app.include_router(
    dashboard_router,
    prefix="/api",
)


# =========================================================
# STARTUP
# =========================================================

@app.on_event("startup")
async def startup_event():

    print(
        "RR Trader backend started successfully."
    )


# =========================================================
# SHUTDOWN
# =========================================================

@app.on_event("shutdown")
async def shutdown_event():

    print(
        "RR Trader backend shutting down."
    )
