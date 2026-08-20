from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..services.ai_service import ai_service

router = APIRouter(prefix="/api/ai", tags=["AI"])


class AIChatRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        max_length=20000,
    )
    context: Optional[Dict[str, Any]] = None
    conversation_id: str = Field(
        default="default",
        min_length=1,
        max_length=200,
    )
    use_web: Optional[bool] = None
    allow_image: bool = True
    image_size: str = "1024x1024"


class AIImageRequest(BaseModel):
    prompt: str = Field(
        ...,
        min_length=1,
        max_length=10000,
    )
    size: str = "1024x1024"
    quality: str = "high"


@router.get("/status")
async def ai_status() -> Dict[str, Any]:
    return {
        "success": True,
        **ai_service.status(),
    }


@router.post("/chat")
async def ai_chat(
    request: AIChatRequest,
) -> Dict[str, Any]:
    result = await ai_service.ask(
        request.message,
        context=request.context,
        conversation_id=request.conversation_id,
        use_web=request.use_web,
        allow_image=request.allow_image,
        image_size=request.image_size,
    )
    return result


@router.post("/image")
async def ai_image(
    request: AIImageRequest,
) -> Dict[str, Any]:
    image = await ai_service.generate_image(
        request.prompt,
        size=request.size,
        quality=request.quality,
    )
    return {
        "success": True,
        "type": "image",
        "image": image,
        "model": ai_service.image_model,
    }


__all__ = ["router"]
