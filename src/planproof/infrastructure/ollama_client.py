"""Ollama LLM client — free, local, no API key required.

# WHY: Ollama runs open-source models (Llama 3, Mistral, Gemma, LLaVA) locally.
# No API key, no cost, no internet required. Ideal for development and iteration.
# For final evaluation runs, switch to OpenAI or Groq via config.
#
# Ollama must be running locally (or as a Docker service) on port 11434.
# Install: https://ollama.ai or use the Docker image ollama/ollama.
"""

from __future__ import annotations

from typing import Any

import requests

from planproof.infrastructure.logging import get_logger

logger = get_logger(__name__)


class OllamaClient:
    """LLM client that calls a local Ollama instance.

    Implements the LLMClient Protocol via structural subtyping.
    No API key required — Ollama is free and runs locally.
    """

    def __init__(self, base_url: str = "http://localhost:11434") -> None:
        self._base_url = base_url.rstrip("/")

    def complete(
        self, prompt: str, model: str = "llama3.1", **kwargs: Any
    ) -> str:
        """Send a completion request to the local Ollama instance.

        Parameters
        ----------
        prompt:
            The prompt text to send.
        model:
            Ollama model name (e.g. "llama3.1", "mistral", "gemma2").
            Must be pulled first: ``ollama pull llama3.1``
        **kwargs:
            Additional parameters passed to Ollama API (temperature, etc.)
        """
        # WHY: temperature=0 for deterministic output (cache consistency)
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", 0),
            },
        }

        try:
            response = requests.post(
                f"{self._base_url}/api/generate",
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            return response.json().get("response", "")
        except requests.ConnectionError:
            msg = (
                f"Cannot connect to Ollama at {self._base_url}. "
                "Is Ollama running? Start with: ollama serve "
                "or docker compose up (includes Ollama service)"
            )
            logger.error("ollama_connection_failed", url=self._base_url)
            raise ConnectionError(msg) from None
        except requests.HTTPError as e:
            logger.error(
                "ollama_request_failed",
                status=e.response.status_code,
                body=e.response.text[:200],
            )
            raise
