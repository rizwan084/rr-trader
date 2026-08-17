from __future__ import annotations

from fastapi import FastAPI

from app.app.api.routes import router as api_router


app = FastAPI(
    title="RR Trader Live Scanner",
    description="AI-powered Binance Spot and Futures market scanner",
    version="2.0.0",
)


@app.get("/")
async def root():
    return {
        "app": "RR Trader Live Scanner",
        "status": "online",
        "version": "2.0.0",
        "markets": ["futures", "spot"],
        "message": "RR Trader backend is working",
    }


@app.get("/health")
async def health():
    return {
        "success": True,
        "status": "healthy",
        "service": "rr-trader",
    }


app.include_router(
    api_router,
    prefix="/api",
    tags=["RR Trader API"],
)
