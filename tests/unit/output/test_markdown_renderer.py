"""Tests for MarkdownReportRenderer.

Verifies that the renderer produces correctly-structured Markdown for all
sections and omits sections when they have no content.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from planproof.output.markdown_renderer import MarkdownReportRenderer
from planproof.schemas.assessability import AssessabilityResult, BlockingReason
from planproof.schemas.entities import EntityType, ExtractedEntity, ExtractionMethod
from planproof.schemas.pipeline import (
    ComplianceReport,
    EvidenceRequest,
    MissingEvidence,
    ReportSummary,
)
from planproof.schemas.rules import RuleOutcome, RuleVerdict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS = datetime(2025, 6, 15, 9, 30, 0)
_GENERATED_AT = datetime(2025, 6, 15, 10, 0, 0)


def _entity(
    source: str = "site_plan.pdf",
    method: ExtractionMethod = ExtractionMethod.OCR_LLM,
    confidence: float = 0.92,
) -> ExtractedEntity:
    return ExtractedEntity(
        entity_type=EntityType.MEASUREMENT,
        value=6.5,
        unit="m",
        confidence=confidence,
        source_document=source,
        extraction_method=method,
        timestamp=_TS,
    )


def _verdict(
    rule_id: str = "R001",
    outcome: RuleOutcome = RuleOutcome.PASS,
    evaluated_value: object = 6.5,
    threshold: object = 6.0,
    explanation: str = "Value meets threshold.",
    evidence: list[ExtractedEntity] | None = None,
) -> RuleVerdict:
    return RuleVerdict(
        rule_id=rule_id,
        outcome=outcome,
        evidence_used=evidence or [_entity()],
        explanation=explanation,
        evaluated_value=evaluated_value,
        threshold=threshold,
    )


def _not_assessable(
    rule_id: str = "R002",
    blocking_reason: BlockingReason = BlockingReason.MISSING_EVIDENCE,
) -> AssessabilityResult:
    return AssessabilityResult(
        rule_id=rule_id,
        status="NOT_ASSESSABLE",
        blocking_reason=blocking_reason,
        missing_evidence=[],
        conflicts=[],
    )


def _summary(
    total: int = 2,
    passed: int = 1,
    failed: int = 0,
    not_assessable: int = 1,
) -> ReportSummary:
    return ReportSummary(
        total_rules=total,
        passed=passed,
        failed=failed,
        not_assessable=not_assessable,
    )


def _evidence_request(
    rule_id: str = "R002",
    attribute: str = "setback",
    guidance: str = "Provide a dimensioned site plan.",
) -> EvidenceRequest:
    return EvidenceRequest(
        rule_id=rule_id,
        missing=[
            MissingEvidence(
                attribute=attribute,
                acceptable_document_types=["DRAWING"],
                guidance=guidance,
            )
        ],
    )


def _report(
    application_id: str = "APP-001",
    verdicts: list[RuleVerdict] | None = None,
    assessability_results: list[AssessabilityResult] | None = None,
    summary: ReportSummary | None = None,
    generated_at: datetime = _GENERATED_AT,
) -> ComplianceReport:
    return ComplianceReport(
        application_id=application_id,
        verdicts=verdicts or [],
        assessability_results=assessability_results or [],
        summary=summary or _summary(total=0, passed=0, failed=0, not_assessable=0),
        generated_at=generated_at,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSummaryTable:
    def test_renders_report_heading(self) -> None:
        report = _report(application_id="APP-42")
        result = MarkdownReportRenderer().render(report)
        assert "# Compliance Report: APP-42" in result

    def test_renders_generated_at(self) -> None:
        report = _report()
        result = MarkdownReportRenderer().render(report)
        assert "Generated:" in result
        assert "2025-06-15" in result

    def test_renders_summary_section_heading(self) -> None:
        report = _report()
        result = MarkdownReportRenderer().render(report)
        assert "## Summary" in result

    def test_renders_summary_table_rows(self) -> None:
        summary = _summary(total=5, passed=3, failed=1, not_assessable=1)
        report = _report(summary=summary)
        result = MarkdownReportRenderer().render(report)
        assert "| Total Rules | 5 |" in result
        assert "| Passed | 3 |" in result
        assert "| Failed | 1 |" in result
        assert "| Not Assessable | 1 |" in result

    def test_renders_summary_table_header(self) -> None:
        report = _report()
        result = MarkdownReportRenderer().render(report)
        assert "| Metric | Count |" in result
        assert "|--------|-------|" in result


class TestPassVerdict:
    def test_renders_verdict_section_heading(self) -> None:
        report = _report(
            verdicts=[_verdict()],
            summary=_summary(total=1, passed=1, failed=0, not_assessable=0),
        )
        result = MarkdownReportRenderer().render(report)
        assert "## Rule Verdicts" in result

    def test_renders_rule_id_as_subheading(self) -> None:
        report = _report(verdicts=[_verdict(rule_id="R001")])
        result = MarkdownReportRenderer().render(report)
        assert "### R001" in result

    def test_renders_pass_outcome(self) -> None:
        report = _report(verdicts=[_verdict(outcome=RuleOutcome.PASS)])
        result = MarkdownReportRenderer().render(report)
        assert "**Verdict:** PASS" in result

    def test_renders_evaluated_value(self) -> None:
        report = _report(verdicts=[_verdict(evaluated_value=7.2)])
        result = MarkdownReportRenderer().render(report)
        assert "**Evaluated Value:** 7.2" in result

    def test_renders_threshold(self) -> None:
        report = _report(verdicts=[_verdict(threshold=6.0)])
        result = MarkdownReportRenderer().render(report)
        assert "**Threshold:** 6.0" in result

    def test_renders_evidence_source_and_method(self) -> None:
        entity = _entity(source="block_plan.pdf", method=ExtractionMethod.VLM_STRUCTURED)
        report = _report(verdicts=[_verdict(evidence=[entity])])
        result = MarkdownReportRenderer().render(report)
        assert "block_plan.pdf" in result
        assert "VLM_STRUCTURED" in result

    def test_renders_evidence_confidence(self) -> None:
        entity = _entity(confidence=0.87)
        report = _report(verdicts=[_verdict(evidence=[entity])])
        result = MarkdownReportRenderer().render(report)
        assert "0.87" in result

    def test_renders_explanation(self) -> None:
        report = _report(verdicts=[_verdict(explanation="Setback is adequate.")])
        result = MarkdownReportRenderer().render(report)
        assert "**Explanation:** Setback is adequate." in result


class TestFailVerdict:
    def test_renders_fail_outcome(self) -> None:
        report = _report(verdicts=[_verdict(outcome=RuleOutcome.FAIL)])
        result = MarkdownReportRenderer().render(report)
        assert "**Verdict:** FAIL" in result

    def test_renders_fail_evaluated_value(self) -> None:
        report = _report(verdicts=[_verdict(outcome=RuleOutcome.FAIL, evaluated_value=4.5, threshold=6.0)])
        result = MarkdownReportRenderer().render(report)
        assert "**Evaluated Value:** 4.5" in result
        assert "**Threshold:** 6.0" in result


class TestNotAssessableSection:
    def test_renders_not_assessable_heading(self) -> None:
        report = _report(
            assessability_results=[_not_assessable()],
            summary=_summary(total=1, passed=0, failed=0, not_assessable=1),
        )
        result = MarkdownReportRenderer().render(report)
        assert "## Not Assessable Rules" in result

    def test_renders_not_assessable_rule_id(self) -> None:
        report = _report(assessability_results=[_not_assessable(rule_id="R099")])
        result = MarkdownReportRenderer().render(report)
        assert "### R099" in result

    def test_renders_not_assessable_status(self) -> None:
        report = _report(assessability_results=[_not_assessable()])
        result = MarkdownReportRenderer().render(report)
        assert "**Status:** NOT_ASSESSABLE" in result

    def test_renders_blocking_reason(self) -> None:
        report = _report(
            assessability_results=[_not_assessable(blocking_reason=BlockingReason.LOW_CONFIDENCE)]
        )
        result = MarkdownReportRenderer().render(report)
        assert "**Reason:** LOW_CONFIDENCE" in result

    def test_filters_only_not_assessable_results(self) -> None:
        """ASSESSABLE results should not appear in the Not Assessable section."""
        assessable = AssessabilityResult(
            rule_id="R010",
            status="ASSESSABLE",
            blocking_reason=BlockingReason.NONE,
            missing_evidence=[],
            conflicts=[],
        )
        report = _report(assessability_results=[assessable])
        result = MarkdownReportRenderer().render(report)
        assert "## Not Assessable Rules" not in result
        assert "R010" not in result


class TestEvidenceRequestsSection:
    def test_renders_evidence_requests_heading(self) -> None:
        report = _report()
        requests = [_evidence_request()]
        result = MarkdownReportRenderer().render(report, evidence_requests=requests)
        assert "## Evidence Requests" in result

    def test_renders_evidence_request_rule_id(self) -> None:
        report = _report()
        requests = [_evidence_request(rule_id="R002")]
        result = MarkdownReportRenderer().render(report, evidence_requests=requests)
        assert "### R002" in result

    def test_renders_whats_needed_heading(self) -> None:
        report = _report()
        requests = [_evidence_request()]
        result = MarkdownReportRenderer().render(report, evidence_requests=requests)
        assert "**What's needed:**" in result

    def test_renders_attribute_and_guidance(self) -> None:
        report = _report()
        requests = [_evidence_request(attribute="height", guidance="Include elevation drawing.")]
        result = MarkdownReportRenderer().render(report, evidence_requests=requests)
        assert "- height: Include elevation drawing." in result

    def test_multiple_missing_items_rendered(self) -> None:
        request = EvidenceRequest(
            rule_id="R003",
            missing=[
                MissingEvidence(attribute="setback", acceptable_document_types=["DRAWING"], guidance="Site plan needed."),
                MissingEvidence(attribute="height", acceptable_document_types=["FORM"], guidance="Form 1 required."),
            ],
        )
        report = _report()
        result = MarkdownReportRenderer().render(report, evidence_requests=[request])
        assert "- setback: Site plan needed." in result
        assert "- height: Form 1 required." in result


class TestEmptyReport:
    def test_empty_report_renders_minimal_output(self) -> None:
        report = _report()
        result = MarkdownReportRenderer().render(report)
        assert "# Compliance Report:" in result
        assert "## Summary" in result

    def test_empty_report_has_no_verdicts_section(self) -> None:
        report = _report()
        result = MarkdownReportRenderer().render(report)
        assert "## Rule Verdicts" not in result

    def test_empty_report_has_no_not_assessable_section(self) -> None:
        report = _report()
        result = MarkdownReportRenderer().render(report)
        assert "## Not Assessable Rules" not in result

    def test_empty_report_has_no_evidence_requests_section(self) -> None:
        report = _report()
        result = MarkdownReportRenderer().render(report)
        assert "## Evidence Requests" not in result


class TestSectionOmission:
    def test_no_verdicts_section_when_verdicts_empty(self) -> None:
        report = _report(
            verdicts=[],
            assessability_results=[_not_assessable()],
        )
        result = MarkdownReportRenderer().render(report)
        assert "## Rule Verdicts" not in result

    def test_no_not_assessable_section_when_all_assessable(self) -> None:
        report = _report(
            verdicts=[_verdict()],
            assessability_results=[],
        )
        result = MarkdownReportRenderer().render(report)
        assert "## Not Assessable Rules" not in result

    def test_no_evidence_requests_section_when_none_passed(self) -> None:
        report = _report(verdicts=[_verdict()])
        result = MarkdownReportRenderer().render(report, evidence_requests=None)
        assert "## Evidence Requests" not in result

    def test_no_evidence_requests_section_when_empty_list(self) -> None:
        report = _report(verdicts=[_verdict()])
        result = MarkdownReportRenderer().render(report, evidence_requests=[])
        assert "## Evidence Requests" not in result

    def test_multiple_verdicts_all_rendered(self) -> None:
        verdicts = [
            _verdict(rule_id="R001", outcome=RuleOutcome.PASS),
            _verdict(rule_id="R002", outcome=RuleOutcome.FAIL),
        ]
        report = _report(verdicts=verdicts)
        result = MarkdownReportRenderer().render(report)
        assert "### R001" in result
        assert "### R002" in result
        assert "**Verdict:** PASS" in result
        assert "**Verdict:** FAIL" in result

    def test_multiple_evidence_requests_rendered(self) -> None:
        requests = [
            _evidence_request(rule_id="R010"),
            _evidence_request(rule_id="R011"),
        ]
        report = _report()
        result = MarkdownReportRenderer().render(report, evidence_requests=requests)
        assert "### R010" in result
        assert "### R011" in result
