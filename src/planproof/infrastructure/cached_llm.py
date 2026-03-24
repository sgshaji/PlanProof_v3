"""Composition of LLMClient + ResponseCache for transparent caching.

Wraps any ``LLMClient`` implementation and transparently checks a
``ResponseCache`` before making an API call.  Cache misses are forwarded
to the underlying client and the response is stored for future reuse.
"""
from __future__ import annotations

import hashlib
from typing import Any

from planproof.interfaces.cache import ResponseCache
from planproof.interfaces.llm import LLMClient


class CachedLLMClient:
    """LLM client decorator that adds transparent response caching.

    Satisfies the ``LLMClient`` Protocol while composing an inner client
    with a ``ResponseCache``.
    """

    def __init__(self, client: LLMClient, cache: ResponseCache) -> None:
        self._client = client
        self._cache = cache

    @staticmethod
    def _compute_prompt_hash(prompt: str) -> str:
        """SHA-256 hex digest of the prompt text."""
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    def complete(
        self,
        prompt: str,
        model: str = "",
        doc_hash: str = "",
        **kwargs: Any,
    ) -> str:
        """Return a cached response if available, otherwise call the LLM.

        Parameters
        ----------
        prompt:
            The full prompt text to send to the LLM.
        model:
            Model identifier (e.g. ``"gpt-4o"``).
        doc_hash:
            Content hash of the document being processed.  Defaults to
            empty string when the call is not document-specific.
        **kwargs:
            Additional arguments forwarded to the underlying client.
        """
        prompt_hash = self._compute_prompt_hash(prompt)

        # Check cache first
        cached = self._cache.get(prompt_hash, doc_hash, model)
        if cached is not None:
            return cached

        # Cache miss — call the underlying LLM client
        response = self._client.complete(prompt, model, **kwargs)

        # Store for future reuse
        self._cache.put(prompt_hash, doc_hash, model, response)

        return response
