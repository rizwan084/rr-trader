from datetime import datetime, timezone

from fastapi import FastAPI

app = FastAPI(
    title="RR Trader",
    description="RR Trader Live Crypto Trading Platform",
    version="1.0.0",
)


@app.get("/")
async def root():
    return {
        "app": "RR Trader",
        "status": "online",
        "version": "1.0.0",
        "message": "RR Trader backend is working",
    }


@app.get("/health")
async def health():
    return {
        "success": True,
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
