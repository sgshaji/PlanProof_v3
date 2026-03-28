"""Evaluator: ratio-based threshold comparison (R003)."""
from __future__ import annotations

from typing import Any

from planproof.schemas.reconciliation import ReconciledEvidence
from planproof.schemas.rules import RuleOutcome, RuleVerdict


class RatioThresholdEvaluator:
    """Evaluate whether a computed ratio meets a regulatory threshold.

    Used for rules like R003 (site coverage) where two measurements
    (e.g. building footprint area and total site area) are combined into
    a ratio that must not exceed a limit.

    Parameters (from YAML)
    ----------------------
    numerator_attribute : str
        The attribute providing the numerator value.
    denominator_attribute : str
        The attribute providing the denominator value.
    operator : str
        Comparison operator (``"<="`` or ``">="``).
    threshold : float
        The maximum or minimum allowed ratio.
    """

    def __init__(self, parameters: dict[str, Any]) -> None:
        self._params = parameters

    def evaluate(
        self, evidence: ReconciledEvidence, params: dict[str, Any]
    ) -> RuleVerdict:
        rule_id: str = self._params.get("rule_id", params.get("rule_id", "unknown"))
        threshold: float = float(self._params["threshold"])
        operator: str = self._params["operator"]

        if evidence.best_value is None:
            return RuleVerdict(
                rule_id=rule_id,
                outcome=RuleOutcome.FAIL,
                evidence_used=evidence.sources,
                explanation="Insufficient evidence: no value available for evaluation.",
                evaluated_value=None,
                threshold=threshold,
            )

        # best_value is expected to be a pre-computed ratio (float in [0, 1])
        value: float = float(evidence.best_value)  # type: ignore[arg-type]

        if operator == "<=":
            passed = value <= threshold
        elif operator == ">=":
            passed = value >= threshold
        else:
            raise ValueError(f"Unsupported operator: {operator!r}")

        outcome = RuleOutcome.PASS if passed else RuleOutcome.FAIL
        pct_value = round(value * 100, 2)
        pct_threshold = round(threshold * 100, 2)

        if passed:
            explanation = (
                f"Ratio {pct_value}% satisfies {operator} {pct_threshold}%."
            )
        else:
            explanation = (
                f"Ratio {pct_value}% does not satisfy {operator} {pct_threshold}%."
            )

        return RuleVerdict(
            rule_id=rule_id,
            outcome=outcome,
            evidence_used=evidence.sources,
            explanation=explanation,
            evaluated_value=value,
            threshold=threshold,
        )
