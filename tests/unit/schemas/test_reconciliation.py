"""Tests for reconciliation schema models."""
from __future__ import annotations

from planproof.schemas.reconciliation import (
    ReconciledEvidence,
    ReconciliationStatus,
)


class TestReconciledEvidence:
    def test_agreed_result(self, sample_entity) -> None:  # type: ignore[no-untyped-def]
        result = ReconciledEvidence(
            attribute="front_setback",
            status=ReconciliationStatus.AGREED,
            best_value=7.5,
            sources=[sample_entity, sample_entity],
        )
        assert result.status == ReconciliationStatus.AGREED
        assert result.best_value == 7.5
        assert len(result.sources) == 2

    def test_conflicting_result(self, sample_entity) -> None:  # type: ignore[no-untyped-def]
        result = ReconciledEvidence(
            attribute="building_height",
            status=ReconciliationStatus.CONFLICTING,
            best_value=None,
            sources=[sample_entity],
            conflict_details="drawing says 7.5m, report says 9.2m",
        )
        assert result.status == ReconciliationStatus.CONFLICTING
        assert result.conflict_details is not None

    def test_missing_result(self) -> None:
        result = ReconciledEvidence(
            attribute="site_area",
            status=ReconciliationStatus.MISSING,
            best_value=None,
            sources=[],
        )
        assert result.status == ReconciliationStatus.MISSING
        assert result.best_value is None

    def test_json_round_trip(self) -> None:
        result = ReconciledEvidence(
            attribute="front_setback",
            status=ReconciliationStatus.SINGLE_SOURCE,
            best_value=6.0,
            sources=[],
        )
        restored = ReconciledEvidence.model_validate_json(
            result.model_dump_json()
        )
        assert restored == result
