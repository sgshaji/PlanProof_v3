"""PlanProof — Assessability-Aware Multimodal Planning Compliance Validation.

A neurosymbolic AI system that validates UK planning applications against
regulatory rules. Unlike traditional compliance tools that force binary
PASS/FAIL verdicts, PlanProof introduces a third state — NOT_ASSESSABLE —
that explicitly models evidence insufficiency.

Architecture:
    Layer 1 (ingestion/)       — Document classification + entity extraction
    Layer 2 (representation/)  — Entity normalisation + Spatial Knowledge Graph
    Layer 3 (reasoning/)       — Reconciliation, gating, assessability, rule evaluation
    Layer 4 (output/)          — Compliance reports + evidence request generation
    Layer 5 (evaluation/)      — Ablation study infrastructure

Cross-cutting:
    interfaces/     — Protocol definitions (no implementations)
    schemas/        — Pydantic data models (M4 integration contracts)
    infrastructure/ — LLM cache, API clients, logging
    pipeline/       — Step registry orchestrator
    bootstrap.py    — Composition root (dependency wiring)
"""

__version__ = "0.1.0"
