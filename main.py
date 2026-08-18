from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router as api_router
from app.api.trade_routes import router as trade_router
from app.core.config import settings

app = FastAPI(
    title="RR Trader",
    version=settings.app_version,
    description="AI-powered Binance Spot and Futures trading intelligence platform.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api", tags=["RR Trader API"])
app.include_router(trade_router, prefix="/api", tags=["Trade Engine"])


@app.get("/", tags=["System"])
async def root():
    return {
        "app": settings.app_name,
        "status": "online",
        "version": settings.app_version,
        "markets": ["spot", "futures"],
        "dashboard": "/dashboard",
    }


@app.get("/dashboard", tags=["Dashboard"])
async def dashboard():
    return {
        "success": True,
        "message": "Dashboard shell is ready. Frontend phase follows.",
        "frontend": "frontend/",
    }
