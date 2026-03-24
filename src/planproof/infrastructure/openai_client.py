"""OpenAI API wrapper implementing the ``LLMClient`` Protocol.

# DESIGN: v1 is synchronous and uses the chat completions endpoint.
# When we add async support, a separate ``AsyncOpenAIClient`` will be
# introduced rather than complicating this class.
"""
from __future__ import annotations

from typing import Any

import openai


class OpenAIClient:
    """Synchronous OpenAI chat-completion client.

    Satisfies the ``LLMClient`` Protocol from ``planproof.interfaces.llm``.
    """

    def __init__(self, api_key: str) -> None:
        if not api_key:
            msg = (
                "OpenAI API key is required. "
                "Set PLANPROOF_LLM_API_KEY or use llm_provider=ollama (free)"
            )
            raise ValueError(msg)
        self._client = openai.OpenAI(api_key=api_key)

    def complete(self, prompt: str, model: str = "gpt-4o", **kwargs: Any) -> str:
        """Send *prompt* to the OpenAI API and return the assistant message.

        # WHY: temperature=0 for cache determinism — with temperature=0 the
        # model produces (near-)identical outputs for the same input, making
        # the SQLite response cache reliable.  Callers can override via kwargs
        # but doing so will reduce cache hit rates.
        """
        params: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        }
        params.update(kwargs)
        response = self._client.chat.completions.create(**params)
        return response.choices[0].message.content or ""
