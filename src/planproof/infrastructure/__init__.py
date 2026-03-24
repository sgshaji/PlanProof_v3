"""Cross-cutting infrastructure for PlanProof.

Provides concrete implementations of the LLM client, response cache, and
structured logging utilities.  All classes satisfy the Protocol contracts
defined in ``planproof.interfaces`` and are wired together in
``planproof.bootstrap``.

Modules
-------
llm_cache       -- SQLite-backed deterministic LLM response cache
openai_client   -- OpenAI API wrapper implementing LLMClient
cached_llm      -- Composition of LLMClient + ResponseCache
logging         -- structlog JSON logging configuration
"""
