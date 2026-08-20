from __future__ import annotations

from contextlib import asynccontextmanager
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
from app.services.ai import ai_service


# =========================================================
# PROJECT PATHS
# =========================================================

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
# APPLICATION VERSION
# =========================================================

APP_NAME = (
    "RR Trader Live Crypto Trading Scanner"
)

APP_VERSION = "3.0.0"


# =========================================================
# SAFE AI STATUS
# =========================================================

def get_ai_status() -> dict[str, Any]:
    """
    Safely read AI service status.

    AI failure must never prevent RR Trader
    from starting.
    """

    try:

        status_method = getattr(
            ai_service,
            "status",
            None,
        )

        if not callable(
            status_method
        ):

            return {
                "enabled": False,
                "configured": False,
                "status": "UNAVAILABLE",
            }

        result = status_method()

        if not isinstance(
            result,
            dict,
        ):

            return {
                "enabled": False,
                "configured": False,
                "status": "INVALID_STATUS",
            }

        return result

    except Exception as exc:

        return {
            "enabled": False,
            "configured": False,
            "status": "ERROR",
            "error": str(exc),
        }


# =========================================================
# APPLICATION LIFESPAN
# =========================================================

@asynccontextmanager
async def lifespan(
    app: FastAPI,
):
    """
    RR Trader application lifecycle.

    Startup:
        - Validate AI
        - Start automatic scanner

    Shutdown:
        - Stop scanner
        - Close AI resources when supported
    """

    print("=" * 70)
    print("RR TRADER STARTING")
    print("=" * 70)

    print(
        f"Application: {APP_NAME}"
    )

    print(
        f"Version: {APP_VERSION}"
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

    # -----------------------------------------------------
    # AI STARTUP CHECK
    # -----------------------------------------------------

    try:

        ai_status = get_ai_status()

        print(
            "AI status:",
            ai_status,
        )

    except Exception as exc:

        print(
            "AI startup warning:",
            exc,
        )

    # -----------------------------------------------------
    # AUTO SCANNER
    # -----------------------------------------------------

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

    print(
        "Liquidation Intelligence: ENABLED"
    )

    print(
        "Liquidation endpoint: "
        "/api/liquidation/status"
    )

    print("=" * 70)

    yield

    # =====================================================
    # SHUTDOWN
    # =====================================================

    print("=" * 70)
    print("RR TRADER SHUTTING DOWN")
    print("=" * 70)

    # -----------------------------------------------------
    # STOP SCANNER
    # -----------------------------------------------------

    try:

        await auto_scanner.stop()

        print(
            "RR Trader automatic scanner stopped."
        )

    except Exception as exc:

        print(
            "Scanner shutdown warning:",
            exc,
        )

    # -----------------------------------------------------
    # CLOSE AI SERVICE
    # -----------------------------------------------------

    try:

        close_method = getattr(
            ai_service,
            "close",
            None,
        )

        if callable(
            close_method
        ):

            result = close_method()

            if hasattr(
                result,
                "__await__",
            ):

                await result

            print(
                "AI service closed."
            )

    except Exception as exc:

        print(
            "AI shutdown warning:",
            exc,
        )

    print(
        "RR Trader backend stopped."
    )

    print("=" * 70)


# =========================================================
# FASTAPI APPLICATION
# =========================================================

app = FastAPI(
    title=APP_NAME,
    description=(
        "Professional AI-powered crypto "
        "market scanner with multi-exchange "
        "analysis, trading intelligence, "
        "liquidation intelligence and "
        "AI assistant capabilities."
    ),
    version=APP_VERSION,
    lifespan=lifespan,
)


# =========================================================
# FRONTEND STATIC FILES
# =========================================================

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


if ASSETS_DIR.is_dir():

    app.mount(
        "/assets",
        StaticFiles(
            directory=str(
                ASSETS_DIR
            ),
        ),
        name="assets",
    )


# =========================================================
# ROOT
# =========================================================

@app.get(
    "/",
    tags=["System"],
)
async def root():

    if FRONTEND_INDEX.is_file():

        return FileResponse(
            str(
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
        "version": APP_VERSION,
    }


# =========================================================
# DASHBOARD
# =========================================================

@app.get(
    "/dashboard",
    tags=["Dashboard"],
)
async def dashboard():

    if FRONTEND_INDEX.is_file():

        return FileResponse(
            str(
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

@app.get(
    "/health",
    tags=["System"],
)
async def health():

    # -----------------------------------------------------
    # Scanner status
    # -----------------------------------------------------

    try:

        scanner_state = (
            auto_scanner.snapshot()
        )

        if not isinstance(
            scanner_state,
            dict,
        ):

            scanner_state = {
                "running": False,
                "status": "INVALID",
            }

    except Exception as exc:

        scanner_state = {
            "running": False,
            "status": "ERROR",
            "error": str(exc),
        }

    # -----------------------------------------------------
    # AI status
    # -----------------------------------------------------

    ai_state = get_ai_status()

    ai_enabled = bool(
        ai_state.get(
            "enabled",
            False,
        )
    )

    ai_configured = bool(
        ai_state.get(
            "configured",
            False,
        )
    )

    ai_online = (
        ai_enabled
        and ai_configured
    )

    # -----------------------------------------------------
    # Overall status
    # -----------------------------------------------------

    return {
        "success": True,

        "app": "RR Trader",

        "name": APP_NAME,

        "status": "healthy",

        "version": APP_VERSION,

        "frontend": {
            "directory_exists":
                FRONTEND_DIR.is_dir(),

            "index_exists":
                FRONTEND_INDEX.is_file(),

            "pages_exists":
                PAGES_DIR.is_dir(),

            "charts_exists":
                CHARTS_DIR.is_dir(),

            "services_exists":
                SERVICES_DIR.is_dir(),

            "components_exists":
                COMPONENTS_DIR.is_dir(),

            "assets_exists":
                ASSETS_DIR.is_dir(),
        },

        "scanner": scanner_state,

        "ai": {
            "online":
                ai_online,

            "enabled":
                ai_enabled,

            "configured":
                ai_configured,

            "status":
                ai_state.get(
                    "status",
                    "UNKNOWN",
                ),

            "model":
                ai_state.get(
                    "model",
                    ai_state.get(
                        "chat_model",
                        None,
                    ),
                ),

            "image_generation":
                ai_state.get(
                    "image_generation",
                    ai_state.get(
                        "image_enabled",
                        False,
                    ),
                ),

            "web_search":
                ai_state.get(
                    "web_search",
                    False,
                ),
        },

        "liquidation": {
            "enabled": True,
            "endpoint":
                "/api/liquidation/status",
        },

        "endpoints": {
            "dashboard":
                "/dashboard",

            "health":
                "/health",

            "ai":
                "/api/ai",

            "ai_chat":
                "/api/ai/chat",

            "ai_status":
                "/api/ai/status",

            "ai_health":
                "/api/ai/health",

            "ai_image":
                "/api/ai/image",

            "scanner":
                "/api",

            "liquidation":
                "/api/liquidation/status",
        },
    }


# =========================================================
# API ROUTERS
# =========================================================

# ---------------------------------------------------------
# MAIN MARKET ROUTES
#
# These routes already belong under /api.
# ---------------------------------------------------------

app.include_router(
    main_router,
    prefix="/api",
    tags=["Markets"],
)


# ---------------------------------------------------------
# TRADE ENGINE
# ---------------------------------------------------------

app.include_router(
    trade_router,
    prefix="/api",
    tags=["Trade Engine"],
)


# ---------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------

app.include_router(
    dashboard_router,
    prefix="/api",
    tags=["Dashboard"],
)


# ---------------------------------------------------------
# SCANNER
# ---------------------------------------------------------

app.include_router(
    scanner_router,
    prefix="/api",
    tags=["Scanner"],
)


# ---------------------------------------------------------
# LIQUIDATION INTELLIGENCE
# ---------------------------------------------------------

app.include_router(
    liquidation_router,
    prefix="/api",
    tags=["Liquidation Intelligence"],
)


# ---------------------------------------------------------
# AI
#
# IMPORTANT:
#
# ai_routes.py already contains:
#
#     prefix="/api/ai"
#
# Therefore DO NOT add prefix="/api" here.
#
# Otherwise routes could become:
#
#     /api/api/ai/...
#
# ---------------------------------------------------------

app.include_router(
    ai_router,
)


# =========================================================
# APPLICATION READY
# =========================================================

@app.get(
    "/ready",
    tags=["System"],
)
async def ready():

    ai_state = get_ai_status()

    try:

        scanner_state = (
            auto_scanner.snapshot()
        )

    except Exception:

        scanner_state = {
            "running": False,
        }

    return {
        "success": True,
        "ready": True,
        "app": "RR Trader",
        "version": APP_VERSION,

        "services": {
            "scanner":
                bool(
                    scanner_state.get(
                        "running",
                        False,
                    )
                ),

            "ai":
                bool(
                    ai_state.get(
                        "enabled",
                        False,
                    )
                    and
                    ai_state.get(
                        "configured",
                        False,
                    )
                ),

            "liquidation":
                True,

            "dashboard":
                FRONTEND_INDEX.is_file(),
        },
    }


# =========================================================
# EXPORT
# =========================================================

__all__ = [
    "app",
]
