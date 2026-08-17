from __future__ import annotations

import json
from typing import Any, Dict, Optional

import httpx

from app.config import Settings


class AIService:
    """
    RR Trader AI Assistant.

    Responsibilities:
    - Analyze market data
    - Explain LONG / SHORT signals
    - Review signal quality
    - Analyze TP / SL results
    - Answer questions about RR Trader signals
    """

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings()

        self.api_key = self.settings.openai_api_key
        self.model = self.settings.ai_model
        self.timeout = float(self.settings.ai_timeout)

        self.url = "https://api.openai.com/v1/responses"

    # =========================================================
    # BASIC REQUEST
    # =========================================================

    async def _request(
        self,
        prompt: str,
    ) -> str:

        if not self.settings.ai_enabled:
            return "AI assistant is disabled."

        if not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY is not configured."
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "input": prompt,
        }

        async with httpx.AsyncClient(
            timeout=self.timeout
        ) as client:

            response = await client.post(
                self.url,
                headers=headers,
                json=payload,
            )

            response.raise_for_status()

            data = response.json()

        # Responses API normally exposes output_text.
        output_text = data.get(
            "output_text"
        )

        if output_text:
            return str(output_text).strip()

        # Safe fallback if output_text is unavailable.
        output = data.get("output", [])

        texts = []

        for item in output:

            for content in item.get(
                "content",
                [],
            ):

                text = content.get("text")

                if text:
                    texts.append(
                        str(text)
                    )

        if texts:
            return "\n".join(
                texts
            ).strip()

        return "AI returned an empty response."

    # =========================================================
    # MARKET ANALYSIS
    # =========================================================

    async def analyze_market(
        self,
        market_data: Dict[str, Any],
    ) -> str:

        prompt = f"""
You are the AI analysis engine of RR Trader.

Analyze the following cryptocurrency market data.

Your job is NOT to blindly predict price.

Use the provided data to explain:
1. Market direction
2. Trend
3. Momentum
4. Volume
5. Liquidity
6. EMA structure
7. LONG or SHORT bias
8. Main risk
9. What confirmation is still needed

Be concise and practical.

Do not invent data that is not provided.

MARKET DATA:
{json.dumps(market_data, indent=2, default=str)}
"""

        return await self._request(
            prompt
        )

    # =========================================================
    # SIGNAL EXPLANATION
    # =========================================================

    async def explain_signal(
        self,
        signal: Dict[str, Any],
    ) -> str:

        prompt = f"""
You are RR Trader's signal explanation AI.

Explain why RR Trader generated this signal.

Analyze:
- LONG or SHORT direction
- Confidence
- EMA trend
- Momentum
- Volume
- Liquidity
- Price structure
- Risk
- Important invalidation level

Give the explanation in simple language.

Do not invent missing values.

SIGNAL:
{json.dumps(signal, indent=2, default=str)}
"""

        return await self._request(
            prompt
        )

    # =========================================================
    # SIGNAL REVIEW
    # =========================================================

    async def review_signal(
        self,
        signal: Dict[str, Any],
        current_market: Dict[str, Any],
    ) -> str:

        prompt = f"""
You are RR Trader's signal monitoring AI.

A previous trading signal is being monitored.

Compare the ORIGINAL SIGNAL with the CURRENT MARKET.

Determine whether the signal is:

- ACTIVE
- TP1_HIT
- TP2_HIT
- TP3_HIT
- SL_HIT
- INVALIDATED
- UNKNOWN

Important:
Do not claim TP or SL was hit unless the provided market data
actually supports it.

Explain briefly what happened.

ORIGINAL SIGNAL:
{json.dumps(signal, indent=2, default=str)}

CURRENT MARKET:
{json.dumps(current_market, indent=2, default=str)}
"""

        return await self._request(
            prompt
        )

    # =========================================================
    # SIGNAL RESULT ANALYSIS
    # =========================================================

    async def analyze_result(
        self,
        signal: Dict[str, Any],
        result: Dict[str, Any],
    ) -> str:

        prompt = f"""
You are RR Trader's post-trade analysis AI.

Review the completed trading signal.

Explain:
1. What happened
2. Which TP or SL was reached
3. Whether the original reasoning was correct
4. What confirmation worked
5. What could be improved

Do not invent information.

ORIGINAL SIGNAL:
{json.dumps(signal, indent=2, default=str)}

RESULT:
{json.dumps(result, indent=2, default=str)}
"""

        return await self._request(
            prompt
        )

    # =========================================================
    # USER QUESTION
    # =========================================================

    async def ask(
        self,
        question: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:

        context_text = ""

        if context:

            context_text = f"""
RR TRADER CURRENT CONTEXT:

{json.dumps(
    context,
    indent=2,
    default=str,
)}
"""

        prompt = f"""
You are RR Trader AI Assistant.

The user can ask you questions about:
- Crypto markets
- RR Trader signals
- LONG / SHORT signals
- Signal confidence
- TP / SL results
- Previous signals
- Market analysis
- Trading-system performance

Answer clearly and honestly.

If the required information is not present in the context,
say that the information is not available.

Do not invent prices, signals, TP hits, SL hits, or statistics.

USER QUESTION:
{question}

{context_text}
"""

        return await self._request(
            prompt
        )


__all__ = [
    "AIService",
]
