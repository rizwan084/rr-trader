from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..services.ai import ai_service

router = APIRouter(prefix="/api/ai", tags=["AI"])


class AIChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=20000)
    context: Optional[Dict[str, Any]] = None
    conversation_id: str = Field(default="default", min_length=1, max_length=200)
    use_web: Optional[bool] = None
    allow_image: bool = True
    image_size: str = Field(default="1024x1024", max_length=32)


class AIImageRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=10000)
    size: str = Field(default="1024x1024", max_length=32)
    quality: str = Field(default="high", max_length=32)


@router.get("/status")
async def ai_status() -> Dict[str, Any]:
    try:
        status = ai_service.status()
        if not isinstance(status, dict):
            status = {}
        configured = bool(getattr(ai_service, "api_key", ""))
        enabled = bool(status.get("enabled", False))
        return {
            "success": True,
            "service": "RR Trader AI",
            **status,
            "enabled": enabled,
            "configured": configured,
            "status": "ONLINE" if enabled and configured else "NOT_CONFIGURED",
        }
    except Exception as exc:
        return {
            "success": False,
            "service": "RR Trader AI",
            "enabled": False,
            "configured": False,
            "status": "ERROR",
            "error_code": "AI_STATUS_FAILED",
            "error": str(exc),
        }


@router.post("/chat")
async def ai_chat(request: AIChatRequest) -> Dict[str, Any]:
    try:
        result = await ai_service.ask(
            request.message,
            context=request.context,
            conversation_id=request.conversation_id,
            use_web=request.use_web,
            allow_image=request.allow_image,
            image_size=request.image_size,
        )
        if not isinstance(result, dict):
            return {
                "success": False,
                "type": "error",
                "error": "AI returned an invalid response.",
                "error_code": "AI_INVALID_RESPONSE",
            }
        return result
    except Exception as exc:
        return {
            "success": False,
            "type": "error",
            "response": "I couldn't process your request right now. Please try again.",
            "error": str(exc),
            "error_code": "AI_CHAT_ROUTE_FAILED",
        }


@router.post("/image")
async def ai_image(request: AIImageRequest) -> Dict[str, Any]:
    try:
        image = await ai_service.generate_image(
            prompt=request.prompt,
            size=request.size,
            quality=request.quality,
        )
        return {
            **image,
            "type": "image" if image.get("success") else "error",
        }
    except Exception as exc:
        return {
            "success": False,
            "type": "error",
            "error": str(exc),
            "error_code": "AI_IMAGE_ROUTE_FAILED",
        }


@router.post("/analyze")
async def ai_analyze_market(
    market_data: Dict[str, Any],
    conversation_id: str = "market",
) -> Dict[str, Any]:
    try:
        result = await ai_service.analyze_market(
            market_data=market_data,
            conversation_id=conversation_id,
        )
        return result if isinstance(result, dict) else {
            "success": False,
            "error": "AI returned an invalid market-analysis response.",
        }
    except Exception as exc:
        return {
            "success": False,
            "type": "error",
            "error": str(exc),
            "error_code": "AI_ANALYSIS_ROUTE_FAILED",
        }


@router.get("/health")
async def ai_health() -> Dict[str, Any]:
    status = await ai_status()
    enabled = bool(status.get("enabled"))
    configured = bool(status.get("configured"))
    return {
        "success": True,
        "service": "RR Trader AI",
        "healthy": enabled and configured,
        "enabled": enabled,
        "configured": configured,
        "status": "ONLINE" if enabled and configured else "NOT_READY",
        "model": status.get("text_model"),
    }


__all__ = ["router", "AIChatRequest", "AIImageRequest"]
