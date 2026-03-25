"""Tests for pipeline output schema models."""
from __future__ import annotations

from datetime import UTC, datetime

from planproof.schemas.assessability import AssessabilityResult, BlockingReason
from planproof.schemas.pipeline import (
    ComplianceReport,
    EvidenceRequest,
    MissingEvidence,
    ReportSummary,
    StepResult,
    StepStatus,
)
from planproof.schemas.rules import RuleOutcome, RuleVerdict


class TestStepResult:
    def test_success_step(self) -> None:
        result = StepResult(
            step_name="classification",
            status=StepStatus.SUCCESS,
            outputs=[{"doc_count": 3}],
            errors=[],
            duration_ms=42.5,
        )
        assert result.status == StepStatus.SUCCESS
        assert result.errors == []

    def test_failed_step(self) -> None:
        result = StepResult(
            step_name="ocr",
            status=StepStatus.FAILED,
            outputs=[],
            errors=["RuntimeError: OCR service unavailable"],
            duration_ms=1500.0,
        )
        assert result.status == StepStatus.FAILED
        assert len(result.errors) == 1

    def test_json_round_trip(self) -> None:
        result = StepResult(
            step_name="test",
            status=StepStatus.PARTIAL,
            outputs=[],
            errors=["one doc failed"],
            duration_ms=100.0,
        )
        restored = StepResult.model_validate_json(
            result.model_dump_json()
        )
        assert restored == result


class TestEvidenceRequest:
    def test_creation(self) -> None:
        req = EvidenceRequest(
            rule_id="R001",
            missing=[
                MissingEvidence(
                    attribute="front_setback",
                    acceptable_document_types=["DRAWING"],
                    guidance="Provide a site plan showing the "
                    "front boundary setback dimension.",
                )
            ],
        )
        assert req.rule_id == "R001"
        assert len(req.missing) == 1

    def test_json_round_trip(self) -> None:
        req = EvidenceRequest(
            rule_id="R002",
            missing=[],
        )
        restored = EvidenceRequest.model_validate_json(
            req.model_dump_json()
        )
        assert restored == req


class TestComplianceReport:
    def test_empty_report(self) -> None:
        report = ComplianceReport(
            application_id="DA-2026-001",
            verdicts=[],
            assessability_results=[],
            summary=ReportSummary(
                total_rules=0,
                passed=0,
                failed=0,
                not_assessable=0,
            ),
            generated_at=datetime.now(UTC),
        )
        assert report.summary.total_rules == 0

    def test_report_with_verdicts(self) -> None:
        verdict = RuleVerdict(
            rule_id="R001",
            outcome=RuleOutcome.PASS,
            evidence_used=[],
            explanation="OK",
            evaluated_value=7.5,
            threshold=6.0,
        )
        assessability = AssessabilityResult(
            rule_id="R002",
            status="NOT_ASSESSABLE",
            blocking_reason=BlockingReason.MISSING_EVIDENCE,
            missing_evidence=[],
            conflicts=[],
        )
        report = ComplianceReport(
            application_id="DA-2026-002",
            verdicts=[verdict],
            assessability_results=[assessability],
            summary=ReportSummary(
                total_rules=2,
                passed=1,
                failed=0,
                not_assessable=1,
            ),
            generated_at=datetime.now(UTC),
        )
        assert report.summary.total_rules == 2
        assert report.summary.passed == 1
        assert report.summary.not_assessable == 1

    def test_json_round_trip(self) -> None:
        report = ComplianceReport(
            application_id="DA-2026-003",
            verdicts=[],
            assessability_results=[],
            summary=ReportSummary(
                total_rules=0,
                passed=0,
                failed=0,
                not_assessable=0,
            ),
            generated_at=datetime.now(UTC),
        )
        restored = ComplianceReport.model_validate_json(
            report.model_dump_json()
        )
        assert restored == report
