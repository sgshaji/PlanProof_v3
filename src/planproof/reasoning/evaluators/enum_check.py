"""Evaluator: enumeration membership check (C1)."""
from __future__ import annotations

from typing import Any

from planproof.schemas.reconciliation import ReconciledEvidence
from planproof.schemas.rules import RuleOutcome, RuleVerdict


class EnumCheckEvaluator:
    """Evaluate whether a categorical value belongs to an allowed set.

    Used for cross-document consistency checks like C1, where a value
    extracted from one document must match one of a set of permitted
    values defined by another document or reference data.

    Parameters (from YAML)
    ----------------------
    attribute : str
        The entity attribute to check.
    valid_values : list[str]
        The set of permitted values (preferred key).
    allowed_values : list[str]
        Alias for valid_values (accepted for compatibility).
    """

    def __init__(self, parameters: dict[str, Any]) -> None:
        self._params = parameters

    def evaluate(
        self, evidence: ReconciledEvidence, params: dict[str, Any]
    ) -> RuleVerdict:
        rule_id: str = self._params.get("rule_id", params.get("rule_id", "unknown"))
        # Support both "valid_values" (YAML) and "allowed_values" (task spec)
        allowed: list[str] = self._params.get(
            "valid_values", self._params.get("allowed_values", [])
        )

        if evidence.best_value is None:
            return RuleVerdict(
                rule_id=rule_id,
                outcome=RuleOutcome.FAIL,
                evidence_used=evidence.sources,
                explanation="Insufficient evidence: no value available for evaluation.",
                evaluated_value=None,
                threshold=allowed,
            )

        value: str = str(evidence.best_value)
        passed = value in allowed
        outcome = RuleOutcome.PASS if passed else RuleOutcome.FAIL

        if passed:
            explanation = f"Value {value!r} is in allowed set {allowed}."
        else:
            explanation = f"Value {value!r} is not in allowed set {allowed}."

        return RuleVerdict(
            rule_id=rule_id,
            outcome=outcome,
            evidence_used=evidence.sources,
            explanation=explanation,
            evaluated_value=value,
            threshold=allowed,
        )
