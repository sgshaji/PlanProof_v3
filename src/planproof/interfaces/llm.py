"""Protocol for LLM client abstraction.

# DESIGN: v1 exposes only a synchronous `complete` method.  When we add
# streaming or async support in v2 we will introduce AsyncLLMClient as a
# separate Protocol rather than breaking this contract.
"""
from __future__ import annotations

from typing import Any, Protocol


class LLMClient(Protocol):
    """Contract: synchronous text-completion interface.

    # WHY: Decouples all LLM-calling code from a specific provider (OpenAI,
    # Anthropic, local models).  Concrete implementations handle auth,
    # retries, and rate-limiting internally.
    """

    def complete(self, prompt: str, model: str, **kwargs: Any) -> str: ...
