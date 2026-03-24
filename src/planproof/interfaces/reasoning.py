"""Protocols for the reasoning layer (Layer 3).

Covers evidence reconciliation, confidence gating, assessability evaluation,
and rule-level compliance verdicts.
"""
from __future__ import annotations

from typing import Any, Protocol

from planproof.schemas.assessability import AssessabilityResult
from planproof.schemas.entities import ExtractedEntity
from planproof.schemas.reconciliation import ReconciledEvidence
from planproof.schemas.rules import RuleVerdict


class Reconciler(Protocol):
    """Contract: resolve conflicting extractions for a single attribute.

    # DESIGN: When multiple sources (OCR vs. VLM vs. SOE) disagree on an
    # attribute value the Reconciler picks a winner and records provenance
    # so downstream verdicts can cite the chain of evidence.
    """

    def reconcile(
        self, entities: list[ExtractedEntity], attribute: str
    ) -> ReconciledEvidence: ...


class ConfidenceGate(Protocol):
    """Contract: filter entities that fall below a trustworthiness threshold.

    # DESIGN: Operates *before* reconciliation so that low-confidence
    # extractions never pollute the evidence pool.
    """

    def is_trustworthy(self, entity: ExtractedEntity) -> bool: ...

    def filter_trusted(
        self, entities: list[ExtractedEntity]
    ) -> list[ExtractedEntity]: ...


class AssessabilityEvaluator(Protocol):
    """Contract: determine whether a rule *can* be assessed given available evidence.

    This is the core research contribution of PlanProof.  Traditional
    compliance-checking systems silently skip rules when evidence is missing,
    producing a false sense of completeness.  The AssessabilityEvaluator makes
    the gap explicit by classifying each rule into one of:

        - ASSESSABLE   -- sufficient evidence exists to render a verdict
        - NOT_ASSESSABLE -- evidence is missing or too uncertain; an
                           EvidenceRequest should be generated instead
        - PARTIALLY_ASSESSABLE -- some sub-checks pass, others lack evidence

    By surfacing what *cannot* be checked, PlanProof shifts compliance from
    a binary pass/fail to a three-valued logic that supports iterative
    evidence gathering.
    """

    def evaluate(self, rule_id: str) -> AssessabilityResult: ...


class RuleEvaluator(Protocol):
    """Contract: evaluate a single compliance rule against reconciled evidence.

    # DESIGN: Each concrete evaluator encapsulates one rule family (setback,
    # height, FSR, landscaping, ...).  The pipeline dispatches to the correct
    # evaluator via the rule_id -> evaluator registry.
    """

    def evaluate(
        self, evidence: ReconciledEvidence, params: dict[str, Any]
    ) -> RuleVerdict: ...
