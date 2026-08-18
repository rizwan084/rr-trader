from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings


class AIEngine:
    """
    RR Trader AI engine foundation.

    Responsibilities:
    - Explain market analysis
    - Explain LONG / SHORT / NO TRADE
    - Explain confidence
    - Generate community posts
    - Later support AI memory/context
    - Never invent market data

    AI is disabled by default in the foundation phase.
    """

    def __init__(self) -> None:
        self.enabled = bool(
            settings.ai_enabled
            and settings.openai_api_key
        )

        self.api_url = (
            "https://api.openai.com/v1/responses"
        )

        self.timeout = float(
            settings.request_timeout
        )

    # =====================================================
    # SYSTEM PROMPT
    # =====================================================

    @staticmethod
    def system_prompt() -> str:
        return """
You are RR Trader AI.

You are the AI assistant inside a professional
cryptocurrency trading intelligence platform.

Your responsibilities:

1. Explain RR Trader market analysis.
2. Explain LONG, SHORT and NO TRADE decisions.
3. Explain confidence scores.
4. Explain the 24-point analysis.
5. Explain risk and execution gates.
6. Explain entries, stop loss and take profits.
7. Help generate community trading posts.
8. Use only market data supplied by RR Trader.
9. Never invent Binance prices, volumes, liquidations,
   funding, open interest or trade results.
10. Clearly state when required data is unavailable.
11. Do not claim a trade is profitable or guaranteed.
12. Prefer practical, concise explanations.

The AI must never replace the deterministic
RR Trader risk engine or trade gate.
"""

    # =====================================================
    # BUILD PROMPT
    # =====================================================

    def build_prompt(
        self,
        *,
        user_request: str,
        context: dict[str, Any] | None = None,
    ) -> str:

        prompt_parts = [
            "USER REQUEST:",
            str(
                user_request
                or ""
            ).strip(),
        ]

        if context:
            prompt_parts.extend(
                [
                    "",
                    "RR TRADER DATA:",
                    self._safe_json(
                        context
                    ),
                ]
            )

        return "\n".join(
            prompt_parts
        )

    # =====================================================
    # SAFE JSON
    # =====================================================

    @staticmethod
    def _safe_json(
        data: Any,
    ) -> str:

        try:
            import json

            return json.dumps(
                data,
                ensure_ascii=False,
                indent=2,
                default=str,
            )

        except Exception:
            return str(data)

    # =====================================================
    # OPENAI REQUEST
    # =====================================================

    async def _openai_response(
        self,
        prompt: str,
    ) -> str:

        if not self.enabled:
            raise RuntimeError(
                "AI is not enabled or OPENAI_API_KEY is missing."
            )

        headers = {
            "Authorization": (
                f"Bearer {settings.openai_api_key}"
            ),
            "Content-Type": "application/json",
        }

        payload = {
            "model": "gpt-5.6",
            "input": [
                {
                    "role": "developer",
                    "content": (
                        self.system_prompt()
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
        }

        async with httpx.AsyncClient(
            timeout=self.timeout
        ) as client:

            response = await client.post(
                self.api_url,
                headers=headers,
                json=payload,
            )

            response.raise_for_status()

            data = response.json()

        # -------------------------------------------------
        # Prefer Responses API output_text
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
        # Safe fallback extraction
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
                    ):
                        texts.append(
                            text
                        )

        if texts:
            return "\n".join(
                texts
            ).strip()

        return "AI returned no text."

    # =====================================================
    # CHAT
    # =====================================================

    async def chat(
        self,
        *,
        user_request: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:

        prompt = self.build_prompt(
            user_request=user_request,
            context=context,
        )

        if not self.enabled:

            return {
                "success": False,
                "enabled": False,
                "error": (
                    "AI is disabled. "
                    "Configure AI_ENABLED=true "
                    "and OPENAI_API_KEY."
                ),
            }

        try:

            answer = await self._openai_response(
                prompt
            )

            return {
                "success": True,
                "enabled": True,
                "answer": answer,
            }

        except Exception as exc:

            return {
                "success": False,
                "enabled": True,
                "error": str(exc),
            }

    # =====================================================
    # ANALYSIS EXPLANATION
    # =====================================================

    async def explain_analysis(
        self,
        analysis: dict[str, Any],
    ) -> dict[str, Any]:

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
            f"Final direction is {direction}. "
            f"Explain the strongest confirmations, "
            f"weaknesses and the reason for the final "
            f"trade decision."
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
Generate a short professional Binance community
post for this RR Trader signal.

Symbol: {symbol}
Direction: {direction}
Confidence: {confidence}%
Entry: {entry}
Stop Loss: {stop_loss}
TP1: {tp1}
TP2: {tp2}
TP3: {tp3}

Use simple natural English.
Do not invent any market information.
Do not add unrelated claims.
"""

        result = await self.chat(
            user_request=request,
            context=analysis,
        )

        if result.get(
            "success"
        ):

            result[
                "symbol"
            ] = symbol

            result[
                "direction"
            ] = direction

        return result

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
            "model": (
                "gpt-5.6"
                if self.enabled
                else None
            ),
        }


ai_engine = AIEngine()


__all__ = [
    "AIEngine",
    "ai_engine",
]
