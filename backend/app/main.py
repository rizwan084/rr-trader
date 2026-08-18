from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as main_router
from app.api.trade_routes import router as trade_router
from app.api.ai_routes import router as ai_router
from app.api.dashboard_routes import router as dashboard_router


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
    version="1.0.0",
)


# =========================================================
# STATIC FILES
# =========================================================

# Pages:
# /pages/overview.html
# /pages/charts.html
# /pages/ai.html
# etc.

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


# Frontend services:
# /frontend-services/...

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


# Charts assets:
# /frontend-charts/...

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


# Components:
# /frontend-components/...

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


# General assets:
# /assets/...

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
        "error":
            "Dashboard frontend not found.",
        "frontend_path":
            str(FRONTEND_INDEX),
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
        "error":
            "Dashboard frontend not found.",
        "frontend_path":
            str(FRONTEND_INDEX),
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

@app.on_event("startup")
async def startup_event():

    print(
        "RR Trader backend started successfully."
    )

    print(
        f"Project root: {PROJECT_ROOT}"
    )

    print(
        f"Frontend: {FRONTEND_DIR}"
    )

    print(
        f"Index exists: "
        f"{FRONTEND_INDEX.is_file()}"
    )

    print(
        f"Pages exists: "
        f"{PAGES_DIR.is_dir()}"
    )

    print(
        f"Charts page exists: "
        f"{(PAGES_DIR / 'charts.html').is_file()}"
    )


# =========================================================
# SHUTDOWN
# =========================================================

@app.on_event("shutdown")
async def shutdown_event():

    print(
        "RR Trader backend shutting down."
    )
