"""Schemas for the assessability engine.

The assessability engine is PlanProof's key differentiator — it determines
whether a rule *can* be evaluated before attempting evaluation. This prevents
the system from issuing false FAIL verdicts when evidence is simply missing
or unreliable.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel


class BlockingReason(StrEnum):
    """Why a rule cannot be assessed."""

    NONE = "NONE"
    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    # WHY: LOW_CONFIDENCE is separate from MISSING — the evidence exists but
    # the extraction confidence is below the gating threshold, so we cannot
    # trust it enough to issue a verdict.
    LOW_CONFIDENCE = "LOW_CONFIDENCE"


class EvidenceRequirement(BaseModel):
    """Specification of what evidence a rule needs for a single attribute."""

    attribute: str
    acceptable_sources: list[str]
    min_confidence: float
    # WHY: spatial_grounding records whether the evidence must come from a
    # specific region of a document (e.g. "site boundary on Block Plan")
    # rather than just any mention of the attribute.
    spatial_grounding: str | None = None

    model_config = {"from_attributes": True}


class ConflictDetail(BaseModel):
    """Details of a conflict between evidence sources for one attribute."""

    attribute: str
    values: list[Any]
    sources: list[str]

    model_config = {"from_attributes": True}


class AssessabilityResult(BaseModel):
    """Whether a specific rule can be evaluated given current evidence.

    # WHY: The tri-state status (ASSESSABLE / NOT_ASSESSABLE) is the core
    # innovation — rules that lack sufficient evidence are explicitly flagged
    # rather than being forced into a PASS/FAIL binary.
    """

    rule_id: str
    status: Literal["ASSESSABLE", "NOT_ASSESSABLE", "PARTIALLY_ASSESSABLE"]
    blocking_reason: BlockingReason
    missing_evidence: list[EvidenceRequirement]
    conflicts: list[ConflictDetail]

    # Dempster-Shafer evidence sufficiency metrics (M8)
    belief: float = 0.0           # Bel(sufficient) — lower bound of evidence support
    plausibility: float = 1.0     # Pl(sufficient) — upper bound
    conflict_mass: float = 0.0    # K from Dempster's rule — source disagreement

    model_config = {"from_attributes": True}
