"""Evaluator: boundary verification (C005)."""
from __future__ import annotations

from typing import Any

from planproof.schemas.boundary import BoundaryVerificationStatus
from planproof.schemas.reconciliation import ReconciledEvidence
from planproof.schemas.rules import RuleOutcome, RuleVerdict


class BoundaryVerificationEvaluator:
    """Evaluate boundary consistency from reconciled evidence.

    PASS when combined_status is CONSISTENT.
    FAIL when DISCREPANCY_DETECTED or INSUFFICIENT_DATA.
    """

    def __init__(self, parameters: dict[str, Any]) -> None:
        self._params = parameters

    def evaluate(
        self, evidence: ReconciledEvidence, params: dict[str, Any]
    ) -> RuleVerdict:
        rule_id: str = self._params.get("rule_id", params.get("rule_id", "unknown"))

        status_str = str(evidence.best_value) if evidence.best_value else ""

        if status_str == BoundaryVerificationStatus.CONSISTENT:
            outcome = RuleOutcome.PASS
            explanation = "Boundary verification: all tiers consistent."
        elif status_str == BoundaryVerificationStatus.DISCREPANCY_DETECTED:
            outcome = RuleOutcome.FAIL
            explanation = "Boundary discrepancy detected by verification pipeline."
        else:
            outcome = RuleOutcome.FAIL
            explanation = "Insufficient boundary verification data."

        return RuleVerdict(
            rule_id=rule_id,
            outcome=outcome,
            evidence_used=evidence.sources,
            explanation=explanation,
            evaluated_value=status_str,
            threshold="CONSISTENT",
        )
