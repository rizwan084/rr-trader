from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from app.config import Settings


class AIMemory:
    """
    Persistent RR Trader AI memory.

    Stores:
    - Conversations
    - User questions
    - AI answers
    - Important remembered facts
    - Signal-related context

    Memory is stored locally as JSON for now.
    Later this can be moved to Supabase/PostgreSQL.
    """

    def __init__(
        self,
        path: Optional[str] = None,
        max_messages: int = 2000,
    ):
        self.path = Path(
            path
            or os.getenv(
                "AI_MEMORY_FILE",
                "data/ai_memory.json",
            )
        )

        self.max_messages = max_messages

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.data: Dict[str, Any] = {
            "conversations": {},
            "memories": [],
        }

        self._load()

    # ---------------------------------------------------------
    # LOAD
    # ---------------------------------------------------------

    def _load(self) -> None:

        if not self.path.exists():
            return

        try:
            with self.path.open(
                "r",
                encoding="utf-8",
            ) as file:
                loaded = json.load(file)

            if isinstance(loaded, dict):
                self.data.update(loaded)

        except Exception:
            # Never crash RR Trader because memory file is damaged.
            self.data = {
                "conversations": {},
                "memories": [],
            }

    # ---------------------------------------------------------
    # SAVE
    # ---------------------------------------------------------

    def _save(self) -> None:

        temporary = self.path.with_suffix(
            ".tmp"
        )

        with temporary.open(
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                self.data,
                file,
                indent=2,
                ensure_ascii=False,
                default=str,
            )

        temporary.replace(self.path)

    # ---------------------------------------------------------
    # CONVERSATION
    # ---------------------------------------------------------

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
    ) -> None:

        conversations = self.data.setdefault(
            "conversations",
            {},
        )

        conversation = conversations.setdefault(
            conversation_id,
            [],
        )

        conversation.append(
            {
                "id": str(uuid.uuid4()),
                "role": role,
                "content": content,
                "created_at": utc_now(),
            }
        )

        # Prevent unlimited growth.
        if len(conversation) > self.max_messages:
            conversations[
                conversation_id
            ] = conversation[
                -self.max_messages:
            ]

        self._save()

    # ---------------------------------------------------------
    # RECENT CONVERSATION
    # ---------------------------------------------------------

    def recent_messages(
        self,
        conversation_id: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:

        conversation = (
            self.data
            .get("conversations", {})
            .get(conversation_id, [])
        )

        return conversation[-limit:]

    # ---------------------------------------------------------
    # REMEMBER
    # ---------------------------------------------------------

    def remember(
        self,
        text: str,
        category: str = "general",
    ) -> Dict[str, Any]:

        item = {
            "id": str(uuid.uuid4()),
            "category": category,
            "text": text.strip(),
            "created_at": utc_now(),
        }

        self.data.setdefault(
            "memories",
            [],
        ).append(item)

        self._save()

        return item

    # ---------------------------------------------------------
    # RECALL
    # ---------------------------------------------------------

    def recall(
        self,
        query: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:

        memories = self.data.get(
            "memories",
            [],
        )

        query_words = {
            word.lower()
            for word in re.findall(
                r"\w+",
                query,
            )
            if len(word) > 2
        }

        scored = []

        for memory in memories:

            text = str(
                memory.get("text", "")
            ).lower()

            score = sum(
                1
                for word in query_words
                if word in text
            )

            if score > 0:
                scored.append(
                    (
                        score,
                        memory,
                    )
                )

        scored.sort(
            key=lambda item: (
                item[0],
                item[1].get(
                    "created_at",
                    "",
                ),
            ),
            reverse=True,
        )

        return [
            item[1]
            for item in scored[:limit]
        ]

    # ---------------------------------------------------------
    # ALL MEMORY
    # ---------------------------------------------------------

    def all_memories(
        self,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:

        return self.data.get(
            "memories",
            [],
        )[-limit:]


# =============================================================
# TIME
# =============================================================

def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


# =============================================================
# AI SERVICE
# =============================================================

class AIService:
    """
    RR Trader Multi-Model AI Agent.

    Supported providers:

    - OpenAI / GPT
    - Anthropic / Claude
    - Google / Gemini
    - xAI / Grok
    - Azure/OpenAI-compatible endpoints

    Features:

    - Normal AI conversation
    - Persistent memory
    - Conversation history
    - Market analysis
    - Signal explanation
    - Signal monitoring analysis
    - TP/SL result analysis
    - Model switching
    - Automatic provider selection
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        memory: Optional[AIMemory] = None,
    ):
        self.settings = settings or Settings()

        # -----------------------------------------------------
        # GENERAL AI SETTINGS
        # -----------------------------------------------------

        self.enabled = self._get_bool(
            "ai_enabled",
            "AI_ENABLED",
            True,
        )

        self.provider = str(
            self._get(
                "ai_provider",
                "AI_PROVIDER",
                "openai",
            )
        ).lower().strip()

        self.model = str(
            self._get(
                "ai_model",
                "AI_MODEL",
                "gpt-5.6",
            )
        )

        self.timeout = float(
            self._get(
                "ai_timeout",
                "AI_TIMEOUT",
                60,
            )
        )

        # -----------------------------------------------------
        # API KEYS
        # -----------------------------------------------------

        self.openai_api_key = self._get(
            "openai_api_key",
            "OPENAI_API_KEY",
            "",
        )

        self.anthropic_api_key = self._get(
            "anthropic_api_key",
            "ANTHROPIC_API_KEY",
            "",
        )

        self.gemini_api_key = self._get(
            "gemini_api_key",
            "GEMINI_API_KEY",
            "",
        )

        self.xai_api_key = self._get(
            "xai_api_key",
            "XAI_API_KEY",
            "",
        )

        # -----------------------------------------------------
        # ENDPOINTS
        # -----------------------------------------------------

        self.openai_url = os.getenv(
            "OPENAI_API_URL",
            "https://api.openai.com/v1/responses",
        )

        self.anthropic_url = os.getenv(
            "ANTHROPIC_API_URL",
            "https://api.anthropic.com/v1/messages",
        )

        self.gemini_url = os.getenv(
            "GEMINI_API_URL",
            "https://generativelanguage.googleapis.com/v1beta",
        )

        self.xai_url = os.getenv(
            "XAI_API_URL",
            "https://api.x.ai/v1/chat/completions",
        )

        # -----------------------------------------------------
        # MEMORY
        # -----------------------------------------------------

        self.memory = memory or AIMemory()

    # =========================================================
    # SETTINGS HELPERS
    # =========================================================

    def _get(
        self,
        attribute: str,
        environment: str,
        default: Any,
    ) -> Any:

        value = getattr(
            self.settings,
            attribute,
            None,
        )

        if value is not None:
            return value

        return os.getenv(
            environment,
            default,
        )

    def _get_bool(
        self,
        attribute: str,
        environment: str,
        default: bool,
    ) -> bool:

        value = self._get(
            attribute,
            environment,
            default,
        )

        if isinstance(value, bool):
            return value

        return str(value).lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    # =========================================================
    # PROVIDER AUTO DETECTION
    # =========================================================

    def _resolve_provider(
        self,
        provider: Optional[str] = None,
    ) -> str:

        selected = (
            provider
            or self.provider
        ).lower().strip()

        if selected != "auto":
            return selected

        if self.openai_api_key:
            return "openai"

        if self.anthropic_api_key:
            return "anthropic"

        if self.gemini_api_key:
            return "gemini"

        if self.xai_api_key:
            return "xai"

        raise ValueError(
            "No AI provider API key is configured."
        )

    # =========================================================
    # MODEL DEFAULTS
    # =========================================================

    def _model_for(
        self,
        provider: str,
        model: Optional[str] = None,
    ) -> str:

        if model:
            return model

        if self.model:
            return self.model

        defaults = {
            "openai": "gpt-5.6",
            "anthropic": "claude-sonnet-4-6",
            "gemini": "gemini-3.6-flash",
            "xai": "grok-4.5",
        }

        return defaults.get(
            provider,
            "gpt-5.6",
        )

    # =========================================================
    # SYSTEM PROMPT
    # =========================================================

    def _system_prompt(self) -> str:

        return """
You are RR Trader AI.

You are the central AI assistant of an advanced cryptocurrency
trading platform.

Your responsibilities include:

1. Answer normal user questions clearly.
2. Understand crypto market terminology.
3. Explain LONG and SHORT signals.
4. Explain confidence scores.
5. Analyze market structure.
6. Analyze EMA, momentum and volume.
7. Analyze liquidity when data is provided.
8. Analyze Futures data when provided.
9. Analyze Spot data when provided.
10. Review previous RR Trader signals.
11. Explain TP1, TP2, TP3 and SL results.
12. Analyze trading-system performance.
13. Remember useful information from previous conversations.
14. Never invent market prices or trading results.
15. Clearly say when required data is unavailable.
16. Prefer actual RR Trader/Binance data over assumptions.
17. Be practical and concise unless the user asks for detail.

IMPORTANT TRADING RULE:

Never claim that a TP or SL was hit unless the application has
verified it using actual market data.

The AI is allowed to reason about supplied data, but it must not
fabricate Binance data.

When a user asks for an action that requires an application tool,
the AI should identify what tool/action is required. The actual
application will execute the tool.
"""

    # =========================================================
    # BUILD CONTEXT
    # =========================================================

    def _build_context(
        self,
        conversation_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:

        history = self.memory.recent_messages(
            conversation_id,
            limit=20,
        )

        memories = self.memory.all_memories(
            limit=50,
        )

        parts = []

        if history:
            parts.append(
                "RECENT CONVERSATION:\n"
                + json.dumps(
                    history,
                    indent=2,
                    ensure_ascii=False,
                    default=str,
                )
            )

        if memories:
            parts.append(
                "LONG-TERM MEMORY:\n"
                + json.dumps(
                    memories,
                    indent=2,
                    ensure_ascii=False,
                    default=str,
                )
            )

        if context:
            parts.append(
                "CURRENT RR TRADER DATA:\n"
                + json.dumps(
                    context,
                    indent=2,
                    ensure_ascii=False,
                    default=str,
                )
            )

        return "\n\n".join(parts)

    # =========================================================
    # OPENAI / GPT
    # =========================================================

    async def _openai(
        self,
        prompt: str,
        model: str,
    ) -> str:

        if not self.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY is not configured."
            )

        headers = {
            "Authorization": (
                f"Bearer {self.openai_api_key}"
            ),
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "input": [
                {
                    "role": "developer",
                    "content": self._system_prompt(),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
        }

        data = await self._post_json(
            self.openai_url,
            headers,
            payload,
        )

        text = data.get(
            "output_text"
        )

        if text:
            return str(text).strip()

        return self._extract_openai_text(
            data
        )

    # =========================================================
    # ANTHROPIC / CLAUDE
    # =========================================================

    async def _anthropic(
        self,
        prompt: str,
        model: str,
    ) -> str:

        if not self.anthropic_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is not configured."
            )

        headers = {
            "x-api-key": (
                self.anthropic_api_key
            ),
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        payload = {
            "model": model,
            "max_tokens": 4096,
            "system": self._system_prompt(),
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        }

        data = await self._post_json(
            self.anthropic_url,
            headers,
            payload,
        )

        content = data.get(
            "content",
            [],
        )

        texts = []

        for item in content:

            if item.get("type") == "text":

                text = item.get("text")

                if text:
                    texts.append(
                        str(text)
                    )

        return "\n".join(texts).strip()

    # =========================================================
    # GOOGLE / GEMINI
    # =========================================================

    async def _gemini(
        self,
        prompt: str,
        model: str,
    ) -> str:

        if not self.gemini_api_key:
            raise ValueError(
                "GEMINI_API_KEY is not configured."
            )

        url = (
            f"{self.gemini_url}"
            f"/models/{model}:generateContent"
        )

        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": (
                self.gemini_api_key
            ),
        }

        payload = {
            "systemInstruction": {
                "parts": [
                    {
                        "text": self._system_prompt()
                    }
                ]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": prompt
                        }
                    ],
                }
            ],
        }

        data = await self._post_json(
            url,
            headers,
            payload,
        )

        candidates = data.get(
            "candidates",
            [],
        )

        texts = []

        for candidate in candidates:

            content = candidate.get(
                "content",
                {},
            )

            for part in content.get(
                "parts",
                [],
            ):

                text = part.get("text")

                if text:
                    texts.append(
                        str(text)
                    )

        return "\n".join(texts).strip()

    # =========================================================
    # xAI / GROK
    # =========================================================

    async def _xai(
        self,
        prompt: str,
        model: str,
    ) -> str:

        if not self.xai_api_key:
            raise ValueError(
                "XAI_API_KEY is not configured."
            )

        headers = {
            "Authorization": (
                f"Bearer {self.xai_api_key}"
            ),
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": self._system_prompt(),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
        }

        data = await self._post_json(
            self.xai_url,
            headers,
            payload,
        )

        choices = data.get(
            "choices",
            [],
        )

        if not choices:
            return ""

        message = choices[0].get(
            "message",
            {},
        )

        return str(
            message.get(
                "content",
                "",
            )
        ).strip()

    # =========================================================
    # HTTP
    # =========================================================

    async def _post_json(
        self,
        url: str,
        headers: Dict[str, str],
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:

        async with httpx.AsyncClient(
            timeout=self.timeout
        ) as client:

            response = await client.post(
                url,
                headers=headers,
                json=payload,
            )

            response.raise_for_status()

            data = response.json()

        if not isinstance(data, dict):
            raise ValueError(
                "AI provider returned invalid JSON."
            )

        return data

    # =========================================================
    # OPENAI TEXT EXTRACTION
    # =========================================================

    @staticmethod
    def _extract_openai_text(
        data: Dict[str, Any],
    ) -> str:

        output = data.get(
            "output",
            [],
        )

        texts = []

        for item in output:

            for content in item.get(
                "content",
                [],
            ):

                text = content.get(
                    "text"
                )

                if text:
                    texts.append(
                        str(text)
                    )

        return "\n".join(
            texts
        ).strip()

    # =========================================================
    # MAIN GENERATE
    # =========================================================

    async def generate(
        self,
        prompt: str,
        *,
        conversation_id: str = "default",
        context: Optional[Dict[str, Any]] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        save_memory: bool = True,
    ) -> str:

        if not self.enabled:
            return "AI assistant is disabled."

        selected_provider = self._resolve_provider(
            provider
        )

        selected_model = self._model_for(
            selected_provider,
            model,
        )

        full_context = self._build_context(
            conversation_id,
            context,
        )

        final_prompt = f"""
{full_context}

USER REQUEST:
{prompt}
"""

        # Save user message first.
        if save_memory:
            self.memory.add_message(
                conversation_id,
                "user",
                prompt,
            )

        try:

            if selected_provider == "openai":
                answer = await self._openai(
                    final_prompt,
                    selected_model,
                )

            elif selected_provider in {
                "anthropic",
                "claude",
            }:
                answer = await self._anthropic(
                    final_prompt,
                    selected_model,
                )

            elif selected_provider in {
                "gemini",
                "google",
            }:
                answer = await self._gemini(
                    final_prompt,
                    selected_model,
                )

            elif selected_provider in {
                "xai",
                "grok",
            }:
                answer = await self._xai(
                    final_prompt,
                    selected_model,
                )

            else:
                raise ValueError(
                    f"Unsupported AI provider: "
                    f"{selected_provider}"
                )

        except Exception as exc:

            answer = (
                "AI provider error: "
                f"{exc}"
            )

        if save_memory:
            self.memory.add_message(
                conversation_id,
                "assistant",
                answer,
            )

        return answer

    # =========================================================
    # ASK
    # =========================================================

    async def ask(
        self,
        question: str,
        context: Optional[Dict[str, Any]] = None,
        conversation_id: str = "default",
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> str:

        return await self.generate(
            question,
            conversation_id=conversation_id,
            context=context,
            provider=provider,
            model=model,
        )

    # =========================================================
    # REMEMBER SOMETHING
    # =========================================================

    def remember(
        self,
        text: str,
        category: str = "general",
    ) -> Dict[str, Any]:

        return self.memory.remember(
            text=text,
            category=category,
        )

    # =========================================================
    # RECALL MEMORY
    # =========================================================

    def recall(
        self,
        query: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:

        return self.memory.recall(
            query=query,
            limit=limit,
        )

    # =========================================================
    # MARKET ANALYSIS
    # =========================================================

    async def analyze_market(
        self,
        market_data: Dict[str, Any],
        conversation_id: str = "market",
    ) -> str:

        return await self.generate(
            """
Analyze this cryptocurrency market data.

Explain:
- Direction
- Trend
- Momentum
- Volume
- Liquidity
- EMA structure
- LONG/SHORT bias
- Main risk
- Required confirmation

Do not invent missing information.
""",
            conversation_id=conversation_id,
            context=market_data,
        )

    # =========================================================
    # SIGNAL EXPLANATION
    # =========================================================

    async def explain_signal(
        self,
        signal: Dict[str, Any],
        conversation_id: str = "signals",
    ) -> str:

        return await self.generate(
            """
Explain why RR Trader generated this signal.

Review:
- Direction
- Confidence
- EMA
- Momentum
- Volume
- Liquidity
- Price structure
- Entry
- Stop loss
- Targets
- Risk

Do not invent missing values.
""",
            conversation_id=conversation_id,
            context=signal,
        )

    # =========================================================
    # SIGNAL REVIEW
    # =========================================================

    async def review_signal(
        self,
        signal: Dict[str, Any],
        current_market: Dict[str, Any],
        conversation_id: str = "signal-monitor",
    ) -> str:

        return await self.generate(
            """
Compare the original signal with the current market.

Determine only from the supplied data whether it is:

ACTIVE
TP1_HIT
TP2_HIT
TP3_HIT
SL_HIT
INVALIDATED
UNKNOWN

Never claim TP or SL was hit without actual price evidence.
""",
            conversation_id=conversation_id,
            context={
                "original_signal": signal,
                "current_market": current_market,
            },
        )

    # =========================================================
    # RESULT ANALYSIS
    # =========================================================

    async def analyze_result(
        self,
        signal: Dict[str, Any],
        result: Dict[str, Any],
        conversation_id: str = "results",
    ) -> str:

        return await self.generate(
            """
Perform a post-trade analysis.

Explain:
1. What happened
2. Which TP/SL was reached
3. Whether the original reasoning worked
4. Which confirmation worked
5. What could be improved

Do not invent information.
""",
            conversation_id=conversation_id,
            context={
                "signal": signal,
                "result": result,
            },
        )


# =============================================================
# SINGLETON
# =============================================================

ai_service = AIService()


__all__ = [
    "AIMemory",
    "AIService",
    "ai_service",
]
