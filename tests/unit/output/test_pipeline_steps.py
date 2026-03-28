"""Tests for ScoringStep and EvidenceRequestStep pipeline steps (M10-M11).

TDD: tests written first; implementation follows.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import Mock

import pytest

from planproof.interfaces.pipeline import PipelineContext, StepResult
from planproof.output.scoring import ComplianceScorer
from planproof.output.evidence_request import MinEvidenceRequestGenerator
from planproof.pipeline.steps.scoring import ScoringStep
from planproof.pipeline.steps.evidence_request import EvidenceRequestStep
from planproof.schemas.assessability import (
    AssessabilityResult,
    BlockingReason,
    EvidenceRequirement,
)
from planproof.schemas.entities import EntityType, ExtractedEntity, ExtractionMethod
from planproof.schemas.pipeline import ComplianceReport, EvidenceRequest
from planproof.schemas.rules import RuleOutcome, RuleVerdict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS = datetime(2024, 1, 1, 12, 0, 0)


def _entity() -> ExtractedEntity:
    return ExtractedEntity(
        entity_type=EntityType.MEASUREMENT,
        value=6.5,
        unit="m",
        confidence=0.95,
        source_document="plan_DRAWING.pdf",
        extraction_method=ExtractionMethod.OCR_LLM,
        timestamp=_TS,
    )


def _verdict(rule_id: str = "R001", outcome: RuleOutcome = RuleOutcome.PASS) -> RuleVerdict:
    return RuleVerdict(
        rule_id=rule_id,
        outcome=outcome,
        evidence_used=[_entity()],
        explanation="Test verdict",
        evaluated_value=6.5,
        threshold=6.0,
    )


def _assessability(
    rule_id: str = "R001",
    status: str = "ASSESSABLE",
    blocking_reason: BlockingReason = BlockingReason.NONE,
) -> AssessabilityResult:
    return AssessabilityResult(
        rule_id=rule_id,
        status=status,  # type: ignore[arg-type]
        blocking_reason=blocking_reason,
        missing_evidence=[],
        conflicts=[],
    )


def _not_assessable_with_missing(
    rule_id: str = "R001",
    missing: list[EvidenceRequirement] | None = None,
) -> AssessabilityResult:
    if missing is None:
        missing = [
            EvidenceRequirement(
                attribute="building_height",
                acceptable_sources=["elevation_drawing"],
                min_confidence=0.8,
            )
        ]
    return AssessabilityResult(
        rule_id=rule_id,
        status="NOT_ASSESSABLE",
        blocking_reason=BlockingReason.MISSING_EVIDENCE,
        missing_evidence=missing,
        conflicts=[],
    )


# =========================================================================
# SCORING STEP TESTS
# =========================================================================


class TestScoringStepName:
    """ScoringStep has correct name property."""

    def test_name_is_scoring(self) -> None:
        step = ScoringStep()
        assert step.name == "scoring"


class TestScoringStepExecuteEmptyContext:
    """execute() handles empty verdicts and assessability_results."""

    def test_empty_context_returns_success(self) -> None:
        step = ScoringStep()
        context: PipelineContext = {
            "verdicts": [],
            "assessability_results": [],
            "metadata": {"application_id": "APP-001"},
        }

        result = step.execute(context)

        assert result["success"] is True

    def test_empty_context_stores_report_in_metadata(self) -> None:
        step = ScoringStep()
        context: PipelineContext = {
            "verdicts": [],
            "assessability_results": [],
            "metadata": {"application_id": "APP-001"},
        }

        step.execute(context)

        assert "compliance_report" in context["metadata"]
        report = context["metadata"]["compliance_report"]
        assert isinstance(report, ComplianceReport)

    def test_empty_context_report_has_zero_counts(self) -> None:
        step = ScoringStep()
        context: PipelineContext = {
            "verdicts": [],
            "assessability_results": [],
            "metadata": {"application_id": "APP-001"},
        }

        step.execute(context)

        report = context["metadata"]["compliance_report"]
        assert report.summary.total_rules == 0
        assert report.summary.passed == 0
        assert report.summary.failed == 0
        assert report.summary.not_assessable == 0


class TestScoringStepExecuteWithVerdicts:
    """execute() processes verdicts and produces correct summary counts."""

    def test_mixed_verdicts_counted_correctly(self) -> None:
        step = ScoringStep()
        verdicts = [
            _verdict("R001", RuleOutcome.PASS),
            _verdict("R002", RuleOutcome.FAIL),
            _verdict("R003", RuleOutcome.PASS),
        ]
        context: PipelineContext = {
            "verdicts": verdicts,
            "assessability_results": [],
            "metadata": {"application_id": "APP-001"},
        }

        step.execute(context)

        report = context["metadata"]["compliance_report"]
        assert report.summary.passed == 2
        assert report.summary.failed == 1
        assert report.summary.not_assessable == 0
        assert report.summary.total_rules == 3

    def test_verdicts_preserved_in_report(self) -> None:
        step = ScoringStep()
        verdicts = [_verdict("R001", RuleOutcome.PASS)]
        context: PipelineContext = {
            "verdicts": verdicts,
            "assessability_results": [],
            "metadata": {"application_id": "APP-001"},
        }

        step.execute(context)

        report = context["metadata"]["compliance_report"]
        assert report.verdicts == verdicts


class TestScoringStepExecuteWithAssessability:
    """execute() counts NOT_ASSESSABLE results correctly."""

    def test_not_assessable_results_counted(self) -> None:
        step = ScoringStep()
        assessability_results = [
            _assessability("R001", "NOT_ASSESSABLE", BlockingReason.MISSING_EVIDENCE),
            _assessability("R002", "NOT_ASSESSABLE", BlockingReason.LOW_CONFIDENCE),
        ]
        context: PipelineContext = {
            "verdicts": [],
            "assessability_results": assessability_results,
            "metadata": {"application_id": "APP-001"},
        }

        step.execute(context)

        report = context["metadata"]["compliance_report"]
        assert report.summary.not_assessable == 2
        assert report.summary.total_rules == 2

    def test_assessable_results_excluded_from_counts(self) -> None:
        step = ScoringStep()
        assessability_results = [
            _assessability("R001", "ASSESSABLE", BlockingReason.NONE),
            _assessability("R002", "NOT_ASSESSABLE", BlockingReason.MISSING_EVIDENCE),
        ]
        context: PipelineContext = {
            "verdicts": [],
            "assessability_results": assessability_results,
            "metadata": {"application_id": "APP-001"},
        }

        step.execute(context)

        report = context["metadata"]["compliance_report"]
        assert report.summary.not_assessable == 1
        assert report.summary.total_rules == 1

    def test_assessability_results_preserved_in_report(self) -> None:
        step = ScoringStep()
        assessability_results = [
            _assessability("R001", "NOT_ASSESSABLE", BlockingReason.MISSING_EVIDENCE),
        ]
        context: PipelineContext = {
            "verdicts": [],
            "assessability_results": assessability_results,
            "metadata": {"application_id": "APP-001"},
        }

        step.execute(context)

        report = context["metadata"]["compliance_report"]
        assert report.assessability_results == assessability_results


class TestScoringStepExecuteMixed:
    """execute() correctly combines verdicts and assessability results."""

    def test_mixed_verdicts_and_assessability(self) -> None:
        step = ScoringStep()
        verdicts = [
            _verdict("R001", RuleOutcome.PASS),
            _verdict("R002", RuleOutcome.FAIL),
        ]
        assessability_results = [
            _assessability("R003", "NOT_ASSESSABLE", BlockingReason.MISSING_EVIDENCE),
        ]
        context: PipelineContext = {
            "verdicts": verdicts,
            "assessability_results": assessability_results,
            "metadata": {"application_id": "APP-001"},
        }

        step.execute(context)

        report = context["metadata"]["compliance_report"]
        assert report.summary.passed == 1
        assert report.summary.failed == 1
        assert report.summary.not_assessable == 1
        assert report.summary.total_rules == 3


class TestScoringStepApplicationId:
    """execute() uses application_id from context metadata."""

    def test_application_id_from_metadata(self) -> None:
        step = ScoringStep()
        context: PipelineContext = {
            "verdicts": [],
            "assessability_results": [],
            "metadata": {"application_id": "DA-42"},
        }

        step.execute(context)

        report = context["metadata"]["compliance_report"]
        assert report.application_id == "DA-42"

    def test_application_id_defaults_to_unknown(self) -> None:
        step = ScoringStep()
        context: PipelineContext = {
            "verdicts": [],
            "assessability_results": [],
            "metadata": {},
        }

        step.execute(context)

        report = context["metadata"]["compliance_report"]
        assert report.application_id == "unknown"


class TestScoringStepArtifacts:
    """execute() returns summary counts in artifacts."""

    def test_artifacts_contain_summary_counts(self) -> None:
        step = ScoringStep()
        verdicts = [
            _verdict("R001", RuleOutcome.PASS),
            _verdict("R002", RuleOutcome.FAIL),
        ]
        context: PipelineContext = {
            "verdicts": verdicts,
            "assessability_results": [],
            "metadata": {"application_id": "APP-001"},
        }

        result = step.execute(context)

        assert "artifacts" in result
        artifacts = result["artifacts"]
        assert artifacts["total_rules"] == 2
        assert artifacts["passed"] == 1
        assert artifacts["failed"] == 1
        assert artifacts["not_assessable"] == 0


# =========================================================================
# EVIDENCE REQUEST STEP TESTS
# =========================================================================


class TestEvidenceRequestStepName:
    """EvidenceRequestStep has correct name property."""

    def test_name_is_evidence_request(self) -> None:
        generator = MinEvidenceRequestGenerator(guidance={})
        step = EvidenceRequestStep(generator)
        assert step.name == "evidence_request"


class TestEvidenceRequestStepExecuteEmptyContext:
    """execute() handles empty assessability results."""

    def test_empty_context_returns_success(self) -> None:
        generator = MinEvidenceRequestGenerator(guidance={})
        step = EvidenceRequestStep(generator)
        context: PipelineContext = {
            "assessability_results": [],
            "metadata": {},
        }

        result = step.execute(context)

        assert result["success"] is True

    def test_empty_context_stores_empty_requests(self) -> None:
        generator = MinEvidenceRequestGenerator(guidance={})
        step = EvidenceRequestStep(generator)
        context: PipelineContext = {
            "assessability_results": [],
            "metadata": {},
        }

        step.execute(context)

        assert "evidence_requests" in context["metadata"]
        requests = context["metadata"]["evidence_requests"]
        assert isinstance(requests, list)
        assert len(requests) == 0


class TestEvidenceRequestStepExecuteFiltering:
    """execute() filters to NOT_ASSESSABLE results only."""

    def test_filters_to_not_assessable_only(self) -> None:
        generator = MinEvidenceRequestGenerator(guidance={})
        step = EvidenceRequestStep(generator)
        assessability_results = [
            _assessability("R001", "ASSESSABLE", BlockingReason.NONE),
            _not_assessable_with_missing("R002"),
        ]
        context: PipelineContext = {
            "assessability_results": assessability_results,
            "metadata": {},
        }

        step.execute(context)

        requests = context["metadata"]["evidence_requests"]
        assert len(requests) == 1
        assert requests[0].rule_id == "R002"

    def test_all_assessable_produces_no_requests(self) -> None:
        generator = MinEvidenceRequestGenerator(guidance={})
        step = EvidenceRequestStep(generator)
        assessability_results = [
            _assessability("R001", "ASSESSABLE", BlockingReason.NONE),
            _assessability("R002", "ASSESSABLE", BlockingReason.NONE),
        ]
        context: PipelineContext = {
            "assessability_results": assessability_results,
            "metadata": {},
        }

        step.execute(context)

        requests = context["metadata"]["evidence_requests"]
        assert len(requests) == 0

    def test_multiple_not_assessable_all_included(self) -> None:
        generator = MinEvidenceRequestGenerator(guidance={})
        step = EvidenceRequestStep(generator)
        assessability_results = [
            _not_assessable_with_missing("R001"),
            _not_assessable_with_missing("R002"),
        ]
        context: PipelineContext = {
            "assessability_results": assessability_results,
            "metadata": {},
        }

        step.execute(context)

        requests = context["metadata"]["evidence_requests"]
        assert len(requests) == 2
        rule_ids = {r.rule_id for r in requests}
        assert rule_ids == {"R001", "R002"}


class TestEvidenceRequestStepGeneratorCall:
    """execute() delegates to generator.generate_requests()."""

    def test_calls_generator_with_not_assessable(self) -> None:
        mock_generator = Mock()
        mock_generator.generate_requests.return_value = []
        step = EvidenceRequestStep(mock_generator)
        assessability_results = [
            _not_assessable_with_missing("R001"),
        ]
        context: PipelineContext = {
            "assessability_results": assessability_results,
            "metadata": {},
        }

        step.execute(context)

        mock_generator.generate_requests.assert_called_once()
        call_args = mock_generator.generate_requests.call_args[0][0]
        assert len(call_args) == 1
        assert call_args[0].rule_id == "R001"

    def test_generator_output_stored_in_metadata(self) -> None:
        expected_requests = [
            EvidenceRequest(rule_id="R001", missing=[]),
            EvidenceRequest(rule_id="R002", missing=[]),
        ]
        mock_generator = Mock()
        mock_generator.generate_requests.return_value = expected_requests
        step = EvidenceRequestStep(mock_generator)
        assessability_results = [
            _not_assessable_with_missing("R001"),
            _not_assessable_with_missing("R002"),
        ]
        context: PipelineContext = {
            "assessability_results": assessability_results,
            "metadata": {},
        }

        step.execute(context)

        assert context["metadata"]["evidence_requests"] == expected_requests


class TestEvidenceRequestStepArtifacts:
    """execute() returns request count in artifacts."""

    def test_artifacts_contain_request_count(self) -> None:
        generator = MinEvidenceRequestGenerator(guidance={})
        step = EvidenceRequestStep(generator)
        assessability_results = [
            _not_assessable_with_missing("R001"),
            _not_assessable_with_missing("R002"),
        ]
        context: PipelineContext = {
            "assessability_results": assessability_results,
            "metadata": {},
        }

        result = step.execute(context)

        assert "artifacts" in result
        assert result["artifacts"]["request_count"] == 2

    def test_zero_requests_in_artifacts(self) -> None:
        generator = MinEvidenceRequestGenerator(guidance={})
        step = EvidenceRequestStep(generator)
        context: PipelineContext = {
            "assessability_results": [],
            "metadata": {},
        }

        result = step.execute(context)

        assert result["artifacts"]["request_count"] == 0


class TestEvidenceRequestStepIntegration:
    """execute() integration with MinEvidenceRequestGenerator."""

    def test_integration_with_real_generator(self) -> None:
        guidance = {
            "building_height": "Provide elevation drawing with dimensions."
        }
        generator = MinEvidenceRequestGenerator(guidance=guidance)
        step = EvidenceRequestStep(generator)

        missing_req = EvidenceRequirement(
            attribute="building_height",
            acceptable_sources=["elevation_drawing"],
            min_confidence=0.8,
        )
        assessability_results = [
            _not_assessable_with_missing("R001", [missing_req]),
        ]
        context: PipelineContext = {
            "assessability_results": assessability_results,
            "metadata": {},
        }

        result = step.execute(context)

        assert result["success"] is True
        requests = context["metadata"]["evidence_requests"]
        assert len(requests) == 1
        assert requests[0].rule_id == "R001"
        assert len(requests[0].missing) == 1
        assert requests[0].missing[0].attribute == "building_height"
        assert requests[0].missing[0].guidance == "Provide elevation drawing with dimensions."
