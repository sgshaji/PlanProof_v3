"""Groq LLM client — free tier, very fast inference.

# WHY: Groq provides free-tier access to Llama 3 and Mistral models with
# extremely fast inference (~500 tokens/sec). Good for development iteration
# when you need cloud-quality models without OpenAI costs.
#
# Free tier limits: 30 requests/min, 14,400 requests/day.
# Sign up: https://console.groq.com (free API key)
#
# DESIGN: Groq's API is OpenAI-compatible, so we reuse the openai library
# with a custom base_url. This avoids adding another SDK dependency.
"""

from __future__ import annotations

from typing import Any

import openai

from planproof.infrastructure.logging import get_logger

logger = get_logger(__name__)

# DESIGN: Groq's API is OpenAI-compatible — same SDK, different base URL.
GROQ_BASE_URL = "https://api.groq.com/openai/v1"


class GroqClient:
    """LLM client that calls the Groq API (OpenAI-compatible).

    Implements the LLMClient Protocol via structural subtyping.
    Requires a free Groq API key from https://console.groq.com
    """

    def __init__(self, api_key: str) -> None:
        if not api_key:
            msg = (
                "Groq API key is required. Get a free key at "
                "https://console.groq.com and set PLANPROOF_LLM_API_KEY"
            )
            raise ValueError(msg)
        self._client = openai.OpenAI(
            api_key=api_key,
            base_url=GROQ_BASE_URL,
        )

    def complete(
        self,
        prompt: str,
        model: str = "llama-3.1-70b-versatile",
        **kwargs: Any,
    ) -> str:
        """Send a completion request to the Groq API.

        Parameters
        ----------
        prompt:
            The prompt text to send.
        model:
            Groq model name. Free tier options:
            - "llama-3.1-70b-versatile" (best quality)
            - "llama-3.1-8b-instant" (faster, smaller)
            - "mixtral-8x7b-32768" (Mistral, good for structured extraction)
        """
        # WHY: temperature=0 for cache determinism
        params: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": kwargs.get("temperature", 0),
        }

        response = self._client.chat.completions.create(**params)
        content = response.choices[0].message.content
        return content or ""
