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
from app.api.accountability_routes import router as accountability_router
from app.api.scanner_routes import router as scanner_router
from app.api.liquidation_routes import router as liquidation_router
from app.api.forex_routes import router as forex_router
from app.core.config import settings
from app.core.market_resilience import install_market_data_resilience
from app.services.auto_scanner import auto_scanner
from app.services.ai import ai_service
from app.services.forex_engine import forex_engine
from app.services.supabase_store import supabase_store

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "frontend"
FRONTEND_INDEX = FRONTEND_DIR / "index.html"
PAGES_DIR = FRONTEND_DIR / "pages"
SERVICES_DIR = FRONTEND_DIR / "services"
CHARTS_DIR = FRONTEND_DIR / "charts"
COMPONENTS_DIR = FRONTEND_DIR / "components"
ASSETS_DIR = FRONTEND_DIR / "assets"
BITGURU_DIR = PROJECT_ROOT / "dashboard"
BITGURU_INDEX = BITGURU_DIR / "index.html"
FARHAT_INDEX = FRONTEND_DIR / "farhat.html"
BITGURU_ACCOUNTABILITY_INDEX = BITGURU_DIR / "accountability.html"

APP_NAME = "RR Trader Professional Trading Intelligence"
APP_VERSION = "5.0.0"


def get_ai_status() -> dict[str, Any]:
    try:
        result = ai_service.status()
        if not isinstance(result, dict): result = {}
        result["configured"] = bool(str(getattr(settings, "openai_api_key", "") or "").strip())
        result["enabled"] = bool(getattr(settings, "ai_enabled", True))
        result["status"] = "ONLINE" if result["enabled"] and result["configured"] else "NOT_CONFIGURED"
        return result
    except Exception as exc:
        return {"enabled": False, "configured": False, "status": "ERROR", "error": str(exc)}


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("RR TRADER STARTING")
    print(f"Version: {APP_VERSION}")
    install_market_data_resilience()
    print("AI status:", get_ai_status())
    print("Forex/Gold status:", forex_engine.status())
    print("Market-data resilience: ENABLED (Binance -> Bitget fallback)")
    try: await auto_scanner.start()
    except Exception as exc: print("Scanner startup warning:", exc)
    yield
    try: await auto_scanner.stop()
    except Exception as exc: print("Scanner shutdown warning:", exc)
    close_method = getattr(ai_service, "close", None)
    if callable(close_method):
        try:
            result = close_method()
            if hasattr(result, "__await__"): await result
        except Exception as exc: print("AI shutdown warning:", exc)


app = FastAPI(title=APP_NAME, description="Professional crypto, Forex and Gold trading intelligence platform.", version=APP_VERSION, lifespan=lifespan)

for path, url, name, html in [(PAGES_DIR, "/pages", "pages", True),(SERVICES_DIR, "/frontend-services", "frontend-services", False),(CHARTS_DIR, "/frontend-charts", "frontend-charts", False),(COMPONENTS_DIR, "/frontend-components", "frontend-components", False),(ASSETS_DIR, "/assets", "assets", False)]:
    if path.is_dir(): app.mount(url, StaticFiles(directory=str(path), html=html), name=name)


@app.get("/", tags=["System"])
async def root():
    if FARHAT_INDEX.is_file(): return FileResponse(str(FARHAT_INDEX), media_type="text/html", headers={"Cache-Control":"no-store, max-age=0"})
    if FRONTEND_INDEX.is_file(): return FileResponse(str(FRONTEND_INDEX), media_type="text/html")
    return {"success": False, "error": "Dashboard frontend not found.", "version": APP_VERSION}


@app.get("/farhat/manifest.json", tags=["Farhat Binance"])
async def farhat_manifest():
    path = FRONTEND_DIR / "farhat" / "manifest.json"
    if path.is_file():
        return FileResponse(str(path), media_type="application/manifest+json")
    return {"success": False, "error": "Farhat manifest not found."}

@app.get("/farhat/sw.js", tags=["Farhat Binance"])
async def farhat_service_worker():
    path = FRONTEND_DIR / "farhat" / "sw.js"
    if path.is_file():
        return FileResponse(str(path), media_type="application/javascript", headers={"Cache-Control":"no-store, max-age=0"})
    return {"success": False, "error": "Farhat service worker not found."}

@app.get("/farhat/icon.svg", tags=["Farhat Binance"])
async def farhat_icon():
    path = FRONTEND_DIR / "farhat" / "icon.svg"
    if path.is_file():
        return FileResponse(str(path), media_type="image/svg+xml")
    return {"success": False, "error": "Farhat icon not found."}

