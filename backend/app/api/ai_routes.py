from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# =========================================================
# RR TRADER AI ROUTES
#
# IMPORTANT:
# The actual AI service file is:
#
#     backend/app/services/ai.py
#
# Therefore the import MUST use:
#
#     from ..services.ai import ai_service
#
# Do NOT use:
#     from ..services.ai_service import ai_service
# =========================================================

from ..services.ai import ai_service


# =========================================================
# ROUTER
# =========================================================

router = APIRouter(
    prefix="/api/ai",
    tags=["AI"],
)


# =========================================================
# REQUEST MODELS
# =========================================================


class AIChatRequest(BaseModel):
    """
    Main AI chat request.
    """

    message: str = Field(
        ...,
        min_length=1,
        max_length=20000,
    )

    context: Optional[
        Dict[str, Any]
    ] = None

    conversation_id: str = Field(
        default="default",
        min_length=1,
        max_length=200,
    )

    use_web: Optional[bool] = None

    allow_image: bool = True

    image_size: str = Field(
        default="1024x1024",
        max_length=32,
    )


class AIImageRequest(BaseModel):
    """
    Direct AI image-generation request.
    """

    prompt: str = Field(
        ...,
        min_length=1,
        max_length=10000,
    )

    size: str = Field(
        default="1024x1024",
        max_length=32,
    )

    quality: str = Field(
        default="high",
        max_length=32,
    )


# =========================================================
# STATUS
# =========================================================


@router.get("/status")
async def ai_status() -> Dict[str, Any]:
    """
    Return AI service health/configuration status.

    This endpoint must NEVER crash the application.
    """

    try:

        status = ai_service.status()

        if not isinstance(
            status,
            dict,
        ):
            status = {}

        return {
            "success": True,
            "service": "RR Trader AI",
            **status,
        }

    except Exception as exc:

        return {
            "success": False,
            "service": "RR Trader AI",
            "enabled": False,
            "status": "ERROR",
            "error_code": "AI_STATUS_FAILED",
            "message": (
                "AI status could not be loaded."
            ),
            "detail": str(exc),
        }


# =========================================================
# CHAT
# =========================================================


@router.post("/chat")
async def ai_chat(
    request: AIChatRequest,
) -> Dict[str, Any]:
    """
    Main AI conversation endpoint.

    Supports:
    - General questions
    - Crypto questions
    - RR Trader context
    - Conversation memory
    - Web search when enabled
    - Image-generation intent
    """

    try:

        result = await ai_service.ask(
            request.message,
            context=request.context,
            conversation_id=(
                request.conversation_id
            ),
            use_web=request.use_web,
            allow_image=request.allow_image,
            image_size=request.image_size,
        )

        if not isinstance(
            result,
            dict,
        ):

            return {
                "success": False,
                "type": "error",
                "response": (
                    "AI returned an invalid response."
                ),
                "error_code": (
                    "AI_INVALID_RESPONSE"
                ),
            }

        return result

    except Exception as exc:

        # Never allow an AI failure to crash
        # the FastAPI application.

        return {
            "success": False,
            "type": "error",
            "response": (
                "I couldn't process your request "
                "right now. Please try again."
            ),
            "error_code": (
                "AI_CHAT_ROUTE_FAILED"
            ),
            "detail": str(exc),
        }


# =========================================================
# IMAGE GENERATION
# =========================================================


@router.post("/image")
async def ai_image(
    request: AIImageRequest,
) -> Dict[str, Any]:
    """
    Direct image generation endpoint.
    """

    try:

        image = await ai_service.generate_image(
            request.prompt,
            size=request.size,
            quality=request.quality,
        )

        return {
            "success": True,
            "type": "image",
            "image": image,
            "model": (
                ai_service.image_model
            ),
        }

    except Exception as exc:

        return {
            "success": False,
            "type": "error",
            "response": (
                "I couldn't generate the image "
                "right now. Please try again."
            ),
            "error_code": (
                "AI_IMAGE_ROUTE_FAILED"
            ),
            "detail": str(exc),
        }


# =========================================================
# MARKET ANALYSIS
# =========================================================


@router.post("/analyze")
async def ai_analyze_market(
    market_data: Dict[str, Any],
    conversation_id: str = "market",
) -> Dict[str, Any]:
    """
    Analyze supplied RR Trader market data.

    This gives the dashboard/other backend services
    a dedicated endpoint instead of forcing them to
    manually build an AI prompt.
    """

    try:

        result = await ai_service.analyze_market(
            market_data=market_data,
            conversation_id=conversation_id,
        )

        if not isinstance(
            result,
            dict,
        ):

            return {
                "success": False,
                "type": "error",
                "response": (
                    "AI returned an invalid "
                    "market-analysis response."
                ),
                "error_code": (
                    "AI_INVALID_ANALYSIS_RESPONSE"
                ),
            }

        return result

    except Exception as exc:

        return {
            "success": False,
            "type": "error",
            "response": (
                "Market analysis could not be "
                "completed right now."
            ),
            "error_code": (
                "AI_ANALYSIS_ROUTE_FAILED"
            ),
            "detail": str(exc),
        }


# =========================================================
# HEALTH
# =========================================================


@router.get("/health")
async def ai_health() -> Dict[str, Any]:
    """
    Lightweight AI health endpoint.

    Useful for Render, dashboard and monitoring.
    """

    try:

        status = ai_service.status()

        if not isinstance(
            status,
            dict,
        ):
            status = {}

        enabled = bool(
            status.get(
                "enabled",
                False,
            )
        )

        configured = bool(
            status.get(
                "configured",
                False,
            )
        )

        return {
            "success": True,
            "service": "RR Trader AI",
            "healthy": (
                enabled
                and configured
            ),
            "enabled": enabled,
            "configured": configured,
            "status": (
                "ONLINE"
                if enabled and configured
                else "NOT_READY"
            ),
        }

    except Exception as exc:

        return {
            "success": False,
            "healthy": False,
            "status": "ERROR",
            "error_code": (
                "AI_HEALTH_FAILED"
            ),
            "message": (
                "AI health check failed."
            ),
            "detail": str(exc),
        }


# =========================================================
# EXPORT
# =========================================================

__all__ = [
    "router",
    "AIChatRequest",
    "AIImageRequest",
]
