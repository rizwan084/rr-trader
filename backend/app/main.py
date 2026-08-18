from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.api.routes import router as main_router
from app.api.trade_routes import router as trade_router
from app.api.ai_routes import router as ai_router
from app.api.dashboard_routes import router as dashboard_router


# =========================================================
# PATHS
# =========================================================

BACKEND_DIR = Path(
    __file__
).resolve().parents[2]

PROJECT_ROOT = (
    BACKEND_DIR.parent
)

FRONTEND_DIR = (
    PROJECT_ROOT / "frontend"
)

FRONTEND_INDEX = (
    FRONTEND_DIR / "index.html"
)


# =========================================================
# APPLICATION
# =========================================================

app = FastAPI(
    title="RR Trader Live Crypto Trading Scanner",
    description=(
        "AI-powered crypto market scanner "
        "and trading analysis platform."
    ),
    version="1.0.0",
)


# =========================================================
# ROOT
# =========================================================

@app.get("/")
async def root():

    if FRONTEND_INDEX.exists():

        return FileResponse(
            FRONTEND_INDEX
        )

    return {
        "success": True,
        "app": "RR Trader",
        "status": "online",
        "version": "1.0.0",
    }


# =========================================================
# DASHBOARD
# =========================================================

@app.get("/dashboard")
async def dashboard():

    if FRONTEND_INDEX.exists():

        return FileResponse(
            FRONTEND_INDEX
        )

    return {
        "success": False,
        "error": "Dashboard frontend not found.",
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
        "version": "1.0.0",
    }


# =========================================================
# API ROUTERS
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

@app.on_event(
    "startup"
)
async def startup_event():

    print(
        "RR Trader backend started successfully."
    )

    print(
        f"Frontend directory: {FRONTEND_DIR}"
    )

    print(
        f"Dashboard index: {FRONTEND_INDEX}"
    )


# =========================================================
# SHUTDOWN
# =========================================================

@app.on_event(
    "shutdown"
)
async def shutdown_event():

    print(
        "RR Trader backend shutting down."
    )
