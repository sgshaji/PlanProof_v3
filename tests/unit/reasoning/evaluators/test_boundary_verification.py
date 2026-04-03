"""Tests for BoundaryVerificationEvaluator (C005)."""
from __future__ import annotations

from planproof.reasoning.evaluators.boundary_verification import (
    BoundaryVerificationEvaluator,
)
from planproof.schemas.reconciliation import ReconciledEvidence, ReconciliationStatus
from planproof.schemas.rules import RuleOutcome


def _evidence(status_value: str) -> ReconciledEvidence:
    return ReconciledEvidence(
        attribute="boundary_verification_status",
        status=ReconciliationStatus.AGREED,
        sources=[],
        best_value=status_value,
    )


def _evaluator(rule_id: str = "C005") -> BoundaryVerificationEvaluator:
    return BoundaryVerificationEvaluator(parameters={"rule_id": rule_id})


class TestBoundaryVerificationEvaluator:
    def test_consistent_passes(self) -> None:
        """CONSISTENT best_value → PASS verdict."""
        evaluator = _evaluator()
        verdict = evaluator.evaluate(_evidence("CONSISTENT"), params={})
        assert verdict.outcome == RuleOutcome.PASS
        assert verdict.rule_id == "C005"
        assert "consistent" in verdict.explanation.lower()

    def test_discrepancy_fails(self) -> None:
        """DISCREPANCY_DETECTED best_value → FAIL verdict."""
        evaluator = _evaluator()
        verdict = evaluator.evaluate(_evidence("DISCREPANCY_DETECTED"), params={})
        assert verdict.outcome == RuleOutcome.FAIL
        assert "discrepancy" in verdict.explanation.lower()

    def test_insufficient_fails(self) -> None:
        """INSUFFICIENT_DATA best_value → FAIL verdict."""
        evaluator = _evaluator()
        verdict = evaluator.evaluate(_evidence("INSUFFICIENT_DATA"), params={})
        assert verdict.outcome == RuleOutcome.FAIL
        assert "insufficient" in verdict.explanation.lower()

    def test_none_best_value_fails(self) -> None:
        """None best_value → FAIL (insufficient data path)."""
        evaluator = _evaluator()
        evidence = ReconciledEvidence(
            attribute="boundary_verification_status",
            status=ReconciliationStatus.MISSING,
            sources=[],
            best_value=None,
        )
        verdict = evaluator.evaluate(evidence, params={})
        assert verdict.outcome == RuleOutcome.FAIL

    def test_threshold_is_consistent(self) -> None:
        """Threshold field is always 'CONSISTENT' for human-readable context."""
        evaluator = _evaluator()
        verdict = evaluator.evaluate(_evidence("CONSISTENT"), params={})
        assert verdict.threshold == "CONSISTENT"

    def test_rule_id_from_params_fallback(self) -> None:
        """rule_id falls back to params dict when not in constructor parameters."""
        evaluator = BoundaryVerificationEvaluator(parameters={})
        verdict = evaluator.evaluate(_evidence("CONSISTENT"), params={"rule_id": "C005"})
        assert verdict.rule_id == "C005"

    def test_evaluated_value_stored(self) -> None:
        """evaluated_value on verdict matches the status string."""
        evaluator = _evaluator()
        verdict = evaluator.evaluate(_evidence("DISCREPANCY_DETECTED"), params={})
        assert verdict.evaluated_value == "DISCREPANCY_DETECTED"
