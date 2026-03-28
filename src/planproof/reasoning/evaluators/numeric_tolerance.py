"""Evaluator: numeric equality within tolerance (C3)."""
from __future__ import annotations

from typing import Any

from planproof.schemas.reconciliation import ReconciledEvidence
from planproof.schemas.rules import RuleOutcome, RuleVerdict


class NumericToleranceEvaluator:
    """Evaluate whether numeric values from different sources agree within tolerance.

    Used for cross-document consistency checks like C3, where the same
    measurement (e.g. site area) appears in multiple documents and must
    agree within an acceptable margin of error.

    Parameters (from YAML)
    ----------------------
    attribute_a : str
        First attribute name (e.g. stated_site_area).
    attribute_b : str
        Second attribute name (e.g. reference_parcel_area).
    tolerance_pct : float
        Maximum allowed relative difference as a decimal fraction (e.g. 0.15
        means ±15%) OR as a whole-number percentage (e.g. 15 meaning 15%).
        Values <= 1.0 are treated as fractions; values > 1.0 are divided by 100.
    tolerance_abs : float | None
        Optional absolute tolerance override.
    """

    def __init__(self, parameters: dict[str, Any]) -> None:
        self._params = parameters

    def evaluate(
        self, evidence: ReconciledEvidence, params: dict[str, Any]
    ) -> RuleVerdict:
        rule_id: str = self._params.get("rule_id", params.get("rule_id", "unknown"))

        raw_tol_early = float(self._params.get("tolerance_pct", 0.0))
        threshold_early = raw_tol_early / 100.0 if raw_tol_early > 1.0 else raw_tol_early

        if evidence.best_value is None:
            return RuleVerdict(
                rule_id=rule_id,
                outcome=RuleOutcome.FAIL,
                evidence_used=evidence.sources,
                explanation="Insufficient evidence: no value available for evaluation.",
                evaluated_value=None,
                threshold=threshold_early,
            )

        # best_value is expected to be a dict {attribute_a: v1, attribute_b: v2}
        # or a tuple/list (stated, reference).
        best: Any = evidence.best_value
        if isinstance(best, dict):
            key_a: str = self._params.get("attribute_a", "")
            key_b: str = self._params.get("attribute_b", "")
            stated: float = float(best[key_a])
            reference: float = float(best[key_b])
        else:
            seq: list[Any] = list(best)
            stated = float(seq[0])
            reference = float(seq[1])

        raw_tol = float(self._params.get("tolerance_pct", 0.0))
        # Normalise: YAML may use fraction (0.15) or whole number (15)
        if raw_tol > 1.0:
            tolerance_frac = raw_tol / 100.0
        else:
            tolerance_frac = raw_tol

        if reference == 0:
            # Avoid division by zero — use absolute tolerance if available
            tol_abs = self._params.get("tolerance_abs")
            if tol_abs is not None:
                actual_diff = abs(stated - reference)
                passed = actual_diff <= float(tol_abs)
            else:
                passed = stated == reference
        else:
            relative_diff = abs(stated - reference) / abs(reference)
            passed = relative_diff <= tolerance_frac

        outcome = RuleOutcome.PASS if passed else RuleOutcome.FAIL

        if reference != 0:
            relative_diff = abs(stated - reference) / abs(reference)
            diff_pct = round(relative_diff * 100, 2)
        else:
            diff_pct = 0.0 if stated == reference else float("inf")

        if passed:
            explanation = (
                f"Stated value {stated} agrees with reference {reference} "
                f"within {tolerance_frac * 100}% tolerance "
                f"(actual diff: {diff_pct}%)."
            )
        else:
            explanation = (
                f"Stated value {stated} deviates from reference {reference} "
                f"by {diff_pct}%, exceeding {tolerance_frac * 100}% tolerance."
            )

        return RuleVerdict(
            rule_id=rule_id,
            outcome=outcome,
            evidence_used=evidence.sources,
            explanation=explanation,
            evaluated_value={"stated": stated, "reference": reference},
            threshold=tolerance_frac,
        )
