from __future__ import annotations

import asyncio
import base64
import binascii
import json
import re
from collections import defaultdict, deque
from typing import Any

import httpx

from app.core.config import settings


# =========================================================
# RR TRADER AI ENGINE
#
# Purpose:
#   - General AI chat
#   - RR Trader analysis explanation
#   - LONG / SHORT / NO TRADE explanation
#   - Binance Square post generation
#   - Image generation
#   - Bounded session memory
#   - Safe API errors + retry handling
#   - Backward compatibility with ai_service
#
# Important:
#   The deterministic RR Trader engines remain authoritative.
#   AI explains supplied data; it must never invent live data
#   or override deterministic risk gates.
# =========================================================


class AIEngine:
    """Production-oriented OpenAI service for RR Trader."""

    DEFAULT_TEXT_MODEL = "gpt-5.6"
    DEFAULT_IMAGE_MODEL = "gpt-image-2"

    RESPONSES_URL = "https://api.openai.com/v1/responses"
    IMAGES_URL = "https://api.openai.com/v1/images/generations"

    MAX_HISTORY_MESSAGES = 20
    MAX_HISTORY_CONTENT_CHARS = 8_000
    MAX_CONTEXT_CHARS = 120_000
    MAX_USER_REQUEST_CHARS = 20_000
    MAX_IMAGE_PROMPT_CHARS = 10_000

    RETRY_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}
    MAX_RETRIES = 3

    def __init__(self) -> None:
        self.api_key = str(
            getattr(settings, "openai_api_key", "") or ""
        ).strip()

        self.enabled = bool(
            getattr(settings, "ai_enabled", True)
            and self.api_key
        )

        self.text_model = str(
            getattr(
                settings,
                "openai_model",
                self.DEFAULT_TEXT_MODEL,
            )
            or self.DEFAULT_TEXT_MODEL
        ).strip()

        self.image_model = str(
            getattr(
                settings,
                "openai_image_model",
                self.DEFAULT_IMAGE_MODEL,
            )
            or self.DEFAULT_IMAGE_MODEL
        ).strip()

        self.api_url = str(
            getattr(
                settings,
                "openai_api_url",
                self.RESPONSES_URL,
            )
            or self.RESPONSES_URL
        ).rstrip("/")

        self.image_api_url = str(
            getattr(
                settings,
                "openai_image_api_url",
                self.IMAGES_URL,
            )
            or self.IMAGES_URL
        ).rstrip("/")

        self.timeout = max(
            10.0,
            float(
                getattr(
                    settings,
                    "request_timeout",
                    60.0,
                )
                or 60.0
            ),
        )

        self.max_output_tokens = max(
            256,
            int(
                getattr(
                    settings,
                    "ai_max_output_tokens",
                    2000,
                )
                or 2000
            ),
        )

        self._sessions: dict[
            str,
            deque[dict[str, str]],
        ] = defaultdict(
            lambda: deque(
                maxlen=self.MAX_HISTORY_MESSAGES
            )
        )

    # =====================================================
    # BASIC HELPERS
    # =====================================================

    @staticmethod
    def _clean_text(
        value: Any,
        maximum: int,
    ) -> str:
        text = str(value or "").strip()
        return text[:maximum] if len(text) > maximum else text

    @staticmethod
    def _safe_json(data: Any) -> str:
        try:
            encoded = json.dumps(
                data,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        except Exception:
            encoded = str(data)

        if len(encoded) > AIEngine.MAX_CONTEXT_CHARS:
            encoded = (
                encoded[: AIEngine.MAX_CONTEXT_CHARS]
                + "\n...[context truncated]"
            )

        return encoded

    @staticmethod
    def _api_error(response: httpx.Response) -> str:
        status = response.status_code

        try:
            data = response.json()
        except Exception:
            data = None

        if isinstance(data, dict):
            error = data.get("error")

            if isinstance(error, dict):
                message = error.get("message")
                error_type = error.get("type")
                code = error.get("code")

                details = str(message or "Unknown API error").strip()

                if error_type:
                    details = f"{details} [{error_type}]"
                if code:
                    details = f"{details} ({code})"

                return f"OpenAI API error {status}: {details}"

            message = data.get("message")
            if message:
                return f"OpenAI API error {status}: {message}"

        body = (response.text or "").strip()
        if len(body) > 500:
            body = body[:500] + "..."

        return (
            f"OpenAI API error {status}: "
            f"{body or 'Unknown error'}"
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # =====================================================
    # SYSTEM PROMPT
    # =====================================================

    @staticmethod
    def system_prompt() -> str:
        return """
You are RR Trader AI, the professional AI assistant inside
the RR Trader Live Crypto Trading Scanner.

Your job is to understand the user's actual request and answer
it directly.

CORE BEHAVIOR:
- Answer normal questions naturally.
- Explain RR Trader data and decisions when data is supplied.
- Explain LONG, SHORT and NO TRADE decisions.
- Explain confidence, market structure, MTF confirmation,
  support/resistance, liquidity, derivatives, liquidations,
  risk/reward and execution.
- Help with the RR Trader dashboard and technical project.
- Generate concise Binance Square posts when requested.
- Help with image-generation requests when the image capability
  is explicitly invoked.
- If the user asks for code, give complete usable code when
  enough information is available.

LIVE MARKET DATA RULES:
- For a specific live coin, use ONLY market data supplied by
  RR Trader in the request/context.
- Never invent current price, volume, funding, open interest,
  liquidation, order-book or trade results.
- If live data was not supplied, clearly say that the live RR
  Trader data is not attached and do not pretend to have it.
- Never guarantee profit or certainty.
- Deterministic RR Trader engines and risk gates are authoritative.
- AI must not override a deterministic risk gate.

ANSWER STYLE:
- Answer the actual question first.
- Be concise for simple questions and detailed when requested.
- Use natural, practical language.
- Do not repeat the question unnecessarily.
- Do not return a generic failure message when a useful answer
  can be given.
- Do not fabricate missing information.
"""

    # =====================================================
    # IMAGE REQUEST DETECTION
    # =====================================================

    @staticmethod
    def _looks_like_image_request(text: str) -> bool:
        value = text.lower().strip()

        explicit_patterns = (
            r"\bgenerate\s+(an?\s+)?image\b",
            r"\bcreate\s+(an?\s+)?image\b",
            r"\bmake\s+(an?\s+)?image\b",
            r"\bdraw\s+(an?\s+)?image\b",
            r"\bdesign\s+(an?\s+)?(an?\s+)?image\b",
            r"\bcreate\s+(an?\s+)?banner\b",
            r"\bmake\s+(an?\s+)?banner\b",
            r"\bdesign\s+(an?\s+)?banner\b",
            r"\bcreate\s+(an?\s+)?poster\b",
            r"\bmake\s+(an?\s+)?poster\b",
            r"\bcreate\s+(an?\s+)?thumbnail\b",
            r"\bmake\s+(an?\s+)?thumbnail\b",
        )

        return any(
            re.search(pattern, value)
            for pattern in explicit_patterns
        )

    # =====================================================
    # PROMPT BUILDING
    # =====================================================

    def build_prompt(
        self,
        *,
        user_request: str,
        context: dict[str, Any] | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        request = self._clean_text(
            user_request,
            self.MAX_USER_REQUEST_CHARS,
        )

        parts = [
            "USER REQUEST:",
            request,
        ]

        if history:
            parts.extend(
                [
                    "",
                    "RECENT CONVERSATION:",
                ]
            )

            for item in history:
                if not isinstance(item, dict):
                    continue

                role = str(
                    item.get("role", "user")
                ).upper().strip()

                content = self._clean_text(
                    item.get("content", ""),
                    self.MAX_HISTORY_CONTENT_CHARS,
                )

                if content:
                    parts.extend(
                        [
                            f"{role}:",
                            content,
                        ]
                    )

        if context:
            parts.extend(
                [
                    "",
                    "RR TRADER DATA:",
                    self._safe_json(context),
                ]
            )

        return "\n".join(parts)

    # =====================================================
    # RESPONSE EXTRACTION
    # =====================================================

    @classmethod
    def _extract_response_text(cls, data: Any) -> str:
        if not isinstance(data, dict):
            return ""

        output_text = data.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

        output = data.get("output", [])
        texts: list[str] = []

        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue

                content = item.get("content", [])
                if not isinstance(content, list):
                    continue

                for part in content:
                    if not isinstance(part, dict):
                        continue

                    text = part.get("text")
                    if isinstance(text, str) and text.strip():
                        texts.append(text.strip())

        return "\n".join(texts).strip()

    # =====================================================
    # RETRYABLE HTTP REQUEST
    # =====================================================

    async def _post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        timeout: float,
    ) -> dict[str, Any]:
        last_error = "Request failed."

        async with httpx.AsyncClient(
            timeout=timeout,
        ) as client:
            for attempt in range(self.MAX_RETRIES + 1):
                try:
                    response = await client.post(
                        url,
                        headers=self._headers(),
                        json=payload,
                    )

                    if response.status_code < 400:
                        data = response.json()

                        if not isinstance(data, dict):
                            raise RuntimeError(
                                "OpenAI returned an invalid JSON response."
                            )

                        return data

                    last_error = self._api_error(response)

                    if (
                        response.status_code
                        not in self.RETRY_STATUS_CODES
                    ):
                        raise RuntimeError(last_error)

                except (
                    httpx.TimeoutException,
                    httpx.NetworkError,
                    httpx.RemoteProtocolError,
                ) as exc:
                    last_error = (
                        f"OpenAI network error: {exc}"
                    )

                    if attempt >= self.MAX_RETRIES:
                        raise RuntimeError(last_error) from exc

                if attempt < self.MAX_RETRIES:
                    delay = min(
                        2 ** attempt,
                        8,
                    )
                    await asyncio.sleep(delay)

        raise RuntimeError(last_error)

    # =====================================================
    # OPENAI TEXT RESPONSE
    # =====================================================

    async def _openai_response(
        self,
        prompt: str,
    ) -> str:
        if not self.enabled:
            raise RuntimeError(
                "AI is disabled or OPENAI_API_KEY is missing."
            )

        clean_prompt = self._clean_text(
            prompt,
            self.MAX_CONTEXT_CHARS,
        )

        # Use the current Responses API shape:
        # instructions = system/developer behavior
        # input = user/application prompt
        payload: dict[str, Any] = {
            "model": self.text_model,
            "instructions": self.system_prompt(),
            "input": clean_prompt,
            "max_output_tokens": self.max_output_tokens,
        }

        data = await self._post_json(
            self.api_url,
            payload,
            timeout=self.timeout,
        )

        answer = self._extract_response_text(data)

        if not answer:
            raise RuntimeError(
                "OpenAI returned a successful response "
                "but no text output."
            )

        return answer

    # =====================================================
    # SESSION MEMORY
    # =====================================================

    def _get_history(
        self,
        session_id: str | None,
    ) -> list[dict[str, str]]:
        if not session_id:
            return []

        return list(self._sessions[session_id])

    def clear_session(
        self,
        session_id: str,
    ) -> dict[str, Any]:
        clean_id = self._clean_text(
            session_id,
            200,
        )

        if clean_id:
            self._sessions.pop(
                clean_id,
                None,
            )

        return {
            "success": True,
            "session_id": clean_id,
            "cleared": True,
        }

    # =====================================================
    # CHAT
    # =====================================================

    async def chat(
        self,
        *,
        user_request: str,
        context: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        request = self._clean_text(
            user_request,
            self.MAX_USER_REQUEST_CHARS,
        )

        if not request:
            return {
                "success": False,
                "enabled": self.enabled,
                "error": "Please provide a message.",
            }

        history = self._get_history(session_id)

        # Explicit image requests can use the image endpoint
        # directly while preserving the normal chat response shape.
        if self._looks_like_image_request(request):
            image_result = await self.generate_image(
                prompt=request,
            )

            if image_result.get("success"):
                answer = (
                    "Image generated successfully."
                )

                if session_id:
                    session = self._sessions[session_id]
                    session.append(
                        {
                            "role": "user",
                            "content": request,
                        }
                    )
                    session.append(
                        {
                            "role": "assistant",
                            "content": answer,
                        }
                    )

                return {
                    "success": True,
                    "enabled": True,
                    "provider": "openai",
                    "model": self.text_model,
                    "answer": answer,
                    "session_id": session_id,
                    "image": image_result.get("image"),
                    "image_url": image_result.get("image_url"),
                    "image_base64": image_result.get("image_base64"),
                    "image_data_url": image_result.get(
                        "image_data_url"
                    ),
                    "image_result": image_result,
                }

            # If image generation failed, return the actual reason
            # rather than a generic "couldn't complete" message.
            return {
                "success": False,
                "enabled": self.enabled,
                "provider": "openai",
                "model": self.image_model,
                "error": image_result.get(
                    "error",
                    "Image generation failed.",
                ),
                "session_id": session_id,
            }

        prompt = self.build_prompt(
            user_request=request,
            context=context,
            history=history,
        )

        if not self.enabled:
            return {
                "success": False,
                "enabled": False,
                "error": (
                    "AI is disabled. Set AI_ENABLED=true "
                    "and configure OPENAI_API_KEY."
                ),
                "session_id": session_id,
            }

        try:
            answer = await self._openai_response(
                prompt,
            )

            if session_id:
                session = self._sessions[session_id]

                session.append(
                    {
                        "role": "user",
                        "content": request,
                    }
                )

                session.append(
                    {
                        "role": "assistant",
                        "content": answer,
                    }
                )

            return {
                "success": True,
                "enabled": True,
                "provider": "openai",
                "model": self.text_model,
                "answer": answer,
                "session_id": session_id,
            }

        except Exception as exc:
            return {
                "success": False,
                "enabled": True,
                "provider": "openai",
                "model": self.text_model,
                "error": str(exc),
                "session_id": session_id,
            }

    # =====================================================
    # ANALYSIS EXPLANATION
    # =====================================================

    async def explain_analysis(
        self,
        analysis: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(analysis, dict):
            return {
                "success": False,
                "error": "Invalid analysis data.",
            }

        symbol = str(
            analysis.get("symbol", "UNKNOWN")
        ).upper()

        direction = str(
            analysis.get("direction", "NO TRADE")
        ).upper()

        request = (
            f"Explain the RR Trader analysis for {symbol}. "
            f"The deterministic direction is {direction}. "
            "Explain the strongest confirmations, weaknesses, "
            "conflicts, market structure, multi-timeframe "
            "confirmation, entry location, risk/reward and why "
            "the deterministic system reached this result. "
            "Do not invent missing information."
        )

        return await self.chat(
            user_request=request,
            context=analysis,
        )

    # =====================================================
    # POST GENERATION
    # =====================================================

    async def generate_post(
        self,
        analysis: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(analysis, dict):
            return {
                "success": False,
                "error": "Invalid analysis data.",
            }

        symbol = str(
            analysis.get("symbol", "")
        ).upper()

        direction = str(
            analysis.get("direction", "NO TRADE")
        ).upper()

        if direction not in {"LONG", "SHORT"}:
            return {
                "success": False,
                "error": (
                    "Post can only be generated "
                    "for LONG or SHORT signals."
                ),
            }

        request = f"""
Generate a short professional Binance Square community post
for this RR Trader signal.

Symbol: {symbol}
Direction: {direction}
Confidence: {analysis.get("confidence", 0)}%
Entry: {analysis.get("entry")}
Stop Loss: {analysis.get("stop_loss")}
TP1: {analysis.get("tp1")}
TP2: {analysis.get("tp2")}
TP3: {analysis.get("tp3")}

Writing rules:
- Use simple natural English.
- Sound like a real human trading creator.
- Do not sound like an AI.
- Do not invent market information.
- Do not add unrelated claims.
- Keep it concise.
- Use supplied RR Trader data only.
"""

        result = await self.chat(
            user_request=request,
            context=analysis,
        )

        if result.get("success"):
            result["symbol"] = symbol
            result["direction"] = direction

        return result

    # =====================================================
    # IMAGE GENERATION
    # =====================================================

    async def generate_image(
        self,
        *,
        prompt: str,
        size: str = "1536x1024",
        quality: str = "high",
        output_format: str = "png",
    ) -> dict[str, Any]:
        if not self.enabled:
            return {
                "success": False,
                "enabled": False,
                "error": (
                    "AI is disabled or OPENAI_API_KEY is missing."
                ),
            }

        clean_prompt = self._clean_text(
            prompt,
            self.MAX_IMAGE_PROMPT_CHARS,
        )

        if not clean_prompt:
            return {
                "success": False,
                "error": "Image prompt is required.",
            }

        allowed_sizes = {
            "1024x1024",
            "1536x1024",
            "1024x1536",
            "auto",
        }

        if size not in allowed_sizes:
            size = "1536x1024"

        allowed_formats = {
            "png",
            "jpeg",
            "webp",
        }

        if output_format not in allowed_formats:
            output_format = "png"

        quality = str(quality or "high").lower()
        if quality not in {"low", "medium", "high", "auto"}:
            quality = "high"

        payload: dict[str, Any] = {
            "model": self.image_model,
            "prompt": clean_prompt,
            "size": size,
            "quality": quality,
            "output_format": output_format,
        }

        try:
            data = await self._post_json(
                self.image_api_url,
                payload,
                timeout=max(
                    self.timeout,
                    120.0,
                ),
            )

            rows = data.get("data", [])

            if not isinstance(rows, list) or not rows:
                raise RuntimeError(
                    "Image API returned no image."
                )

            first = rows[0]

            if not isinstance(first, dict):
                raise RuntimeError(
                    "Invalid image result."
                )

            image_base64 = first.get("b64_json")
            image_url = first.get("url")

            result: dict[str, Any] = {
                "success": True,
                "enabled": True,
                "provider": "openai",
                "model": self.image_model,
                "size": size,
                "quality": quality,
                "format": output_format,
            }

            if (
                isinstance(image_base64, str)
                and image_base64.strip()
            ):
                clean_base64 = image_base64.strip()

                try:
                    base64.b64decode(
                        clean_base64,
                        validate=True,
                    )
                except (
                    ValueError,
                    binascii.Error,
                ) as exc:
                    raise RuntimeError(
                        "Image API returned invalid base64 image data."
                    ) from exc

                mime = {
                    "png": "image/png",
                    "jpeg": "image/jpeg",
                    "webp": "image/webp",
                }[output_format]

                data_url = (
                    f"data:{mime};base64,{clean_base64}"
                )

                result["image_base64"] = clean_base64
                result["image_data_url"] = data_url
                result["image"] = data_url

                return result

            if isinstance(image_url, str) and image_url.strip():
                clean_url = image_url.strip()
                result["image_url"] = clean_url
                result["image"] = clean_url
                return result

            raise RuntimeError(
                "Image API returned neither base64 image data "
                "nor image URL."
            )

        except Exception as exc:
            return {
                "success": False,
                "enabled": True,
                "provider": "openai",
                "model": self.image_model,
                "error": str(exc),
            }

    # =====================================================
    # GENERIC ALIASES
    # =====================================================

    async def create_image(
        self,
        prompt: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return await self.generate_image(
            prompt=prompt,
            **kwargs,
        )

    async def ask(
        self,
        user_request: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return await self.chat(
            user_request=user_request,
            **kwargs,
        )

    # =====================================================
    # STATUS
    # =====================================================

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "provider": "openai" if self.enabled else None,
            "text_model": self.text_model if self.enabled else None,
            "image_model": self.image_model if self.enabled else None,
            "responses_api": self.api_url,
            "image_api": self.image_api_url,
            "conversation_memory": True,
            "max_history_messages": self.MAX_HISTORY_MESSAGES,
            "retry_enabled": True,
            "max_retries": self.MAX_RETRIES,
        }


# =========================================================
# SHARED INSTANCES
# =========================================================

ai_engine = AIEngine()

# Backward compatibility:
# ai_routes.py imports:
#     from ..services.ai import ai_service
ai_service = ai_engine


__all__ = [
    "AIEngine",
    "ai_engine",
    "ai_service",
]
