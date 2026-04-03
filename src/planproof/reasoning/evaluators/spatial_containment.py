"""Evaluator: spatial containment check (C006)."""
from __future__ import annotations

from typing import Any

from planproof.schemas.reconciliation import ReconciledEvidence
from planproof.schemas.rules import RuleOutcome, RuleVerdict


class SpatialContainmentEvaluator:
    """Check if a property is within a restricted spatial zone.

    PASS if the property is NOT in the restricted zone (or zone status unknown).
    FAIL if the property IS in the restricted zone without heritage assessment.

    This evaluator requires evidence sourced from SNKG (graph spatial query).
    When SNKG is absent (e.g. ablation_b), the assessability engine marks the
    rule NOT_ASSESSABLE before this evaluator is ever called, so the ablation
    difference is captured at the assessability stage.
    """

    def __init__(self, parameters: dict[str, Any]) -> None:
        self._params = parameters

    def evaluate(
        self, evidence: ReconciledEvidence, params: dict[str, Any]
    ) -> RuleVerdict:
        rule_id: str = self._params.get("rule_id", params.get("rule_id", "unknown"))
        required_status: bool = self._params.get("required_status", False)

        if evidence.best_value is None:
            return RuleVerdict(
                rule_id=rule_id,
                outcome=RuleOutcome.FAIL,
                evidence_used=evidence.sources,
                explanation="Insufficient evidence: conservation area status unknown.",
                evaluated_value=None,
                threshold=str(required_status),
            )

        # best_value should be a boolean or string indicating if in conservation area
        in_zone = str(evidence.best_value).lower() in (
            "true", "yes", "1", "in_conservation_area"
        )

        if in_zone and not required_status:
            outcome = RuleOutcome.FAIL
            explanation = (
                "Property is in a Conservation Area — heritage assessment required."
            )
        else:
            outcome = RuleOutcome.PASS
            explanation = (
                "Property is not in a Conservation Area, or heritage assessment provided."
            )

        return RuleVerdict(
            rule_id=rule_id,
            outcome=outcome,
            evidence_used=evidence.sources,
            explanation=explanation,
            evaluated_value=str(in_zone),
            threshold=str(required_status),
        )