@app.get("/farhat", tags=["Farhat Binance"])
async def farhat_dashboard():
    if FARHAT_INDEX.is_file(): return FileResponse(str(FARHAT_INDEX), media_type="text/html")
    return {"success": False, "error": "Farhat Binance dashboard not found."}


@app.get("/dashboard", tags=["Dashboard"])
async def dashboard():
    if FRONTEND_INDEX.is_file(): return FileResponse(str(FRONTEND_INDEX), media_type="text/html")
    return {"success": False, "error": "Dashboard frontend not found."}


@app.get("/bitguru", tags=["BitGuru"])
@app.get("/bitguru/", tags=["BitGuru"])
async def bitguru_dashboard():
    path = BITGURU_ACCOUNTABILITY_INDEX if BITGURU_ACCOUNTABILITY_INDEX.is_file() else BITGURU_INDEX
    if path.is_file(): return FileResponse(str(path), media_type="text/html")
    return {"success": False, "error": "BitGuru dashboard frontend not found."}


@app.get("/bitguru/manifest.json", tags=["BitGuru"])
async def bitguru_manifest():
    path = BITGURU_DIR / "manifest.json"
    if path.is_file(): return FileResponse(str(path), media_type="application/manifest+json")
    return {"success": False, "error": "BitGuru manifest not found."}


@app.get("/bitguru/icon.svg", tags=["BitGuru"])
async def bitguru_icon():
    path = BITGURU_DIR / "icon.svg"
    if path.is_file(): return FileResponse(str(path), media_type="image/svg+xml")
    return {"success": False, "error": "BitGuru icon not found."}


@app.get("/healthz", tags=["System"])
async def healthz():
    """Ultra-light liveness endpoint; never touches Binance, Supabase, AI or MT5."""
    return {"success": True, "status": "alive", "app": "RR Trader", "version": APP_VERSION}


@app.get("/health", tags=["System"])
async def health():
    try: scanner_state = auto_scanner.snapshot()
    except Exception as exc: scanner_state = {"running": False, "status": "ERROR", "error": str(exc)}
    ai_state = get_ai_status()
    return {"success": True, "app": "RR Trader", "status": "healthy", "version": APP_VERSION, "scanner": scanner_state, "ai": ai_state, "forex": forex_engine.status(), "liquidation": {"enabled": True, "endpoint": "/api/liquidation/status"}, "market_data": {"primary": "Binance", "fallback": "Bitget Futures", "resilience_enabled": True}, "supabase": supabase_store.status(), "endpoints": {"dashboard": "/dashboard", "farhat": "/farhat", "bitguru": "/bitguru/", "bitguru_accountability": "/api/dashboard/accountability", "ai_chat": "/api/ai/chat", "scanner": "/api", "liquidation": "/api/liquidation/status", "forex_status": "/api/forex/status", "forex_watchlist": "/api/forex/watchlist", "gold_mtf": "/api/forex/multi-timeframe?symbol=XAUUSD"}}


app.include_router(main_router, prefix="/api", tags=["Markets"])
app.include_router(trade_router, prefix="/api", tags=["Trade Engine"])
app.include_router(dashboard_router, prefix="/api", tags=["Dashboard"])
app.include_router(accountability_router, prefix="/api", tags=["BitGuru Accountability"])
app.include_router(scanner_router, prefix="/api", tags=["Scanner"])
app.include_router(liquidation_router, prefix="/api", tags=["Liquidation Intelligence"])
app.include_router(forex_router)
app.include_router(ai_router)


@app.get("/ready", tags=["System"])
async def ready():
    ai_state = get_ai_status()
    try: scanner_state = auto_scanner.snapshot()
    except Exception: scanner_state = {"running": False}
    forex_state = forex_engine.status()
    return {"success": True, "ready": True, "app": "RR Trader", "version": APP_VERSION, "services": {"scanner": bool(scanner_state.get("running", False)), "ai": bool(ai_state.get("enabled", False) and ai_state.get("configured", False)), "forex_mt5": bool(forex_state.get("configured", False)), "gold_xauusd": True, "liquidation": True, "market_data_fallback": True, "dashboard": FRONTEND_INDEX.is_file(), "bitguru_dashboard": BITGURU_ACCOUNTABILITY_INDEX.is_file() or BITGURU_INDEX.is_file()}}


__all__ = ["app"]
