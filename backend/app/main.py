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

from app.services.auto_scanner import auto_scanner


# =========================================================
# RR TRADER
# APPLICATION PATHS
# =========================================================

# File:
# backend/app/main.py
#
# parents[0] = backend/app
# parents[1] = backend
# parents[2] = project root

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
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
# FASTAPI APPLICATION
# =========================================================

app = FastAPI(
    title=(
        "RR Trader Live Crypto Trading Scanner"
    ),
    description=(
        "AI-powered cryptocurrency "
        "market scanner and trading "
        "analysis platform."
    ),
    version="2.0.0",
)


# =========================================================
# FRONTEND STATIC FILES
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
        name="frontend-pages",
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
            ),
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
            ),
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
            ),
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
            ),
        ),
        name="frontend-assets",
    )


# =========================================================
# ROOT
# =========================================================

@app.get("/")
async def root():
    """
    Main application entry point.

    Serves the dashboard frontend when available.
    """

    if FRONTEND_INDEX.is_file():

        return FileResponse(
            path=str(
                FRONTEND_INDEX
            ),
            media_type="text/html",
        )

    return {
        "success": False,
        "app": "RR Trader",
        "status": "online",
        "version": "2.0.0",
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
    """
    Dashboard entry point.

    Uses the same frontend index page,
    so the dashboard remains in the
    same application/window.
    """

    if FRONTEND_INDEX.is_file():

        return FileResponse(
            path=str(
                FRONTEND_INDEX
            ),
            media_type="text/html",
        )

    return {
        "success": False,
        "app": "RR Trader",
        "status": "online",
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

    scanner = (
        auto_scanner.snapshot()
    )

    return {
        "success": True,
        "app": "RR Trader",
        "status": "healthy",
        "version": "2.0.0",

        "frontend": {
            "directory_exists":
                FRONTEND_DIR.is_dir(),

            "index_exists":
                FRONTEND_INDEX.is_file(),

            "pages_exists":
                PAGES_DIR.is_dir(),

            "charts_exists":
                CHARTS_DIR.is_dir(),
        },

        "scanner": {
            "running":
                scanner.get(
                    "running",
                    False,
                ),

            "market":
                scanner.get(
                    "market",
                    "futures",
                ),

            "refresh_seconds":
                scanner.get(
                    "refresh_seconds",
                    60,
                ),

            "next_scan_in_seconds":
                scanner.get(
                    "next_scan_in_seconds"
                ),
        },
    }


# =========================================================
# API ROUTERS
# =========================================================

# ---------------------------------------------------------
# Main market / analysis API
# ---------------------------------------------------------

app.include_router(
    main_router,
    prefix="/api",
    tags=[
        "Markets",
    ],
)


# ---------------------------------------------------------
# Trade engine API
# ---------------------------------------------------------

app.include_router(
    trade_router,
    prefix="/api",
    tags=[
        "Trade Engine",
    ],
)


# ---------------------------------------------------------
# AI API
# ---------------------------------------------------------

app.include_router(
    ai_router,
    prefix="/api",
    tags=[
        "AI",
    ],
)


# ---------------------------------------------------------
# Dashboard API
# ---------------------------------------------------------

app.include_router(
    dashboard_router,
    prefix="/api",
    tags=[
        "Dashboard",
    ],
)


# ---------------------------------------------------------
# Scanner API
# ---------------------------------------------------------

app.include_router(
    scanner_router,
    prefix="/api",
    tags=[
        "Scanner",
    ],
)


# =========================================================
# STARTUP
# =========================================================

@app.on_event("startup")
async def startup_event():

    print(
        "========================================"
    )

    print(
        "RR Trader backend starting..."
    )

    print(
        f"Project root: {PROJECT_ROOT}"
    )

    print(
        f"Frontend directory: "
        f"{FRONTEND_DIR}"
    )

    print(
        f"Frontend index exists: "
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
        "Starting automatic Binance Futures scanner..."
    )

    try:

        await auto_scanner.start()

        scanner = (
            auto_scanner.snapshot()
        )

        print(
            "Automatic scanner started successfully."
        )

        print(
            f"Scanner market: "
            f"{scanner.get('market', 'futures')}"
        )

        print(
            "Scanner interval: "
            f"{scanner.get('refresh_seconds', 60)} seconds"
        )

    except Exception as exc:

        print(
            "Scanner startup error:"
        )

        print(
            str(exc)
        )

    print(
        "RR Trader backend startup complete."
    )

    print(
        "========================================"
    )


# =========================================================
# SHUTDOWN
# =========================================================

@app.on_event("shutdown")
async def shutdown_event():

    print(
        "========================================"
    )

    print(
        "Stopping RR Trader auto scanner..."
    )

    try:

        await auto_scanner.stop()

        print(
            "Auto scanner stopped successfully."
        )

    except Exception as exc:

        print(
            "Scanner shutdown error:"
        )

        print(
            str(exc)
        )

    print(
        "RR Trader backend shutting down."
    )

    print(
        "========================================"
    )
