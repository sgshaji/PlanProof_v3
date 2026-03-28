"""Tests for PairwiseReconciler — evidence reconciliation across sources."""
from __future__ import annotations

from datetime import datetime

import pytest

from planproof.reasoning.reconciliation import PairwiseReconciler
from planproof.schemas.entities import EntityType, ExtractedEntity, ExtractionMethod
from planproof.schemas.reconciliation import ReconciliationStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS = datetime(2024, 1, 1, 12, 0, 0)


def _entity(
    value: object,
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


# ---------------------------------------------------------------------------
# MISSING
# ---------------------------------------------------------------------------


class TestMissing:
    def test_no_entities_returns_missing(self) -> None:
        reconciler = PairwiseReconciler()
        result = reconciler.reconcile([], "site_area")

        assert result.status == ReconciliationStatus.MISSING
        assert result.best_value is None
        assert result.sources == []
        assert result.attribute == "site_area"

    def test_missing_has_no_conflict_details(self) -> None:
        reconciler = PairwiseReconciler()
        result = reconciler.reconcile([], "height")

        assert result.conflict_details is None


# ---------------------------------------------------------------------------
# SINGLE_SOURCE
# ---------------------------------------------------------------------------


class TestSingleSource:
    def test_one_entity_returns_single_source(self) -> None:
        reconciler = PairwiseReconciler()
        entity = _entity(7.5)
        result = reconciler.reconcile([entity], "height")

        assert result.status == ReconciliationStatus.SINGLE_SOURCE

    def test_single_source_best_value_is_entity_value(self) -> None:
        reconciler = PairwiseReconciler()
        entity = _entity(7.5)
        result = reconciler.reconcile([entity], "height")

        assert result.best_value == 7.5

    def test_single_source_has_one_source_entry(self) -> None:
        reconciler = PairwiseReconciler()
        entity = _entity(7.5, source="form_a.pdf")
        result = reconciler.reconcile([entity], "height")

        assert len(result.sources) == 1
        assert result.sources[0].source_document == "form_a.pdf"

    def test_single_source_string_value(self) -> None:
        reconciler = PairwiseReconciler()
        entity = _entity("Residential", entity_type=EntityType.ZONE)
        result = reconciler.reconcile([entity], "zone_type")

        assert result.status == ReconciliationStatus.SINGLE_SOURCE
        assert result.best_value == "Residential"


# ---------------------------------------------------------------------------
# AGREED — numeric
# ---------------------------------------------------------------------------


class TestAgreedNumeric:
    def test_two_values_within_tolerance_returns_agreed(self) -> None:
        reconciler = PairwiseReconciler(tolerances={"height": 0.5})
        entities = [_entity(7.5, "doc_a.pdf"), _entity(7.8, "doc_b.pdf")]
        result = reconciler.reconcile(entities, "height")

        assert result.status == ReconciliationStatus.AGREED

    def test_agreed_best_value_is_mean(self) -> None:
        reconciler = PairwiseReconciler(tolerances={"height": 0.5})
        entities = [_entity(7.5, "doc_a.pdf"), _entity(7.8, "doc_b.pdf")]
        result = reconciler.reconcile(entities, "height")

        assert result.best_value == pytest.approx(7.65)

    def test_three_values_all_within_tolerance_agreed(self) -> None:
        reconciler = PairwiseReconciler(tolerances={"area": 1.0})
        entities = [
            _entity(100.0, "doc_a.pdf"),
            _entity(100.5, "doc_b.pdf"),
            _entity(100.8, "doc_c.pdf"),
        ]
        result = reconciler.reconcile(entities, "area")

        assert result.status == ReconciliationStatus.AGREED
        assert result.best_value == pytest.approx(100.4333, rel=1e-3)

    def test_agreed_collects_all_sources(self) -> None:
        reconciler = PairwiseReconciler(tolerances={"height": 0.5})
        entities = [_entity(7.5, "doc_a.pdf"), _entity(7.8, "doc_b.pdf")]
        result = reconciler.reconcile(entities, "height")

        docs = {e.source_document for e in result.sources}
        assert docs == {"doc_a.pdf", "doc_b.pdf"}

    def test_agreed_no_conflict_details(self) -> None:
        reconciler = PairwiseReconciler(tolerances={"height": 0.5})
        entities = [_entity(7.5, "doc_a.pdf"), _entity(7.8, "doc_b.pdf")]
        result = reconciler.reconcile(entities, "height")

        assert result.conflict_details is None

    def test_default_tolerance_used_when_not_specified(self) -> None:
        # Default tolerance=0.5; values 10.0 and 10.4 agree
        reconciler = PairwiseReconciler()
        entities = [_entity(10.0, "doc_a.pdf"), _entity(10.4, "doc_b.pdf")]
        result = reconciler.reconcile(entities, "unknown_attr")

        assert result.status == ReconciliationStatus.AGREED

    def test_exactly_at_tolerance_boundary_is_agreed(self) -> None:
        reconciler = PairwiseReconciler(tolerances={"width": 0.5})
        entities = [_entity(5.0, "doc_a.pdf"), _entity(5.5, "doc_b.pdf")]
        result = reconciler.reconcile(entities, "width")

        assert result.status == ReconciliationStatus.AGREED


# ---------------------------------------------------------------------------
# CONFLICTING — numeric
# ---------------------------------------------------------------------------


class TestConflictingNumeric:
    def test_two_values_beyond_tolerance_returns_conflicting(self) -> None:
        reconciler = PairwiseReconciler(tolerances={"height": 0.5})
        entities = [_entity(7.5, "doc_a.pdf"), _entity(12.0, "doc_b.pdf")]
        result = reconciler.reconcile(entities, "height")

        assert result.status == ReconciliationStatus.CONFLICTING

    def test_conflicting_has_conflict_details(self) -> None:
        reconciler = PairwiseReconciler(tolerances={"height": 0.5})
        entities = [_entity(7.5, "doc_a.pdf"), _entity(12.0, "doc_b.pdf")]
        result = reconciler.reconcile(entities, "height")

        assert result.conflict_details is not None
        assert len(result.conflict_details) > 0

    def test_conflicting_details_mention_both_values(self) -> None:
        reconciler = PairwiseReconciler(tolerances={"height": 0.5})
        entities = [_entity(7.5, "doc_a.pdf"), _entity(12.0, "doc_b.pdf")]
        result = reconciler.reconcile(entities, "height")

        assert "7.5" in result.conflict_details  # type: ignore[operator]
        assert "12.0" in result.conflict_details  # type: ignore[operator]

    def test_conflicting_sources_include_all_entities(self) -> None:
        reconciler = PairwiseReconciler(tolerances={"height": 0.5})
        entities = [_entity(7.5, "doc_a.pdf"), _entity(12.0, "doc_b.pdf")]
        result = reconciler.reconcile(entities, "height")

        assert len(result.sources) == 2

    def test_one_pair_beyond_tolerance_in_three_entities(self) -> None:
        # Two agree but one conflicts — overall CONFLICTING
        reconciler = PairwiseReconciler(tolerances={"area": 0.5})
        entities = [
            _entity(50.0, "doc_a.pdf"),
            _entity(50.3, "doc_b.pdf"),
            _entity(60.0, "doc_c.pdf"),  # outlier
        ]
        result = reconciler.reconcile(entities, "area")

        assert result.status == ReconciliationStatus.CONFLICTING

    def test_custom_tolerance_overrides_default(self) -> None:
        # With strict tolerance 0.1, diff of 0.3 conflicts
        reconciler = PairwiseReconciler(tolerances={"setback": 0.1})
        entities = [_entity(3.0, "doc_a.pdf"), _entity(3.3, "doc_b.pdf")]
        result = reconciler.reconcile(entities, "setback")

        assert result.status == ReconciliationStatus.CONFLICTING

    def test_custom_tolerance_wider_makes_agreed(self) -> None:
        # With wide tolerance 5.0, diff of 4.5 agrees
        reconciler = PairwiseReconciler(tolerances={"setback": 5.0})
        entities = [_entity(3.0, "doc_a.pdf"), _entity(7.5, "doc_b.pdf")]
        result = reconciler.reconcile(entities, "setback")

        assert result.status == ReconciliationStatus.AGREED


# ---------------------------------------------------------------------------
# AGREED — string
# ---------------------------------------------------------------------------


class TestAgreedString:
    def test_exact_string_match_returns_agreed(self) -> None:
        reconciler = PairwiseReconciler()
        entities = [
            _entity("Residential", "doc_a.pdf", EntityType.ZONE),
            _entity("Residential", "doc_b.pdf", EntityType.ZONE),
        ]
        result = reconciler.reconcile(entities, "zone_type")

        assert result.status == ReconciliationStatus.AGREED

    def test_agreed_string_best_value_is_the_shared_value(self) -> None:
        reconciler = PairwiseReconciler()
        entities = [
            _entity("Residential", "doc_a.pdf", EntityType.ZONE),
            _entity("Residential", "doc_b.pdf", EntityType.ZONE),
        ]
        result = reconciler.reconcile(entities, "zone_type")

        assert result.best_value == "Residential"

    def test_three_identical_strings_agreed(self) -> None:
        reconciler = PairwiseReconciler()
        entities = [
            _entity("R2", "a.pdf", EntityType.ZONE),
            _entity("R2", "b.pdf", EntityType.ZONE),
            _entity("R2", "c.pdf", EntityType.ZONE),
        ]
        result = reconciler.reconcile(entities, "zone_code")

        assert result.status == ReconciliationStatus.AGREED


# ---------------------------------------------------------------------------
# CONFLICTING — string
# ---------------------------------------------------------------------------


class TestConflictingString:
    def test_string_mismatch_returns_conflicting(self) -> None:
        reconciler = PairwiseReconciler()
        entities = [
            _entity("Residential", "doc_a.pdf", EntityType.ZONE),
            _entity("Commercial", "doc_b.pdf", EntityType.ZONE),
        ]
        result = reconciler.reconcile(entities, "zone_type")

        assert result.status == ReconciliationStatus.CONFLICTING

    def test_string_conflict_has_conflict_details(self) -> None:
        reconciler = PairwiseReconciler()
        entities = [
            _entity("Residential", "doc_a.pdf", EntityType.ZONE),
            _entity("Commercial", "doc_b.pdf", EntityType.ZONE),
        ]
        result = reconciler.reconcile(entities, "zone_type")

        assert result.conflict_details is not None

    def test_string_conflict_details_mention_both_values(self) -> None:
        reconciler = PairwiseReconciler()
        entities = [
            _entity("Residential", "doc_a.pdf", EntityType.ZONE),
            _entity("Commercial", "doc_b.pdf", EntityType.ZONE),
        ]
        result = reconciler.reconcile(entities, "zone_type")

        assert "Residential" in result.conflict_details  # type: ignore[operator]
        assert "Commercial" in result.conflict_details  # type: ignore[operator]

    def test_one_mismatch_in_three_strings_is_conflicting(self) -> None:
        reconciler = PairwiseReconciler()
        entities = [
            _entity("R2", "a.pdf", EntityType.ZONE),
            _entity("R2", "b.pdf", EntityType.ZONE),
            _entity("B4", "c.pdf", EntityType.ZONE),  # outlier
        ]
        result = reconciler.reconcile(entities, "zone_code")

        assert result.status == ReconciliationStatus.CONFLICTING


# ---------------------------------------------------------------------------
# Output schema correctness
# ---------------------------------------------------------------------------


class TestOutputSchema:
    def test_attribute_propagated_in_all_statuses(self) -> None:
        reconciler = PairwiseReconciler()
        for entities, attr in [
            ([], "area"),
            ([_entity(1.0)], "area"),
            ([_entity(1.0, "a.pdf"), _entity(1.0, "b.pdf")], "area"),
        ]:
            result = reconciler.reconcile(entities, attr)  # type: ignore[arg-type]
            assert result.attribute == attr

    def test_sources_list_is_copy_not_reference(self) -> None:
        reconciler = PairwiseReconciler()
        entities = [_entity(5.0, "a.pdf"), _entity(5.0, "b.pdf")]
        result = reconciler.reconcile(entities, "height")

        # Mutating the original list does not affect the result
        entities.clear()
        assert len(result.sources) == 2
