"""Tests for ComplianceScorer — compliance report generation (M10)."""
from __future__ import annotations

from datetime import datetime

from planproof.output.scoring import ComplianceScorer
from planproof.schemas.assessability import (
    AssessabilityResult,
    BlockingReason,
)
from planproof.schemas.entities import EntityType, ExtractedEntity, ExtractionMethod
from planproof.schemas.pipeline import ComplianceReport
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


# ---------------------------------------------------------------------------
# 1. Empty inputs → all zeros
# ---------------------------------------------------------------------------


class TestEmptyInputs:
    def test_empty_verdicts_and_assessability_all_zeros(self) -> None:
        scorer = ComplianceScorer()
        report = scorer.generate(verdicts=[], assessability_results=[])

        assert report.summary.total_rules == 0
        assert report.summary.passed == 0
        assert report.summary.failed == 0
        assert report.summary.not_assessable == 0

    def test_empty_inputs_returns_compliance_report(self) -> None:
        scorer = ComplianceScorer()
        report = scorer.generate(verdicts=[], assessability_results=[])

        assert isinstance(report, ComplianceReport)


# ---------------------------------------------------------------------------
# 2. All PASS verdicts → passed count correct
# ---------------------------------------------------------------------------


class TestAllPass:
    def test_all_pass_verdicts_counted(self) -> None:
        verdicts = [
            _verdict("R001", RuleOutcome.PASS),
            _verdict("R002", RuleOutcome.PASS),
            _verdict("R003", RuleOutcome.PASS),
        ]
        scorer = ComplianceScorer()
        report = scorer.generate(verdicts=verdicts, assessability_results=[])

        assert report.summary.passed == 3
        assert report.summary.failed == 0
        assert report.summary.not_assessable == 0
        assert report.summary.total_rules == 3

    def test_verdicts_passed_through_to_report(self) -> None:
        verdicts = [_verdict("R001", RuleOutcome.PASS)]
        scorer = ComplianceScorer()
        report = scorer.generate(verdicts=verdicts, assessability_results=[])

        assert report.verdicts == verdicts


# ---------------------------------------------------------------------------
# 3. Mixed PASS/FAIL → counts correct
# ---------------------------------------------------------------------------


class TestMixedPassFail:
    def test_mixed_pass_fail_counts(self) -> None:
        verdicts = [
            _verdict("R001", RuleOutcome.PASS),
            _verdict("R002", RuleOutcome.FAIL),
            _verdict("R003", RuleOutcome.PASS),
            _verdict("R004", RuleOutcome.FAIL),
            _verdict("R005", RuleOutcome.FAIL),
        ]
        scorer = ComplianceScorer()
        report = scorer.generate(verdicts=verdicts, assessability_results=[])

        assert report.summary.passed == 2
        assert report.summary.failed == 3
        assert report.summary.not_assessable == 0
        assert report.summary.total_rules == 5

    def test_all_fail_counted_correctly(self) -> None:
        verdicts = [
            _verdict("R001", RuleOutcome.FAIL),
            _verdict("R002", RuleOutcome.FAIL),
        ]
        scorer = ComplianceScorer()
        report = scorer.generate(verdicts=verdicts, assessability_results=[])

        assert report.summary.passed == 0
        assert report.summary.failed == 2


# ---------------------------------------------------------------------------
# 4. NOT_ASSESSABLE counted from assessability_results
# ---------------------------------------------------------------------------


class TestNotAssessable:
    def test_not_assessable_counted_from_assessability_results(self) -> None:
        assessability_results = [
            _assessability("R010", "NOT_ASSESSABLE", BlockingReason.MISSING_EVIDENCE),
            _assessability("R011", "NOT_ASSESSABLE", BlockingReason.LOW_CONFIDENCE),
        ]
        scorer = ComplianceScorer()
        report = scorer.generate(verdicts=[], assessability_results=assessability_results)

        assert report.summary.not_assessable == 2
        assert report.summary.total_rules == 2

    def test_assessable_results_excluded_from_not_assessable_count(self) -> None:
        assessability_results = [
            _assessability("R001", "ASSESSABLE", BlockingReason.NONE),
            _assessability("R002", "NOT_ASSESSABLE", BlockingReason.MISSING_EVIDENCE),
        ]
        scorer = ComplianceScorer()
        report = scorer.generate(verdicts=[], assessability_results=assessability_results)

        assert report.summary.not_assessable == 1

    def test_total_rules_is_verdicts_plus_not_assessable(self) -> None:
        verdicts = [
            _verdict("R001", RuleOutcome.PASS),
            _verdict("R002", RuleOutcome.FAIL),
        ]
        assessability_results = [
            _assessability("R003", "NOT_ASSESSABLE", BlockingReason.MISSING_EVIDENCE),
            # ASSESSABLE ones should not inflate total_rules
            _assessability("R001", "ASSESSABLE", BlockingReason.NONE),
            _assessability("R002", "ASSESSABLE", BlockingReason.NONE),
        ]
        scorer = ComplianceScorer()
        report = scorer.generate(verdicts=verdicts, assessability_results=assessability_results)

        # total = 2 verdicts + 1 NOT_ASSESSABLE
        assert report.summary.total_rules == 3
        assert report.summary.passed == 1
        assert report.summary.failed == 1
        assert report.summary.not_assessable == 1

    def test_assessability_results_passed_through_to_report(self) -> None:
        assessability_results = [
            _assessability("R010", "NOT_ASSESSABLE", BlockingReason.MISSING_EVIDENCE),
        ]
        scorer = ComplianceScorer()
        report = scorer.generate(verdicts=[], assessability_results=assessability_results)

        assert report.assessability_results == assessability_results


# ---------------------------------------------------------------------------
# 5. application_id flows through to the report
# ---------------------------------------------------------------------------


class TestApplicationId:
    def test_default_application_id_is_unknown(self) -> None:
        scorer = ComplianceScorer()
        report = scorer.generate(verdicts=[], assessability_results=[])

        assert report.application_id == "unknown"

    def test_custom_application_id_flows_through(self) -> None:
        scorer = ComplianceScorer(application_id="APP-2024-001")
        report = scorer.generate(verdicts=[], assessability_results=[])

        assert report.application_id == "APP-2024-001"

    def test_application_id_preserved_with_verdicts(self) -> None:
        scorer = ComplianceScorer(application_id="DA-42")
        verdicts = [_verdict("R001", RuleOutcome.PASS)]
        report = scorer.generate(verdicts=verdicts, assessability_results=[])

        assert report.application_id == "DA-42"


# ---------------------------------------------------------------------------
# 6. generated_at is a timezone-aware datetime
# ---------------------------------------------------------------------------


class TestGeneratedAt:
    def test_generated_at_is_datetime(self) -> None:
        scorer = ComplianceScorer()
        report = scorer.generate(verdicts=[], assessability_results=[])

        assert isinstance(report.generated_at, datetime)

    def test_generated_at_is_timezone_aware(self) -> None:
        scorer = ComplianceScorer()
        report = scorer.generate(verdicts=[], assessability_results=[])

        assert report.generated_at.tzinfo is not None
