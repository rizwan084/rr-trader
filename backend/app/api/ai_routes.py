from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.services.ai import ai_engine


router = APIRouter()


# =========================================================
# AI STATUS
# =========================================================

@router.get("/ai/status")
async def ai_status() -> dict[str, Any]:
    return {
        "success": True,
        **ai_engine.status(),
    }


# =========================================================
# AI CHAT
# =========================================================

@router.post("/ai/chat")
async def ai_chat(
    payload: dict[str, Any],
) -> dict[str, Any]:

    message = str(
        payload.get(
            "message",
            "",
        )
    ).strip()

    context = payload.get(
        "context"
    )

    if not message:
        return {
            "success": False,
            "error": "Message is required.",
        }

    if context is not None and not isinstance(
        context,
        dict,
    ):
        context = None

    return await ai_engine.chat(
        user_request=message,
        context=context,
    )


# =========================================================
# AI ANALYSIS EXPLANATION
# =========================================================

@router.post("/ai/explain")
async def ai_explain(
    analysis: dict[str, Any],
) -> dict[str, Any]:

    return await ai_engine.explain_analysis(
        analysis
    )


# =========================================================
# POST GENERATION
# =========================================================

@router.post("/ai/post")
async def ai_post(
    analysis: dict[str, Any],
) -> dict[str, Any]:

    return await ai_engine.generate_post(
        analysis
    )
