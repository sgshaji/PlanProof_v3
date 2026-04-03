"""Tests for SpatialContainmentEvaluator (C006)."""
from __future__ import annotations

from planproof.reasoning.evaluators.spatial_containment import SpatialContainmentEvaluator
from planproof.schemas.reconciliation import ReconciledEvidence, ReconciliationStatus
from planproof.schemas.rules import RuleOutcome


def _evidence(best_value: str | None) -> ReconciledEvidence:
    return ReconciledEvidence(
        attribute="conservation_area_status",
        status=ReconciliationStatus.AGREED if best_value is not None else ReconciliationStatus.MISSING,
        sources=[],
        best_value=best_value,
    )


def _evaluator(rule_id: str = "C006", required_status: bool = False) -> SpatialContainmentEvaluator:
    return SpatialContainmentEvaluator(
        parameters={"rule_id": rule_id, "required_status": required_status}
    )


class TestSpatialContainmentEvaluator:
    def test_not_in_conservation_area_passes(self) -> None:
        """'false' best_value → PASS (not in conservation area)."""
        evaluator = _evaluator()
        verdict = evaluator.evaluate(_evidence("false"), params={})
        assert verdict.outcome == RuleOutcome.PASS
        assert verdict.rule_id == "C006"
        assert "not in a Conservation Area" in verdict.explanation

    def test_in_conservation_area_fails(self) -> None:
        """'true' best_value → FAIL (in conservation area, heritage assessment needed)."""
        evaluator = _evaluator()
        verdict = evaluator.evaluate(_evidence("true"), params={})
        assert verdict.outcome == RuleOutcome.FAIL
        assert "heritage assessment required" in verdict.explanation

    def test_in_conservation_area_with_true_string(self) -> None:
        """'True' (capitalised) is correctly detected as in-zone."""
        evaluator = _evaluator()
        verdict = evaluator.evaluate(_evidence("True"), params={})
        assert verdict.outcome == RuleOutcome.FAIL

    def test_yes_value_fails(self) -> None:
        """'yes' is treated as in-zone → FAIL."""
        evaluator = _evaluator()
        verdict = evaluator.evaluate(_evidence("yes"), params={})
        assert verdict.outcome == RuleOutcome.FAIL

    def test_no_evidence_fails(self) -> None:
        """None best_value → FAIL with explanation about insufficient evidence."""
        evaluator = _evaluator()
        verdict = evaluator.evaluate(_evidence(None), params={})
        assert verdict.outcome == RuleOutcome.FAIL
        assert "unknown" in verdict.explanation.lower()
        assert verdict.evaluated_value is None

    def test_threshold_reflects_required_status(self) -> None:
        """threshold field on verdict echoes required_status parameter."""
        evaluator = _evaluator(required_status=False)
        verdict = evaluator.evaluate(_evidence("false"), params={})
        assert verdict.threshold == "False"

    def test_rule_id_from_params_fallback(self) -> None:
        """rule_id falls back to params dict when not in constructor parameters."""
        evaluator = SpatialContainmentEvaluator(parameters={})
        verdict = evaluator.evaluate(_evidence("false"), params={"rule_id": "C006"})
        assert verdict.rule_id == "C006"

    def test_evaluated_value_stored(self) -> None:
        """evaluated_value on verdict is the string representation of in_zone."""
        evaluator = _evaluator()
        verdict = evaluator.evaluate(_evidence("true"), params={})
        assert verdict.evaluated_value == "True"

    def test_false_string_passes(self) -> None:
        """'false' value means not in conservation area → PASS."""
        evaluator = _evaluator()
        verdict = evaluator.evaluate(_evidence("false"), params={})
        assert verdict.evaluated_value == "False"
        assert verdict.outcome == RuleOutcome.PASS
