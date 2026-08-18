from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as main_router
from app.api.trade_routes import router as trade_router
from app.api.ai_routes import router as ai_router
from app.api.dashboard_routes import router as dashboard_router
from app.api.scanner_routes import router as scanner_router

from app.services.auto_scanner import (
    auto_scanner,
)


# =========================================================
# PROJECT PATHS
# =========================================================

PROJECT_ROOT = (
    Path(__file__).resolve().parents[2]
)

FRONTEND_DIR = (
    PROJECT_ROOT / "frontend"
)

FRONTEND_INDEX = (
    FRONTEND_DIR / "index.html"
)

PAGES_DIR = (
    FRONTEND_DIR / "pages"
)

SERVICES_DIR = (
    FRONTEND_DIR / "services"
)

CHARTS_DIR = (
    FRONTEND_DIR / "charts"
)

COMPONENTS_DIR = (
    FRONTEND_DIR / "components"
)

ASSETS_DIR = (
    FRONTEND_DIR / "assets"
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
    version="2.0.0",
)


# =========================================================
# STATIC FILES
# =========================================================

# ---------------------------------------------------------
# HTML pages
# ---------------------------------------------------------

if PAGES_DIR.is_dir():

    app.mount(
        "/pages",
        StaticFiles(
            directory=str(
                PAGES_DIR
            ),
            html=True,
        ),
        name="pages",
    )


# ---------------------------------------------------------
# Frontend services
# ---------------------------------------------------------

if SERVICES_DIR.is_dir():

    app.mount(
        "/frontend-services",
        StaticFiles(
            directory=str(
                SERVICES_DIR
            )
        ),
        name="frontend-services",
    )


# ---------------------------------------------------------
# Frontend chart assets
# ---------------------------------------------------------

if CHARTS_DIR.is_dir():

    app.mount(
        "/frontend-charts",
        StaticFiles(
            directory=str(
                CHARTS_DIR
            )
        ),
        name="frontend-charts",
    )


# ---------------------------------------------------------
# Frontend components
# ---------------------------------------------------------

if COMPONENTS_DIR.is_dir():

    app.mount(
        "/frontend-components",
        StaticFiles(
            directory=str(
                COMPONENTS_DIR
            )
        ),
        name="frontend-components",
    )


# ---------------------------------------------------------
# General assets
# ---------------------------------------------------------

if ASSETS_DIR.is_dir():

    app.mount(
        "/assets",
        StaticFiles(
            directory=str(
                ASSETS_DIR
            )
        ),
        name="assets",
    )


# =========================================================
# ROOT
# =========================================================

@app.get("/")
async def root():

    if FRONTEND_INDEX.is_file():

        return FileResponse(
            path=str(
                FRONTEND_INDEX
            ),
            media_type="text/html",
        )

    return {
        "success": False,
        "error": (
            "Dashboard frontend not found."
        ),
        "frontend_path": str(
            FRONTEND_INDEX
        ),
    }


# =========================================================
# DASHBOARD
# =========================================================

@app.get("/dashboard")
async def dashboard():

    if FRONTEND_INDEX.is_file():

        return FileResponse(
            path=str(
                FRONTEND_INDEX
            ),
            media_type="text/html",
        )

    return {
        "success": False,
        "error": (
            "Dashboard frontend not found."
        ),
        "frontend_path": str(
            FRONTEND_INDEX
        ),
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
        "version": "2.0.0",
        "auto_scanner": (
            auto_scanner.snapshot()
        ),
    }


# =========================================================
# API ROUTERS
# =========================================================

# Main market / analysis API
app.include_router(
    main_router,
    prefix="/api",
)


# Trade / risk API
app.include_router(
    trade_router,
    prefix="/api",
)


# AI API
app.include_router(
    ai_router,
    prefix="/api",
)


# Dashboard API
app.include_router(
    dashboard_router,
    prefix="/api",
)


# Scanner API
app.include_router(
    scanner_router,
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

    print(
        f"Project root: {PROJECT_ROOT}"
    )

    print(
        f"Frontend exists: "
        f"{FRONTEND_INDEX.is_file()}"
    )

    print(
        f"Pages directory exists: "
        f"{PAGES_DIR.is_dir()}"
    )

    print(
        f"Charts directory exists: "
        f"{CHARTS_DIR.is_dir()}"
    )

    print(
        "Starting RR Trader auto scanner..."
    )

    await auto_scanner.start()

    print(
        "RR Trader auto scanner started."
    )


# =========================================================
# SHUTDOWN
# =========================================================

@app.on_event("shutdown")
async def shutdown_event():

    print(
        "Stopping RR Trader auto scanner..."
    )

    await auto_scanner.stop()

    print(
        "RR Trader auto scanner stopped."
    )

    print(
        "RR Trader backend shutting down."
    )
