"""Protocol contracts for PlanProof.

This package contains all Protocol (structural subtyping) definitions that
define the boundaries between PlanProof's architectural layers.  Concrete
implementations live in their respective layer packages and must satisfy
these contracts -- but never import them at runtime (Protocols are checked
statically by mypy / pyright).

Modules
-------
extraction  -- Document ingestion and entity extraction (Layer 1)
graph       -- Knowledge-graph read/write interfaces (ISP-split)
reasoning   -- Reconciliation, confidence gating, assessability, rule eval
output      -- Report and evidence-request generation
pipeline    -- Step abstraction and shared pipeline context
cache       -- Deterministic response caching
llm         -- LLM client abstraction
"""
