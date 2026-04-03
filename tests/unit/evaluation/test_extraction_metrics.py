"""Tests for extraction accuracy metrics — entity matching, recall, precision, value accuracy."""
from __future__ import annotations

import pytest

from planproof.evaluation.extraction_metrics import (
    ExtractionEvalResult,
    ExtractionMatch,
    compute_extraction_metrics,
    match_entities,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gt(attribute: str, value, entity_type: str = "field") -> dict:
    return {"attribute": attribute, "value": value, "entity_type": entity_type}


def _pred(attribute: str, value, doc_type: str = "") -> dict:
    return {"attribute": attribute, "value": value, "doc_type": doc_type}


# ---------------------------------------------------------------------------
# match_entities — structural tests
# ---------------------------------------------------------------------------


class TestMatchEntitiesExactMatch:
    def test_exact_attribute_match_returns_one_matched_entry(self):
        gt = [_gt("lot_area", 500)]
        pred = [_pred("lot_area", 500)]
        matches = match_entities(gt, pred)
        assert len(matches) == 1
        m = matches[0]
        assert m.matched is True
        assert m.gt_attribute == "lot_area"
        assert m.predicted_attribute == "lot_area"

    def test_exact_match_correct_value_flagged(self):
        gt = [_gt("lot_area", 500)]
        pred = [_pred("lot_area", 500)]
        matches = match_entities(gt, pred)
        assert matches[0].value_correct is True

    def test_exact_match_wrong_value_flagged(self):
        gt = [_gt("lot_area", 500)]
        pred = [_pred("lot_area", 999)]
        matches = match_entities(gt, pred)
        assert matches[0].matched is True
        assert matches[0].value_correct is False


class TestMatchEntitiesCaseInsensitive:
    def test_case_insensitive_attribute_matching(self):
        gt = [_gt("Lot_Area", 500)]
        pred = [_pred("lot_area", 500)]
        matches = match_entities(gt, pred)
        assert len(matches) == 1
        assert matches[0].matched is True

    def test_whitespace_stripped_in_attribute_matching(self):
        gt = [_gt("  lot_area  ", 500)]
        pred = [_pred("lot_area", 500)]
        matches = match_entities(gt, pred)
        assert matches[0].matched is True


class TestMatchEntitiesMissedEntity:
    def test_missed_gt_entity_produces_fn_entry(self):
        gt = [_gt("lot_area", 500)]
        pred = []
        matches = match_entities(gt, pred)
        assert len(matches) == 1
        m = matches[0]
        assert m.matched is False
        assert m.value_correct is False
        assert m.gt_attribute == "lot_area"
        assert m.predicted_attribute is None
        assert m.predicted_value is None

    def test_missed_entity_gt_value_preserved(self):
        gt = [_gt("setback_front", 3.0)]
        pred = []
        matches = match_entities(gt, pred)
        assert matches[0].gt_value == 3.0


class TestMatchEntitiesHallucination:
    def test_hallucinated_entity_produces_fp_entry(self):
        gt = []
        pred = [_pred("made_up_field", "yes")]
        matches = match_entities(gt, pred)
        assert len(matches) == 1
        m = matches[0]
        assert m.matched is False
        assert m.value_correct is False
        assert m.gt_attribute is None
        assert m.gt_value is None
        assert m.predicted_attribute == "made_up_field"

    def test_hallucinated_value_preserved(self):
        gt = []
        pred = [_pred("ghost_field", 42)]
        matches = match_entities(gt, pred)
        assert matches[0].predicted_value == 42


class TestMatchEntitiesMetadata:
    def test_doc_type_and_set_id_propagated(self):
        gt = [_gt("x", 1)]
        pred = [_pred("x", 1)]
        matches = match_entities(gt, pred, doc_type="DA", set_id="s99")
        assert matches[0].doc_type == "DA"
        assert matches[0].set_id == "s99"


# ---------------------------------------------------------------------------
# Value matching — numeric tolerance
# ---------------------------------------------------------------------------


class TestNumericTolerance:
    def test_numeric_within_10_percent_is_correct(self):
        gt = [_gt("floor_area", 100.0)]
        pred = [_pred("floor_area", 108.0)]  # 8% off — within tolerance
        matches = match_entities(gt, pred)
        assert matches[0].value_correct is True

    def test_numeric_outside_10_percent_is_incorrect(self):
        gt = [_gt("floor_area", 100.0)]
        pred = [_pred("floor_area", 115.0)]  # 15% off — outside tolerance
        matches = match_entities(gt, pred)
        assert matches[0].value_correct is False

    def test_numeric_exactly_at_10_percent_boundary_is_correct(self):
        gt = [_gt("floor_area", 100.0)]
        pred = [_pred("floor_area", 110.0)]  # exactly 10% — within (<=)
        matches = match_entities(gt, pred)
        assert matches[0].value_correct is True

    def test_small_value_absolute_tolerance_within(self):
        # value < 5.0: ±0.5 absolute
        gt = [_gt("setback", 2.0)]
        pred = [_pred("setback", 2.4)]  # 0.4 off — within ±0.5
        matches = match_entities(gt, pred)
        assert matches[0].value_correct is True

    def test_small_value_absolute_tolerance_outside(self):
        gt = [_gt("setback", 2.0)]
        pred = [_pred("setback", 2.6)]  # 0.6 off — outside ±0.5
        matches = match_entities(gt, pred)
        assert matches[0].value_correct is False

    def test_small_value_absolute_tolerance_boundary(self):
        gt = [_gt("setback", 2.0)]
        pred = [_pred("setback", 2.5)]  # exactly 0.5 off — within (<=)
        matches = match_entities(gt, pred)
        assert matches[0].value_correct is True

    def test_zero_gt_value_exact_match(self):
        gt = [_gt("offset", 0)]
        pred = [_pred("offset", 0)]
        matches = match_entities(gt, pred)
        assert matches[0].value_correct is True

    def test_zero_gt_value_nonzero_pred_outside_absolute(self):
        gt = [_gt("offset", 0)]
        pred = [_pred("offset", 1.0)]  # absolute diff 1.0 > 0.5
        matches = match_entities(gt, pred)
        assert matches[0].value_correct is False


# ---------------------------------------------------------------------------
# Value matching — string fuzzy
# ---------------------------------------------------------------------------


class TestStringFuzzyMatch:
    def test_high_similarity_string_is_correct(self):
        gt = [_gt("zone_code", "Residential A")]
        pred = [_pred("zone_code", "Residential A")]
        matches = match_entities(gt, pred)
        assert matches[0].value_correct is True

    def test_minor_typo_above_threshold_is_correct(self):
        # "Residential A" vs "Residential B" — small change, expect ≥0.85 similarity
        gt = [_gt("zone_code", "Residential Area")]
        pred = [_pred("zone_code", "Residential Area ")]  # trailing space
        matches = match_entities(gt, pred)
        assert matches[0].value_correct is True

    def test_string_mismatch_below_threshold_is_incorrect(self):
        gt = [_gt("zone_code", "Commercial")]
        pred = [_pred("zone_code", "Residential")]
        matches = match_entities(gt, pred)
        assert matches[0].value_correct is False

    def test_empty_string_vs_non_empty_is_incorrect(self):
        gt = [_gt("description", "something")]
        pred = [_pred("description", "")]
        matches = match_entities(gt, pred)
        assert matches[0].value_correct is False


# ---------------------------------------------------------------------------
# Value matching — categorical
# ---------------------------------------------------------------------------


class TestCategoricalMatch:
    def test_categorical_exact_case_insensitive(self):
        gt = [_gt("permitted_use", "yes")]
        pred = [_pred("permitted_use", "YES")]
        matches = match_entities(gt, pred)
        assert matches[0].value_correct is True

    def test_categorical_mismatch(self):
        gt = [_gt("permitted_use", "yes")]
        pred = [_pred("permitted_use", "no")]
        matches = match_entities(gt, pred)
        assert matches[0].value_correct is False


# ---------------------------------------------------------------------------
# compute_extraction_metrics — aggregate metrics
# ---------------------------------------------------------------------------


class TestComputeExtractionMetricsPerfect:
    def test_perfect_extraction_all_ones(self):
        gt = [_gt("a", 1), _gt("b", "foo")]
        pred = [_pred("a", 1), _pred("b", "foo")]
        result = compute_extraction_metrics(gt, pred, set_id="s1", doc_type="DA")
        assert result.recall == pytest.approx(1.0)
        assert result.precision == pytest.approx(1.0)
        assert result.value_accuracy == pytest.approx(1.0)

    def test_perfect_result_has_correct_ids(self):
        gt = [_gt("a", 1)]
        pred = [_pred("a", 1)]
        result = compute_extraction_metrics(gt, pred, set_id="s42", doc_type="CC")
        assert result.set_id == "s42"
        assert result.doc_type == "CC"


class TestComputeExtractionMetricsPartial:
    def test_one_missed_entity_reduces_recall(self):
        gt = [_gt("a", 1), _gt("b", 2)]
        pred = [_pred("a", 1)]
        result = compute_extraction_metrics(gt, pred)
        # TP=1, FN=1 → recall=0.5
        assert result.recall == pytest.approx(0.5)
        # precision=1.0 (no FP)
        assert result.precision == pytest.approx(1.0)

    def test_one_hallucinated_entity_reduces_precision(self):
        gt = [_gt("a", 1)]
        pred = [_pred("a", 1), _pred("ghost", 99)]
        result = compute_extraction_metrics(gt, pred)
        # TP=1, FP=1 → precision=0.5
        assert result.precision == pytest.approx(0.5)
        assert result.recall == pytest.approx(1.0)

    def test_wrong_value_reduces_value_accuracy(self):
        gt = [_gt("a", 100)]
        pred = [_pred("a", 200)]  # matched but wrong value
        result = compute_extraction_metrics(gt, pred)
        assert result.recall == pytest.approx(1.0)
        assert result.value_accuracy == pytest.approx(0.0)

    def test_partial_value_accuracy(self):
        gt = [_gt("a", 1), _gt("b", 2)]
        pred = [_pred("a", 1), _pred("b", 999)]
        result = compute_extraction_metrics(gt, pred)
        assert result.value_accuracy == pytest.approx(0.5)


class TestComputeExtractionMetricsEmpty:
    def test_empty_gt_and_pred(self):
        result = compute_extraction_metrics([], [])
        assert result.recall == pytest.approx(0.0)
        assert result.precision == pytest.approx(0.0)
        assert result.value_accuracy == pytest.approx(0.0)
        assert result.matches == []

    def test_empty_gt_with_predictions_zero_recall(self):
        pred = [_pred("ghost", 1)]
        result = compute_extraction_metrics([], pred)
        assert result.recall == pytest.approx(0.0)
        assert result.precision == pytest.approx(0.0)

    def test_empty_pred_with_gt_zero_precision(self):
        gt = [_gt("a", 1)]
        result = compute_extraction_metrics(gt, [])
        assert result.recall == pytest.approx(0.0)
        assert result.precision == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Per-attribute breakdown
# ---------------------------------------------------------------------------


class TestPerAttributeBreakdown:
    def test_per_attribute_keys_present(self):
        gt = [_gt("lot_area", 100), _gt("setback", 3.0)]
        pred = [_pred("lot_area", 100), _pred("setback", 3.0)]
        result = compute_extraction_metrics(gt, pred)
        assert "lot_area" in result.per_attribute
        assert "setback" in result.per_attribute

    def test_per_attribute_contains_required_keys(self):
        gt = [_gt("lot_area", 100)]
        pred = [_pred("lot_area", 100)]
        result = compute_extraction_metrics(gt, pred)
        attr = result.per_attribute["lot_area"]
        assert "recall" in attr
        assert "precision" in attr
        assert "value_accuracy" in attr

    def test_per_attribute_matched_attribute_perfect_scores(self):
        gt = [_gt("lot_area", 100)]
        pred = [_pred("lot_area", 100)]
        result = compute_extraction_metrics(gt, pred)
        attr = result.per_attribute["lot_area"]
        assert attr["recall"] == pytest.approx(1.0)
        assert attr["precision"] == pytest.approx(1.0)
        assert attr["value_accuracy"] == pytest.approx(1.0)

    def test_per_attribute_missed_entity_zero_recall(self):
        gt = [_gt("lot_area", 100)]
        pred = []
        result = compute_extraction_metrics(gt, pred)
        attr = result.per_attribute["lot_area"]
        assert attr["recall"] == pytest.approx(0.0)

    def test_per_attribute_hallucinated_entity_zero_precision(self):
        gt = []
        pred = [_pred("ghost_attr", 99)]
        result = compute_extraction_metrics(gt, pred)
        attr = result.per_attribute["ghost_attr"]
        assert attr["precision"] == pytest.approx(0.0)
        assert attr["recall"] == pytest.approx(0.0)

    def test_per_attribute_independent_across_attributes(self):
        gt = [_gt("a", 1), _gt("b", 2)]
        pred = [_pred("a", 1)]  # b missed
        result = compute_extraction_metrics(gt, pred)
        assert result.per_attribute["a"]["recall"] == pytest.approx(1.0)
        assert result.per_attribute["b"]["recall"] == pytest.approx(0.0)
