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
from app.api.liquidation_routes import router as liquidation_router

from app.services.auto_scanner import auto_scanner


# =========================================================
# RR TRADER APPLICATION CONFIGURATION
# =========================================================

APP_VERSION = "2.3.0"

STRATEGY_MODE = "SETUP_QUALITY"

MINIMUM_CONFIDENCE = 85.0

MIN_SUPPORT_TOUCHES = 2
MIN_RESISTANCE_TOUCHES = 2

PRIMARY_SETUP_TYPES = (
    "SUPPORT_BOUNCE",
    "RESISTANCE_REJECTION",
)

CORE_TIMEFRAMES = (
    "15m",
    "1h",
    "4h",
)

SCANNER_REFRESH_SECONDS = 60


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
        "AI-powered crypto market scanner "
        "with multi-exchange analysis, "
        "market-structure intelligence, "
        "support/resistance setup detection "
        "and liquidation intelligence."
    ),
    version=APP_VERSION,
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
        "frontend_path": str(FRONTEND_INDEX),
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
        "frontend_path": str(FRONTEND_INDEX),
    }


# =========================================================
# STRATEGY CONFIGURATION
# =========================================================

@app.get("/api/strategy/config")
async def strategy_config():

    return {
        "success": True,
        "version": APP_VERSION,
        "strategy_mode": STRATEGY_MODE,

        "signal_policy": {
            "top_gainers_alone": False,
            "top_losers_alone": False,
            "setup_quality_required": True,
            "minimum_confidence": MINIMUM_CONFIDENCE,
        },

        "required_setup_types": list(
            PRIMARY_SETUP_TYPES
        ),

        "support": {
            "minimum_touches":
                MIN_SUPPORT_TOUCHES,
            "required_for_long": True,
        },

        "resistance": {
            "minimum_touches":
                MIN_RESISTANCE_TOUCHES,
            "required_for_short": True,
        },

        "core_timeframes": list(
            CORE_TIMEFRAMES
        ),

        "scanner_refresh_seconds":
            SCANNER_REFRESH_SECONDS,
    }


# =========================================================
# HEALTH
# =========================================================

@app.get("/health")
async def health():

    try:

        scanner_state = (
            auto_scanner.snapshot()
        )

    except Exception as exc:

        scanner_state = {
            "running": False,
            "error": str(exc),
        }

    return {
        "success": True,

        "app": "RR Trader",

        "status": "healthy",

        "version": APP_VERSION,

        "strategy": {
            "mode": STRATEGY_MODE,
            "minimum_confidence":
                MINIMUM_CONFIDENCE,

            "support_bounce": {
                "enabled": True,
                "minimum_touches":
                    MIN_SUPPORT_TOUCHES,
            },

            "resistance_rejection": {
                "enabled": True,
                "minimum_touches":
                    MIN_RESISTANCE_TOUCHES,
            },

            "top_mover_only_signals": False,

            "core_timeframes":
                list(CORE_TIMEFRAMES),
        },

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

        "scanner": scanner_state,

        "liquidation": {
            "enabled": True,
            "endpoint":
                "/api/liquidation/status",
        },
    }


# =========================================================
# API ROUTERS
# =========================================================

app.include_router(
    main_router,
    prefix="/api",
    tags=["Markets"],
)


app.include_router(
    trade_router,
    prefix="/api",
    tags=["Trade Engine"],
)


app.include_router(
    ai_router,
    prefix="/api",
    tags=["AI"],
)


app.include_router(
    dashboard_router,
    prefix="/api",
    tags=["Dashboard"],
)


app.include_router(
    scanner_router,
    prefix="/api",
    tags=["Scanner"],
)


# =========================================================
# LIQUIDATION INTELLIGENCE
# =========================================================

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

    print("=" * 60)
    print("RR TRADER STARTING")
    print("=" * 60)

    print(
        f"Application version: {APP_VERSION}"
    )

    print(
        f"Project root: {PROJECT_ROOT}"
    )

    print(
        f"Frontend directory: "
        f"{FRONTEND_DIR.is_dir()}"
    )

    print(
        f"Frontend index: "
        f"{FRONTEND_INDEX.is_file()}"
    )

    print(
        f"Pages directory: "
        f"{PAGES_DIR.is_dir()}"
    )

    print(
        f"Charts directory: "
        f"{CHARTS_DIR.is_dir()}"
    )

    print(
        "Strategy mode: "
        f"{STRATEGY_MODE}"
    )

    print(
        "Minimum confidence: "
        f"{MINIMUM_CONFIDENCE}"
    )

    print(
        "Minimum support touches: "
        f"{MIN_SUPPORT_TOUCHES}"
    )

    print(
        "Minimum resistance touches: "
        f"{MIN_RESISTANCE_TOUCHES}"
    )

    print(
        "Top-gainer/top-loser-only signals: "
        "DISABLED"
    )

    print(
        "Required setups: "
        "SUPPORT_BOUNCE / "
        "RESISTANCE_REJECTION"
    )

    print(
        "Core timeframes: "
        "15m / 1h / 4h"
    )

    print(
        "Liquidation Intelligence: ENABLED"
    )

    print(
        "Liquidation endpoint: "
        "/api/liquidation/status"
    )

    try:

        await auto_scanner.start()

        print(
            "RR Trader automatic scanner started."
        )

        print(
            "Scanner refresh: "
            f"{SCANNER_REFRESH_SECONDS} seconds."
        )

    except Exception as exc:

        print(
            "Scanner startup warning:",
            exc,
        )

    print("=" * 60)


# =========================================================
# SHUTDOWN
# =========================================================

@app.on_event("shutdown")
async def shutdown_event():

    print(
        "Stopping RR Trader scanner..."
    )

    try:

        await auto_scanner.stop()

    except Exception as exc:

        print(
            "Scanner shutdown warning:",
            exc,
        )

    print(
        "RR Trader backend stopped."
    )
