from __future__ import annotations

import base64
import binascii
import json
from collections import defaultdict, deque
from typing import Any, Optional

import httpx

from app.core.config import settings


# =========================================================
# RR TRADER AI ENGINE
#
# Responsibilities:
# - General AI chat
# - RR Trader analysis explanation
# - LONG / SHORT / NO TRADE explanation
# - Confidence explanation
# - Binance community post generation
# - Image generation
# - Session conversation context
# - Safe API error handling
# - Backward compatibility with ai_service
#
# The deterministic trading engines remain authoritative.
# AI explains and assists; it does NOT override risk gates.
# =========================================================


class AIEngine:

    # =====================================================
    # DEFAULTS
    # =====================================================

    DEFAULT_TEXT_MODEL = "gpt-5.6"
    DEFAULT_IMAGE_MODEL = "gpt-image-2"

    RESPONSES_URL = (
        "https://api.openai.com/v1/responses"
    )

    IMAGES_URL = (
        "https://api.openai.com/v1/images/generations"
    )

    MAX_HISTORY_MESSAGES = 20
    MAX_CONTEXT_CHARS = 120_000
    MAX_USER_REQUEST_CHARS = 20_000

    # =====================================================
    # INIT
    # =====================================================

    def __init__(self) -> None:

        self.api_key = str(
            getattr(
                settings,
                "openai_api_key",
                "",
            )
            or ""
        ).strip()

        self.enabled = bool(
            getattr(
                settings,
                "ai_enabled",
                True,
            )
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

        self.timeout = float(
            getattr(
                settings,
                "request_timeout",
                60.0,
            )
            or 60.0
        )

        self.max_output_tokens = int(
            getattr(
                settings,
                "ai_max_output_tokens",
                2000,
            )
            or 2000
        )

        self.temperature = getattr(
            settings,
            "ai_temperature",
            None,
        )

        # -------------------------------------------------
        # In-memory conversation history.
        #
        # This is intentionally bounded so the service
        # cannot grow indefinitely.
        # -------------------------------------------------

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
        maximum: int = 20_000,
    ) -> str:

        text = str(
            value or ""
        ).strip()

        if len(text) > maximum:
            return text[:maximum]

        return text

    @staticmethod
    def _safe_float(
        value: Any,
        default: float = 0.0,
    ) -> float:

        try:
            return float(value)

        except (
            TypeError,
            ValueError,
        ):
            return default

    @staticmethod
    def _safe_int(
        value: Any,
        default: int = 0,
    ) -> int:

        try:
            return int(value)

        except (
            TypeError,
            ValueError,
        ):
            return default

    # =====================================================
    # SAFE JSON
    # =====================================================

    @staticmethod
    def _safe_json(
        data: Any,
    ) -> str:

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
                encoded[
                    :AIEngine.MAX_CONTEXT_CHARS
                ]
                + "\n...[context truncated]"
            )

        return encoded

    # =====================================================
    # API HEADERS
    # =====================================================

    def _headers(self) -> dict[str, str]:

        return {
            "Authorization": (
                f"Bearer {self.api_key}"
            ),
            "Content-Type": (
                "application/json"
            ),
        }

    # =====================================================
    # SYSTEM PROMPT
    # =====================================================

    @staticmethod
    def system_prompt() -> str:

        return """
You are RR Trader AI.

You are the AI assistant inside a professional
cryptocurrency trading intelligence platform.

Your job is to understand the user's request and
answer the actual question directly.

CORE RESPONSIBILITIES:

1. Answer general user questions clearly.
2. Explain RR Trader market analysis.
3. Explain LONG, SHORT and NO TRADE decisions.
4. Explain confidence scores.
5. Explain the 24-point analysis framework.
6. Explain market structure.
7. Explain multi-timeframe confirmation.
8. Explain support and resistance.
9. Explain liquidity and order-book information.
10. Explain derivatives and liquidation information.
11. Explain entries, stop loss and take profits when supplied.
12. Generate professional community posts when requested.
13. Help the user understand the RR Trader dashboard.
14. Help explain technical/system information when requested.
15. Generate image requests when the image-generation capability
    is explicitly requested.

TRADING DATA RULES:

- Use only market data supplied by RR Trader when discussing
  a specific live market.
- Never invent Binance prices.
- Never invent volume.
- Never invent funding rate.
- Never invent open interest.
- Never invent liquidation data.
- Never invent trade results.
- Never claim guaranteed profit.
- Never claim a trade is certain.
- Clearly say when required market data is unavailable.
- The deterministic RR Trader engines remain authoritative.
- Never override a deterministic risk gate simply because
  an AI opinion appears bullish or bearish.

ANSWER STYLE:

- Answer the user's actual question first.
- Do not produce generic error messages when a useful answer
  can be given.
- Be practical.
- Be concise when the question is simple.
- Be detailed when the user asks for detailed analysis.
- Use simple natural language.
- Do not unnecessarily repeat the user's question.
- If the user asks for code, provide complete usable code.
- If the user asks for an explanation, explain instead of
  returning a trading signal.
"""

    # =====================================================
    # BUILD PROMPT
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

                if not isinstance(
                    item,
                    dict,
                ):
                    continue

                role = str(
                    item.get(
                        "role",
                        "user",
                    )
                ).upper()

                content = self._clean_text(
                    item.get(
                        "content",
                        "",
                    ),
                    8_000,
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
                    self._safe_json(
                        context
                    ),
                ]
            )

        return "\n".join(parts)

    # =====================================================
    # RESPONSE TEXT EXTRACTION
    # =====================================================

    @classmethod
    def _extract_response_text(
        cls,
        data: Any,
    ) -> str:

        if not isinstance(
            data,
            dict,
        ):
            return ""

        # -------------------------------------------------
        # Preferred Responses API field.
        # -------------------------------------------------

        output_text = data.get(
            "output_text"
        )

        if isinstance(
            output_text,
            str,
        ) and output_text.strip():

            return output_text.strip()

        # -------------------------------------------------
        # Generic output traversal.
        # -------------------------------------------------

        output = data.get(
            "output",
            [],
        )

        texts: list[str] = []

        if isinstance(
            output,
            list,
        ):

            for item in output:

                if not isinstance(
                    item,
                    dict,
                ):
                    continue

                content = item.get(
                    "content",
                    [],
                )

                if not isinstance(
                    content,
                    list,
                ):
                    continue

                for part in content:

                    if not isinstance(
                        part,
                        dict,
                    ):
                        continue

                    text = part.get(
                        "text"
                    )

                    if isinstance(
                        text,
                        str,
                    ) and text.strip():

                        texts.append(
                            text.strip()
                        )

        if texts:

            return "\n".join(
                texts
            ).strip()

        return ""

    # =====================================================
    # API ERROR EXTRACTION
    # =====================================================

    @staticmethod
    def _api_error(
        response: httpx.Response,
    ) -> str:

        status = response.status_code

        try:

            data = response.json()

        except Exception:

            data = None

        if isinstance(
            data,
            dict,
        ):

            error = data.get(
                "error"
            )

            if isinstance(
                error,
                dict,
            ):

                message = error.get(
                    "message"
                )

                if message:

                    return (
                        f"OpenAI API error "
                        f"{status}: {message}"
                    )

            message = data.get(
                "message"
            )

            if message:

                return (
                    f"OpenAI API error "
                    f"{status}: {message}"
                )

        text = (
            response.text
            or ""
        ).strip()

        if len(text) > 500:
            text = text[:500]

        return (
            f"OpenAI API error "
            f"{status}: {text or 'Unknown error'}"
        )

    # =====================================================
    # OPENAI TEXT RESPONSE
    # =====================================================

    async def _openai_response(
        self,
        prompt: str,
        *,
        history: list[dict[str, str]] | None = None,
    ) -> str:

        if not self.enabled:

            raise RuntimeError(
                "AI is disabled or "
                "OPENAI_API_KEY is missing."
            )

        clean_prompt = self._clean_text(
            prompt,
            self.MAX_CONTEXT_CHARS,
        )

        payload: dict[str, Any] = {
            "model": self.text_model,
            "input": [
                {
                    "role": "developer",
                    "content": (
                        self.system_prompt()
                    ),
                },
                {
                    "role": "user",
                    "content": clean_prompt,
                },
            ],
            "max_output_tokens": (
                self.max_output_tokens
            ),
        }

        # -------------------------------------------------
        # Keep compatibility with configurations that
        # expose temperature.
        # -------------------------------------------------

        if self.temperature is not None:

            try:

                payload["temperature"] = float(
                    self.temperature
                )

            except (
                TypeError,
                ValueError,
            ):

                pass

        async with httpx.AsyncClient(
            timeout=self.timeout
        ) as client:

            response = await client.post(
                self.api_url,
                headers=self._headers(),
                json=payload,
            )

            if response.status_code >= 400:

                raise RuntimeError(
                    self._api_error(
                        response
                    )
                )

            data = response.json()

        answer = self._extract_response_text(
            data
        )

        if not answer:

            raise RuntimeError(
                "OpenAI returned a successful "
                "response but no text output."
            )

        return answer

    # =====================================================
    # SESSION HISTORY
    # =====================================================

    def _get_history(
        self,
        session_id: str | None,
    ) -> list[dict[str, str]]:

        if not session_id:

            return []

        return list(
            self._sessions[
                session_id
            ]
        )

    def clear_session(
        self,
        session_id: str,
    ) -> dict[str, Any]:

        session_id = self._clean_text(
            session_id,
            200,
        )

        if session_id:

            self._sessions.pop(
                session_id,
                None,
            )

        return {
            "success": True,
            "session_id": session_id,
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
                "error": (
                    "Please provide a message."
                ),
            }

        history = self._get_history(
            session_id
        )

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
                    "AI is disabled. "
                    "Set AI_ENABLED=true and "
                    "configure OPENAI_API_KEY."
                ),
            }

        try:

            answer = await self._openai_response(
                prompt,
                history=history,
            )

            if session_id:

                session = self._sessions[
                    session_id
                ]

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

        if not isinstance(
            analysis,
            dict,
        ):

            return {
                "success": False,
                "error": (
                    "Invalid analysis data."
                ),
            }

        symbol = str(
            analysis.get(
                "symbol",
                "UNKNOWN",
            )
        ).upper()

        direction = str(
            analysis.get(
                "direction",
                "NO TRADE",
            )
        ).upper()

        request = (
            f"Explain the RR Trader analysis "
            f"for {symbol}. "
            f"The current deterministic direction "
            f"is {direction}. "
            f"Explain the strongest confirmations, "
            f"weaknesses, conflicts, market structure, "
            f"multi-timeframe confirmation, entry location, "
            f"risk/reward and why the deterministic system "
            f"reached this result. "
            f"Do not invent missing information."
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

        if not isinstance(
            analysis,
            dict,
        ):

            return {
                "success": False,
                "error": (
                    "Invalid analysis data."
                ),
            }

        symbol = str(
            analysis.get(
                "symbol",
                "",
            )
        ).upper()

        direction = str(
            analysis.get(
                "direction",
                "NO TRADE",
            )
        ).upper()

        confidence = analysis.get(
            "confidence",
            0,
        )

        entry = analysis.get(
            "entry"
        )

        stop_loss = analysis.get(
            "stop_loss"
        )

        tp1 = analysis.get(
            "tp1"
        )

        tp2 = analysis.get(
            "tp2"
        )

        tp3 = analysis.get(
            "tp3"
        )

        if direction not in {
            "LONG",
            "SHORT",
        }:

            return {
                "success": False,
                "error": (
                    "Post can only be generated "
                    "for LONG or SHORT signals."
                ),
            }

        request = f"""
Generate a short professional Binance Square
community post for this RR Trader signal.

Symbol: {symbol}
Direction: {direction}
Confidence: {confidence}%
Entry: {entry}
Stop Loss: {stop_loss}
TP1: {tp1}
TP2: {tp2}
TP3: {tp3}

Writing rules:

- Use simple natural English.
- Sound like a real human trading creator.
- Do not sound like an AI.
- Do not invent market information.
- Do not add unrelated claims.
- Keep it concise.
- Use the supplied RR Trader data only.
"""

        result = await self.chat(
            user_request=request,
            context=analysis,
        )

        if result.get(
            "success"
        ):

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
                    "AI is disabled or "
                    "OPENAI_API_KEY is missing."
                ),
            }

        clean_prompt = self._clean_text(
            prompt,
            10_000,
        )

        if not clean_prompt:

            return {
                "success": False,
                "error": (
                    "Image prompt is required."
                ),
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

        payload: dict[str, Any] = {
            "model": self.image_model,
            "prompt": clean_prompt,
            "size": size,
            "quality": quality,
            "output_format": output_format,
        }

        try:

            async with httpx.AsyncClient(
                timeout=max(
                    self.timeout,
                    120.0,
                )
            ) as client:

                response = await client.post(
                    self.image_api_url,
                    headers=self._headers(),
                    json=payload,
                )

                if response.status_code >= 400:

                    raise RuntimeError(
                        self._api_error(
                            response
                        )
                    )

                data = response.json()

            if not isinstance(
                data,
                dict,
            ):

                raise RuntimeError(
                    "Invalid image API response."
                )

            rows = data.get(
                "data",
                [],
            )

            if not isinstance(
                rows,
                list,
            ) or not rows:

                raise RuntimeError(
                    "Image API returned no image."
                )

            first = rows[0]

            if not isinstance(
                first,
                dict,
            ):

                raise RuntimeError(
                    "Invalid image result."
                )

            image_base64 = first.get(
                "b64_json"
            )

            image_url = first.get(
                "url"
            )

            result: dict[str, Any] = {
                "success": True,
                "enabled": True,
                "provider": "openai",
                "model": self.image_model,
                "size": size,
                "quality": quality,
                "format": output_format,
            }

            # -------------------------------------------------
            # Base64 response.
            # -------------------------------------------------

            if isinstance(
                image_base64,
                str,
            ) and image_base64.strip():

                clean_base64 = (
                    image_base64.strip()
                )

                # Validate that the returned base64 is
                # actually decodable before exposing it.
                try:

                    base64.b64decode(
                        clean_base64,
                        validate=True,
                    )

                except (
                    ValueError,
                    binascii.Error,
                ):

                    raise RuntimeError(
                        "Image API returned invalid "
                        "base64 image data."
                    )

                mime = (
                    "image/png"
                    if output_format == "png"
                    else (
                        "image/jpeg"
                        if output_format == "jpeg"
                        else "image/webp"
                    )
                )

                result[
                    "image_base64"
                ] = clean_base64

                result[
                    "image_data_url"
                ] = (
                    f"data:{mime};base64,"
                    f"{clean_base64}"
                )

                result[
                    "image"
                ] = (
                    f"data:{mime};base64,"
                    f"{clean_base64}"
                )

                return result

            # -------------------------------------------------
            # URL response.
            # -------------------------------------------------

            if isinstance(
                image_url,
                str,
            ) and image_url.strip():

                result[
                    "image_url"
                ] = image_url.strip()

                result[
                    "image"
                ] = image_url.strip()

                return result

            raise RuntimeError(
                "Image API returned neither "
                "base64 image data nor image URL."
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
    # GENERIC IMAGE ALIAS
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

    # =====================================================
    # STATUS
    # =====================================================

    def status(
        self,
    ) -> dict[str, Any]:

        return {
            "enabled": self.enabled,
            "provider": (
                "openai"
                if self.enabled
                else None
            ),
            "text_model": (
                self.text_model
                if self.enabled
                else None
            ),
            "image_model": (
                self.image_model
                if self.enabled
                else None
            ),
            "responses_api": (
                self.api_url
            ),
            "image_api": (
                self.image_api_url
            ),
            "conversation_memory": True,
            "max_history_messages": (
                self.MAX_HISTORY_MESSAGES
            ),
        }


# =========================================================
# SHARED INSTANCES
# =========================================================

ai_engine = AIEngine()

# IMPORTANT:
#
# ai_routes.py currently imports:
#
#     from ..services.ai import ai_service
#
# Therefore this compatibility alias MUST exist.
#
ai_service = ai_engine


# =========================================================
# EXPORTS
# =========================================================

__all__ = [
    "AIEngine",
    "ai_engine",
    "ai_service",
]
