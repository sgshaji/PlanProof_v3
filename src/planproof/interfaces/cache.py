"""Protocol for deterministic LLM response caching.

# WHY: LLM calls are expensive and non-deterministic.  Caching by
# (prompt_hash, doc_hash, model) enables reproducible runs during
# development and avoids redundant API spend when re-processing the
# same document with the same prompt template.
"""
from __future__ import annotations

from typing import Protocol


class ResponseCache(Protocol):
    """Contract: content-addressed cache for LLM responses."""

    def get(
        self, prompt_hash: str, doc_hash: str, model: str
    ) -> str | None:
        """Return cached response or None on miss."""
        ...

    def put(
        self, prompt_hash: str, doc_hash: str, model: str, response: str
    ) -> None:
        """Store a response under the composite key."""
        ...
