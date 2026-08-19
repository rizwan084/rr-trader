from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as main_router
from app.api.trade_routes import router as trade_router
from app.api.ai_routes import router as ai_router
from app.api.dashboard_routes import router as dashboard_router
from app.api.scanner_routes import router as scanner_router
from app.api.liquidation_routes import (
    router as liquidation_router,
)

from app.services.auto_scanner import auto_scanner
from app.services.liquidation_engine import (
    liquidation_engine,
)


# =========================================================
# PROJECT PATHS
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

FRONTEND_DIR = PROJECT_ROOT / "frontend"
FRONTEND_INDEX = FRONTEND_DIR / "index.html"

PAGES_DIR = FRONTEND_DIR / "pages"
SERVICES_DIR = FRONTEND_DIR / "services"
CHARTS_DIR = FRONTEND_DIR / "charts"
COMPONENTS_DIR = FRONTEND_DIR / "components"
ASSETS_DIR = FRONTEND_DIR / "assets"


# =========================================================
# APPLICATION
# =========================================================

app = FastAPI(
    title="RR Trader Live Crypto Trading Scanner",
    description=(
        "AI-powered crypto market scanner, "
        "multi-exchange analysis and "
        "liquidation intelligence platform."
    ),
    version="2.2.0",
)


# =========================================================
# FRONTEND STATIC FILES
# =========================================================

if PAGES_DIR.is_dir():

    app.mount(
        "/pages",
        StaticFiles(
            directory=str(PAGES_DIR),
            html=True,
        ),
        name="pages",
    )


if SERVICES_DIR.is_dir():

    app.mount(
        "/frontend-services",
        StaticFiles(
            directory=str(SERVICES_DIR),
        ),
        name="frontend-services",
    )


if CHARTS_DIR.is_dir():

    app.mount(
        "/frontend-charts",
        StaticFiles(
            directory=str(CHARTS_DIR),
        ),
        name="frontend-charts",
    )


if COMPONENTS_DIR.is_dir():

    app.mount(
        "/frontend-components",
        StaticFiles(
            directory=str(COMPONENTS_DIR),
        ),
        name="frontend-components",
    )


if ASSETS_DIR.is_dir():

    app.mount(
        "/assets",
        StaticFiles(
            directory=str(ASSETS_DIR),
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
            str(FRONTEND_INDEX),
            media_type="text/html",
        )

    return {
        "success": False,
        "error": "Dashboard frontend not found.",
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
            str(FRONTEND_INDEX),
            media_type="text/html",
        )

    return {
        "success": False,
        "error": "Dashboard frontend not found.",
        "frontend_path": str(
            FRONTEND_INDEX
        ),
    }


# =========================================================
# HEALTH
# =========================================================

@app.get("/health")
async def health():

    scanner_state: dict[str, Any] = {}
    liquidation_state: dict[str, Any] = {}

    # -----------------------------------------------------
    # Scanner status
    # -----------------------------------------------------

    try:

        scanner_state = (
            auto_scanner.snapshot()
        )

    except Exception as exc:

        scanner_state = {
            "running": False,
            "error": str(exc),
        }

    # -----------------------------------------------------
    # Liquidation engine status
    # -----------------------------------------------------

    try:

        liquidation_state = (
            liquidation_engine.snapshot()
        )

    except Exception as exc:

        liquidation_state = {
            "running": False,
            "error": str(exc),
        }

    # -----------------------------------------------------
    # Response
    # -----------------------------------------------------

    return {
        "success": True,
        "app": "RR Trader",
        "status": "healthy",
        "version": "2.2.0",

        "frontend": {
            "directory_exists": (
                FRONTEND_DIR.is_dir()
            ),
            "index_exists": (
                FRONTEND_INDEX.is_file()
            ),
            "pages_exists": (
                PAGES_DIR.is_dir()
            ),
            "charts_exists": (
                CHARTS_DIR.is_dir()
            ),
        },

        "scanner": scanner_state,

        "liquidation_engine": (
            liquidation_state
        ),
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
    tags=["Markets"],
)


# ---------------------------------------------------------
# Trade / risk API
# ---------------------------------------------------------

app.include_router(
    trade_router,
    prefix="/api",
    tags=["Trade Engine"],
)


# ---------------------------------------------------------
# AI API
# ---------------------------------------------------------

app.include_router(
    ai_router,
    prefix="/api",
    tags=["AI"],
)


# ---------------------------------------------------------
# Dashboard API
# ---------------------------------------------------------

app.include_router(
    dashboard_router,
    prefix="/api",
    tags=["Dashboard"],
)


# ---------------------------------------------------------
# Scanner API
# ---------------------------------------------------------

app.include_router(
    scanner_router,
    prefix="/api",
    tags=["Scanner"],
)


# ---------------------------------------------------------
# Liquidation Intelligence API
# ---------------------------------------------------------

app.include_router(
    liquidation_router,
    prefix="/api",
    tags=["Liquidation Intelligence"],
)


# =========================================================
# STARTUP
# =========================================================

@app.on_event("startup")
async def startup_event():

    print("=" * 70)
    print("RR TRADER STARTING")
    print("=" * 70)

    print(
        f"Project root: {PROJECT_ROOT}"
    )

    print(
        "Frontend directory:",
        FRONTEND_DIR.is_dir(),
    )

    print(
        "Frontend index:",
        FRONTEND_INDEX.is_file(),
    )

    print(
        "Pages directory:",
        PAGES_DIR.is_dir(),
    )

    print(
        "Charts directory:",
        CHARTS_DIR.is_dir(),
    )

    # =====================================================
    # AUTO MARKET SCANNER
    # =====================================================

    try:

        await auto_scanner.start()

        print(
            "RR Trader automatic scanner started."
        )

        print(
            "Scanner refresh: 60 seconds."
        )

    except Exception as exc:

        print(
            "Scanner startup warning:",
            exc,
        )

    # =====================================================
    # LIQUIDATION INTELLIGENCE ENGINE
    # =====================================================

    try:

        await liquidation_engine.start()

        print(
            "RR Liquidation Intelligence Engine started."
        )

        print(
            "Liquidation providers:"
        )

        print(
            "  - Binance"
        )

        print(
            "  - Bitget"
        )

        print(
            "  - OKX"
        )

        print(
            "  - MEXC estimated mode"
        )

    except Exception as exc:

        print(
            "Liquidation engine startup warning:",
            exc,
        )

    # =====================================================
    # FINAL STATUS
    # =====================================================

    print("=" * 70)
    print("RR TRADER BACKEND READY")
    print("=" * 70)


# =========================================================
# SHUTDOWN
# =========================================================

@app.on_event("shutdown")
async def shutdown_event():

    print("=" * 70)
    print("RR TRADER SHUTDOWN")
    print("=" * 70)

    # =====================================================
    # STOP AUTO SCANNER
    # =====================================================

    try:

        await auto_scanner.stop()

        print(
            "RR Trader scanner stopped."
        )

    except Exception as exc:

        print(
            "Scanner shutdown warning:",
            exc,
        )

    # =====================================================
    # STOP LIQUIDATION ENGINE
    # =====================================================

    try:

        await liquidation_engine.stop()

        print(
            "RR Liquidation Intelligence Engine stopped."
        )

    except Exception as exc:

        print(
            "Liquidation engine shutdown warning:",
            exc,
        )

    print(
        "RR Trader backend stopped."
    )

    print("=" * 70)
