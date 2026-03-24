"""Tests for assessability schema models."""

from __future__ import annotations

from planproof.schemas.assessability import (
    AssessabilityResult,
    BlockingReason,
    ConflictDetail,
    EvidenceRequirement,
)


class TestAssessabilityResult:
    def test_assessable_result(self) -> None:
        result = AssessabilityResult(
            rule_id="R001",
            status="ASSESSABLE",
            blocking_reason=BlockingReason.NONE,
            missing_evidence=[],
            conflicts=[],
        )
        assert result.status == "ASSESSABLE"
        assert result.blocking_reason == BlockingReason.NONE

    def test_not_assessable_missing_evidence(self) -> None:
        result = AssessabilityResult(
            rule_id="R001",
            status="NOT_ASSESSABLE",
            blocking_reason=BlockingReason.MISSING_EVIDENCE,
            missing_evidence=[
                EvidenceRequirement(
                    attribute="building_height",
                    acceptable_sources=["DRAWING", "REPORT"],
                    min_confidence=0.80,
                    spatial_grounding=None,
                )
            ],
            conflicts=[],
        )
        assert result.status == "NOT_ASSESSABLE"
        assert len(result.missing_evidence) == 1
        assert result.missing_evidence[0].attribute == "building_height"

    def test_not_assessable_conflicting_evidence(self) -> None:
        result = AssessabilityResult(
            rule_id="R001",
            status="NOT_ASSESSABLE",
            blocking_reason=BlockingReason.CONFLICTING_EVIDENCE,
            missing_evidence=[],
            conflicts=[
                ConflictDetail(
                    attribute="building_height",
                    values=[7.5, 9.2],
                    sources=["drawing.pdf", "report.pdf"],
                )
            ],
        )
        assert len(result.conflicts) == 1

    def test_json_round_trip(self) -> None:
        result = AssessabilityResult(
            rule_id="R002",
            status="ASSESSABLE",
            blocking_reason=BlockingReason.NONE,
            missing_evidence=[],
            conflicts=[],
        )
        restored = AssessabilityResult.model_validate_json(
            result.model_dump_json()
        )
        assert restored == result
