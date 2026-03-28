"""Evaluator: absolute numeric threshold comparison (R001, R002)."""
from __future__ import annotations

from typing import Any

from planproof.schemas.reconciliation import ReconciledEvidence
from planproof.schemas.rules import RuleOutcome, RuleVerdict


class NumericThresholdEvaluator:
    """Evaluate whether a numeric value meets a maximum or minimum threshold.

    Used for rules like R001 (max building height) and R002 (min rear garden
    depth) where a single numeric measurement is compared against a fixed
    regulatory limit.

    Parameters (from YAML)
    ----------------------
    attribute : str
        The entity attribute to evaluate.
    operator : str
        Comparison operator (``"<="`` or ``">="``).
    threshold : float
        The regulatory limit value.
    unit : str
        Expected unit of measurement (e.g. ``"metres"``).
    """

    def __init__(self, parameters: dict[str, Any]) -> None:
        self._params = parameters

    def evaluate(
        self, evidence: ReconciledEvidence, params: dict[str, Any]
    ) -> RuleVerdict:
        rule_id: str = self._params.get("rule_id", params.get("rule_id", "unknown"))
        threshold: float = float(self._params["threshold"])
        operator: str = self._params["operator"]
        value: float = float(evidence.best_value)  # type: ignore[arg-type]

        if operator == "<=":
            passed = value <= threshold
        elif operator == ">=":
            passed = value >= threshold
        else:
            raise ValueError(f"Unsupported operator: {operator!r}")

        unit = self._params.get("unit", "")
        unit_str = f" {unit}" if unit else ""
        outcome = RuleOutcome.PASS if passed else RuleOutcome.FAIL

        if passed:
            explanation = (
                f"Value {value}{unit_str} satisfies {operator} {threshold}{unit_str}."
            )
        else:
            explanation = (
                f"Value {value}{unit_str} does not satisfy {operator} "
                f"{threshold}{unit_str}."
            )

        return RuleVerdict(
            rule_id=rule_id,
            outcome=outcome,
            evidence_used=evidence.sources,
            explanation=explanation,
            evaluated_value=value,
            threshold=threshold,
        )
