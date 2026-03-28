"""Tests for all 6 rule evaluators (M9)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from planproof.reasoning.evaluators.attribute_diff import AttributeDiffEvaluator
from planproof.reasoning.evaluators.enum_check import EnumCheckEvaluator
from planproof.reasoning.evaluators.fuzzy_match import FuzzyMatchEvaluator
from planproof.reasoning.evaluators.numeric_threshold import NumericThresholdEvaluator
from planproof.reasoning.evaluators.numeric_tolerance import NumericToleranceEvaluator
from planproof.reasoning.evaluators.ratio_threshold import RatioThresholdEvaluator
from planproof.schemas.entities import EntityType, ExtractedEntity, ExtractionMethod
from planproof.schemas.reconciliation import ReconciledEvidence, ReconciliationStatus
from planproof.schemas.rules import RuleOutcome

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_TS = datetime(2024, 1, 1, 12, 0, 0)


def _entity(
    value: Any,
    source: str = "doc_a.pdf",
    entity_type: EntityType = EntityType.MEASUREMENT,
) -> ExtractedEntity:
    return ExtractedEntity(
        entity_type=entity_type,
        value=value,
        unit="m",
        confidence=0.9,
        source_document=source,
        extraction_method=ExtractionMethod.OCR_LLM,
        timestamp=_TS,
    )


def _evidence(
    best_value: Any, sources: list[ExtractedEntity] | None = None
) -> ReconciledEvidence:
    return ReconciledEvidence(
        attribute="test_attr",
        status=ReconciliationStatus.AGREED,
        best_value=best_value,
        sources=sources or [_entity(best_value)],
    )


# ---------------------------------------------------------------------------
# NumericThresholdEvaluator (R001 / R002)
# ---------------------------------------------------------------------------


class TestNumericThresholdEvaluator:
    def _evaluator(self, operator: str, threshold: float) -> NumericThresholdEvaluator:
        return NumericThresholdEvaluator(
            {
                "rule_id": "R001",
                "operator": operator,
                "threshold": threshold,
                "unit": "metres",
            }
        )

    def test_pass_when_height_below_threshold(self) -> None:
        ev = self._evaluator("<=", 8.0)
        evidence = _evidence(7.5)
        verdict = ev.evaluate(evidence, {})
        assert verdict.outcome == RuleOutcome.PASS
        assert verdict.evaluated_value == 7.5
        assert verdict.threshold == 8.0
        assert verdict.rule_id == "R001"
        assert len(verdict.evidence_used) > 0

    def test_fail_when_height_above_threshold(self) -> None:
        ev = self._evaluator("<=", 8.0)
        evidence = _evidence(9.0)
        verdict = ev.evaluate(evidence, {})
        assert verdict.outcome == RuleOutcome.FAIL
        assert verdict.evaluated_value == 9.0

    def test_pass_at_exact_threshold(self) -> None:
        ev = self._evaluator("<=", 8.0)
        evidence = _evidence(8.0)
        verdict = ev.evaluate(evidence, {})
        assert verdict.outcome == RuleOutcome.PASS

    def test_pass_min_threshold_ge(self) -> None:
        ev = self._evaluator(">=", 10.0)
        evidence = _evidence(12.0)
        verdict = ev.evaluate(evidence, {})
        assert verdict.outcome == RuleOutcome.PASS

    def test_fail_min_threshold_ge(self) -> None:
        ev = self._evaluator(">=", 10.0)
        evidence = _evidence(8.0)
        verdict = ev.evaluate(evidence, {})
        assert verdict.outcome == RuleOutcome.FAIL

    def test_invalid_operator_raises(self) -> None:
        ev = self._evaluator("!=", 8.0)
        evidence = _evidence(7.5)
        with pytest.raises(ValueError, match="Unsupported operator"):
            ev.evaluate(evidence, {})

    def test_explanation_is_non_empty(self) -> None:
        ev = self._evaluator("<=", 8.0)
        verdict = ev.evaluate(_evidence(7.5), {})
        assert isinstance(verdict.explanation, str)
        assert len(verdict.explanation) > 0


# ---------------------------------------------------------------------------
# RatioThresholdEvaluator (R003)
# ---------------------------------------------------------------------------


class TestRatioThresholdEvaluator:
    def _evaluator(self, operator: str, threshold: float) -> RatioThresholdEvaluator:
        return RatioThresholdEvaluator(
            {"rule_id": "R003", "operator": operator, "threshold": threshold}
        )

    def test_pass_when_coverage_below_50_pct(self) -> None:
        ev = self._evaluator("<=", 0.50)
        # 45% expressed as ratio 0.45
        evidence = _evidence(0.45)
        verdict = ev.evaluate(evidence, {})
        assert verdict.outcome == RuleOutcome.PASS
        assert verdict.evaluated_value == 0.45

    def test_fail_when_coverage_exceeds_50_pct(self) -> None:
        ev = self._evaluator("<=", 0.50)
        evidence = _evidence(0.55)
        verdict = ev.evaluate(evidence, {})
        assert verdict.outcome == RuleOutcome.FAIL

    def test_pass_at_exact_threshold(self) -> None:
        ev = self._evaluator("<=", 0.50)
        evidence = _evidence(0.50)
        verdict = ev.evaluate(evidence, {})
        assert verdict.outcome == RuleOutcome.PASS

    def test_pass_ge_operator(self) -> None:
        ev = self._evaluator(">=", 0.20)
        evidence = _evidence(0.30)
        verdict = ev.evaluate(evidence, {})
        assert verdict.outcome == RuleOutcome.PASS

    def test_fail_ge_operator(self) -> None:
        ev = self._evaluator(">=", 0.20)
        evidence = _evidence(0.10)
        verdict = ev.evaluate(evidence, {})
        assert verdict.outcome == RuleOutcome.FAIL

    def test_explanation_contains_percentage(self) -> None:
        ev = self._evaluator("<=", 0.50)
        verdict = ev.evaluate(_evidence(0.45), {})
        assert "%" in verdict.explanation


# ---------------------------------------------------------------------------
# FuzzyMatchEvaluator (C2)
# ---------------------------------------------------------------------------


class TestFuzzyMatchEvaluator:
    def _evaluator(self, min_similarity: float = 0.85) -> FuzzyMatchEvaluator:
        return FuzzyMatchEvaluator(
            {
                "rule_id": "C002",
                "attribute_a": "form_address",
                "attribute_b": "drawing_address",
                "min_similarity": min_similarity,
            }
        )

    def _evidence_from_pair(self, a: str, b: str) -> ReconciledEvidence:
        return ReconciledEvidence(
            attribute="address",
            status=ReconciliationStatus.AGREED,
            best_value={"form_address": a, "drawing_address": b},
            sources=[_entity(a, entity_type=EntityType.ADDRESS)],
        )

    def test_pass_similar_addresses(self) -> None:
        ev = self._evaluator()
        # "High Street" vs "High St" — close enough
        evidence = self._evidence_from_pair(
            "123 High Street Bristol", "123 High St Bristol"
        )
        verdict = ev.evaluate(evidence, {})
        assert verdict.outcome == RuleOutcome.PASS
        assert isinstance(verdict.evaluated_value, float)
        assert verdict.evaluated_value >= 0.85

    def test_fail_dissimilar_addresses(self) -> None:
        ev = self._evaluator()
        evidence = self._evidence_from_pair(
            "123 High Street Bristol", "456 Low Road London"
        )
        verdict = ev.evaluate(evidence, {})
        assert verdict.outcome == RuleOutcome.FAIL

    def test_identical_strings_pass(self) -> None:
        ev = self._evaluator()
        addr = "10 Downing Street SW1A 2AA"
        evidence = self._evidence_from_pair(addr, addr)
        verdict = ev.evaluate(evidence, {})
        assert verdict.outcome == RuleOutcome.PASS
        assert verdict.evaluated_value == pytest.approx(1.0, abs=0.01)

    def test_threshold_stored_in_verdict(self) -> None:
        ev = self._evaluator(0.90)
        evidence = self._evidence_from_pair("A", "A")
        verdict = ev.evaluate(evidence, {})
        assert verdict.threshold == 0.90

    def test_tuple_fallback_pass(self) -> None:
        """best_value as a list/tuple should also work."""
        ev = FuzzyMatchEvaluator({"rule_id": "C002", "min_ratio": 0.80})
        evidence = ReconciledEvidence(
            attribute="address",
            status=ReconciliationStatus.SINGLE_SOURCE,
            best_value=["123 High St", "123 High Street"],
            sources=[_entity("123 High St", entity_type=EntityType.ADDRESS)],
        )
        verdict = ev.evaluate(evidence, {})
        assert verdict.outcome == RuleOutcome.PASS

    def test_tuple_fallback_fail(self) -> None:
        ev = FuzzyMatchEvaluator({"rule_id": "C002", "min_ratio": 0.85})
        evidence = ReconciledEvidence(
            attribute="address",
            status=ReconciliationStatus.CONFLICTING,
            best_value=["123 High St", "999 Fake Blvd"],
            sources=[_entity("123 High St", entity_type=EntityType.ADDRESS)],
        )
        verdict = ev.evaluate(evidence, {})
        assert verdict.outcome == RuleOutcome.FAIL


# ---------------------------------------------------------------------------
# EnumCheckEvaluator (C1)
# ---------------------------------------------------------------------------


class TestEnumCheckEvaluator:
    def _evaluator(self, allowed: list[str]) -> EnumCheckEvaluator:
        return EnumCheckEvaluator(
            {"rule_id": "C001", "valid_values": allowed}
        )

    def test_pass_when_value_in_allowed_set(self) -> None:
        ev = self._evaluator(["A", "B", "C", "D"])
        evidence = _evidence("A")
        verdict = ev.evaluate(evidence, {})
        assert verdict.outcome == RuleOutcome.PASS
        assert verdict.evaluated_value == "A"

    def test_fail_when_value_not_in_allowed_set(self) -> None:
        ev = self._evaluator(["A", "B", "C", "D"])
        evidence = _evidence("E")
        verdict = ev.evaluate(evidence, {})
        assert verdict.outcome == RuleOutcome.FAIL

    def test_allowed_values_key_alias(self) -> None:
        """Evaluator should also accept 'allowed_values' key."""
        ev = EnumCheckEvaluator({"rule_id": "C001", "allowed_values": ["A", "B"]})
        evidence = _evidence("A")
        verdict = ev.evaluate(evidence, {})
        assert verdict.outcome == RuleOutcome.PASS

    def test_threshold_is_allowed_list(self) -> None:
        ev = self._evaluator(["A", "B"])
        verdict = ev.evaluate(_evidence("A"), {})
        assert verdict.threshold == ["A", "B"]

    def test_case_sensitive_mismatch(self) -> None:
        ev = self._evaluator(["A", "B", "C", "D"])
        evidence = _evidence("a")  # lowercase — not in set
        verdict = ev.evaluate(evidence, {})
        assert verdict.outcome == RuleOutcome.FAIL

    def test_explanation_mentions_value(self) -> None:
        ev = self._evaluator(["A", "B"])
        verdict = ev.evaluate(_evidence("Z"), {})
        assert "Z" in verdict.explanation


# ---------------------------------------------------------------------------
# NumericToleranceEvaluator (C3)
# ---------------------------------------------------------------------------


class TestNumericToleranceEvaluator:
    def _evaluator(self, tolerance_pct: float) -> NumericToleranceEvaluator:
        return NumericToleranceEvaluator(
            {
                "rule_id": "C003",
                "attribute_a": "stated_site_area",
                "attribute_b": "reference_parcel_area",
                "tolerance_pct": tolerance_pct,
            }
        )

    def _evidence_from_pair(
        self, stated: float, reference: float
    ) -> ReconciledEvidence:
        return ReconciledEvidence(
            attribute="site_area",
            status=ReconciliationStatus.AGREED,
            best_value={"stated_site_area": stated, "reference_parcel_area": reference},
            sources=[_entity(stated)],
        )

    def test_pass_within_tolerance_fraction(self) -> None:
        # 0.15 = 15% tolerance, stated=100, reference=95 → diff=5/95=5.26% < 15%
        ev = self._evaluator(0.15)
        evidence = self._evidence_from_pair(100.0, 95.0)
        verdict = ev.evaluate(evidence, {})
        assert verdict.outcome == RuleOutcome.PASS

    def test_pass_within_tolerance_whole_number(self) -> None:
        # tolerance_pct=15 (whole number) should also be treated as 15%
        ev = self._evaluator(15)
        evidence = self._evidence_from_pair(100.0, 95.0)
        verdict = ev.evaluate(evidence, {})
        assert verdict.outcome == RuleOutcome.PASS

    def test_fail_outside_tolerance(self) -> None:
        # stated=100, reference=50 → diff=50/50=100% > 15%
        ev = self._evaluator(0.15)
        evidence = self._evidence_from_pair(100.0, 50.0)
        verdict = ev.evaluate(evidence, {})
        assert verdict.outcome == RuleOutcome.FAIL

    def test_evaluated_value_contains_both(self) -> None:
        ev = self._evaluator(0.15)
        verdict = ev.evaluate(self._evidence_from_pair(100.0, 95.0), {})
        assert verdict.evaluated_value["stated"] == 100.0
        assert verdict.evaluated_value["reference"] == 95.0

    def test_threshold_stored_as_fraction(self) -> None:
        ev = self._evaluator(15)
        verdict = ev.evaluate(self._evidence_from_pair(100.0, 95.0), {})
        assert verdict.threshold == pytest.approx(0.15)

    def test_tuple_fallback(self) -> None:
        ev = NumericToleranceEvaluator({"rule_id": "C003", "tolerance_pct": 0.15})
        evidence = ReconciledEvidence(
            attribute="site_area",
            status=ReconciliationStatus.AGREED,
            best_value=(100.0, 95.0),
            sources=[_entity(100.0)],
        )
        verdict = ev.evaluate(evidence, {})
        assert verdict.outcome == RuleOutcome.PASS

    def test_exact_match_always_passes(self) -> None:
        ev = self._evaluator(0.0)
        evidence = self._evidence_from_pair(100.0, 100.0)
        verdict = ev.evaluate(evidence, {})
        assert verdict.outcome == RuleOutcome.PASS


# ---------------------------------------------------------------------------
# AttributeDiffEvaluator (C4)
# ---------------------------------------------------------------------------


class TestAttributeDiffEvaluator:
    def _evaluator(
        self,
        attributes: list[str],
        tolerances: dict[str, float] | None = None,
    ) -> AttributeDiffEvaluator:
        params: dict[str, Any] = {
            "rule_id": "C004",
            "attributes": attributes,
        }
        if tolerances is not None:
            params["tolerances"] = tolerances
        return AttributeDiffEvaluator(params)

    def _evidence_from_dict(self, data: dict[str, Any]) -> ReconciledEvidence:
        return ReconciledEvidence(
            attribute="plan_comparison",
            status=ReconciliationStatus.AGREED,
            best_value=data,
            sources=[_entity(str(data))],
        )

    def test_pass_when_values_identical(self) -> None:
        ev = self._evaluator(["building_height", "number_of_storeys"])
        evidence = self._evidence_from_dict(
            {
                "building_height": {"proposed": 7.5, "approved": 7.5},
                "number_of_storeys": {"proposed": 2, "approved": 2},
            }
        )
        verdict = ev.evaluate(evidence, {})
        assert verdict.outcome == RuleOutcome.PASS

    def test_fail_when_values_differ_beyond_tolerance(self) -> None:
        ev = self._evaluator(["building_height"])
        evidence = self._evidence_from_dict(
            {"building_height": {"proposed": 9.0, "approved": 7.5}}
        )
        verdict = ev.evaluate(evidence, {})
        assert verdict.outcome == RuleOutcome.FAIL

    def test_pass_within_tolerance(self) -> None:
        ev = self._evaluator(
            ["building_height"], tolerances={"building_height": 0.5}
        )
        evidence = self._evidence_from_dict(
            {"building_height": {"proposed": 7.5, "approved": 7.3}}
        )
        verdict = ev.evaluate(evidence, {})
        assert verdict.outcome == RuleOutcome.PASS

    def test_fail_just_outside_tolerance(self) -> None:
        ev = self._evaluator(
            ["building_height"], tolerances={"building_height": 0.1}
        )
        evidence = self._evidence_from_dict(
            {"building_height": {"proposed": 7.5, "approved": 7.3}}
        )
        verdict = ev.evaluate(evidence, {})
        assert verdict.outcome == RuleOutcome.FAIL

    def test_evaluated_value_contains_diff_info(self) -> None:
        ev = self._evaluator(["building_height"])
        evidence = self._evidence_from_dict(
            {"building_height": {"proposed": 8.0, "approved": 7.5}}
        )
        verdict = ev.evaluate(evidence, {})
        assert "building_height" in verdict.evaluated_value
        diff_info = verdict.evaluated_value["building_height"]
        assert diff_info["diff"] == pytest.approx(0.5)

    def test_missing_attribute_is_skipped(self) -> None:
        """Attributes in the config but absent from best_value are silently skipped."""
        ev = self._evaluator(["building_height", "number_of_storeys"])
        evidence = self._evidence_from_dict(
            {"building_height": {"proposed": 7.5, "approved": 7.5}}
            # number_of_storeys absent
        )
        verdict = ev.evaluate(evidence, {})
        assert verdict.outcome == RuleOutcome.PASS

    def test_explanation_mentions_violations(self) -> None:
        ev = self._evaluator(["building_height"])
        evidence = self._evidence_from_dict(
            {"building_height": {"proposed": 10.0, "approved": 7.5}}
        )
        verdict = ev.evaluate(evidence, {})
        assert "building_height" in verdict.explanation
