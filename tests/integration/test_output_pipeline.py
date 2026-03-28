"""Integration tests — full output layer pipeline.

Exercises the chain: verdicts + assessability results → ComplianceReport
→ EvidenceRequests → Markdown output.

Tests use only in-process components (no Neo4j, no external services).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from planproof.output.evidence_request import MinEvidenceRequestGenerator
from planproof.output.markdown_renderer import MarkdownReportRenderer
from planproof.output.scoring import ComplianceScorer
from planproof.schemas.assessability import (
    AssessabilityResult,
    BlockingReason,
    EvidenceRequirement,
)
from planproof.schemas.entities import (
    EntityType,
    ExtractedEntity,
    ExtractionMethod,
)
from planproof.schemas.pipeline import EvidenceRequest
from planproof.schemas.rules import RuleOutcome, RuleVerdict

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_GUIDANCE_PATH = Path("configs/evidence_guidance.yaml")
_GUIDANCE_EXISTS = _GUIDANCE_PATH.exists()

# ---------------------------------------------------------------------------
# Timestamp shared across helpers
# ---------------------------------------------------------------------------

_TS = datetime(2025, 6, 1, 10, 0, 0)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_measurement_entity(
    value: float,
    source_doc: str,
    confidence: float = 0.92,
    unit: str = "metres",
) -> ExtractedEntity:
    """Return a realistic MEASUREMENT ExtractedEntity."""
    return ExtractedEntity(
        entity_type=EntityType.MEASUREMENT,
        value=value,
        unit=unit,
        confidence=confidence,
        source_document=source_doc,
        source_page=1,
        extraction_method=ExtractionMethod.OCR_LLM,
        timestamp=_TS,
    )


def _make_r001_verdict(entity: ExtractedEntity) -> RuleVerdict:
    """R001 PASS — building height 7.5 m ≤ 8.0 m threshold."""
    return RuleVerdict(
        rule_id="R001",
        outcome=RuleOutcome.PASS,
        evidence_used=[entity],
        explanation="Building height 7.5 m is within the 8.0 m limit.",
        evaluated_value=7.5,
        threshold=8.0,
    )


def _make_r002_verdict(entity: ExtractedEntity) -> RuleVerdict:
    """R002 PASS — rear garden depth 12.0 m ≥ 10.0 m threshold."""
    return RuleVerdict(
        rule_id="R002",
        outcome=RuleOutcome.PASS,
        evidence_used=[entity],
        explanation="Rear garden depth 12.0 m meets the 10.0 m minimum.",
        evaluated_value=12.0,
        threshold=10.0,
    )


def _make_assessable(rule_id: str) -> AssessabilityResult:
    """Return an ASSESSABLE result with no missing evidence or conflicts."""
    return AssessabilityResult(
        rule_id=rule_id,
        status="ASSESSABLE",
        blocking_reason=BlockingReason.NONE,
        missing_evidence=[],
        conflicts=[],
    )


def _make_not_assessable_r002() -> AssessabilityResult:
    """Return a NOT_ASSESSABLE result for R002 — rear_garden_depth missing."""
    return AssessabilityResult(
        rule_id="R002",
        status="NOT_ASSESSABLE",
        blocking_reason=BlockingReason.MISSING_EVIDENCE,
        missing_evidence=[
            EvidenceRequirement(
                attribute="rear_garden_depth",
                acceptable_sources=["DRAWING", "REPORT"],
                min_confidence=0.75,
                spatial_grounding="site_boundary",
            )
        ],
        conflicts=[],
    )


# ---------------------------------------------------------------------------
# Test 1: Full report generation
# ---------------------------------------------------------------------------


class TestFullReportGeneration:
    """ComplianceScorer produces a well-formed ComplianceReport."""

    def test_full_report_generation(self) -> None:
        height_entity = _make_measurement_entity(7.5, "elevation_DRAWING.pdf")
        garden_entity = _make_measurement_entity(12.0, "site_plan_DRAWING.pdf")

        verdicts = [
            _make_r001_verdict(height_entity),
            _make_r002_verdict(garden_entity),
        ]
        assessability = [
            _make_assessable("R001"),
            _make_assessable("R002"),
        ]

        scorer = ComplianceScorer(application_id="APP-2025-001")
        report = scorer.generate(verdicts, assessability)

        # application_id propagated correctly
        assert report.application_id == "APP-2025-001"

        # verdicts preserved
        assert len(report.verdicts) == 2
        verdict_ids = {v.rule_id for v in report.verdicts}
        assert "R001" in verdict_ids
        assert "R002" in verdict_ids

        # summary counts
        assert report.summary.total_rules == 2
        assert report.summary.passed == 2
        assert report.summary.failed == 0
        assert report.summary.not_assessable == 0

        # generated_at is a datetime
        assert isinstance(report.generated_at, datetime)

    def test_report_with_mixed_outcomes(self) -> None:
        """One PASS and one FAIL; not_assessable=0."""
        height_entity = _make_measurement_entity(7.5, "elevation_DRAWING.pdf")
        garden_entity = _make_measurement_entity(5.0, "site_plan_DRAWING.pdf")  # below threshold

        fail_verdict = RuleVerdict(
            rule_id="R002",
            outcome=RuleOutcome.FAIL,
            evidence_used=[garden_entity],
            explanation="Rear garden depth 5.0 m is below the 10.0 m minimum.",
            evaluated_value=5.0,
            threshold=10.0,
        )
        verdicts = [_make_r001_verdict(height_entity), fail_verdict]
        assessability = [_make_assessable("R001"), _make_assessable("R002")]

        scorer = ComplianceScorer(application_id="APP-2025-002")
        report = scorer.generate(verdicts, assessability)

        assert report.summary.passed == 1
        assert report.summary.failed == 1
        assert report.summary.not_assessable == 0
        assert report.summary.total_rules == 2


# ---------------------------------------------------------------------------
# Test 2: Evidence requests for NOT_ASSESSABLE rules
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _GUIDANCE_EXISTS, reason="configs/evidence_guidance.yaml not found")
class TestEvidenceRequestsForNotAssessable:
    """MinEvidenceRequestGenerator produces correct EvidenceRequests."""

    def test_evidence_requests_for_not_assessable(self) -> None:
        not_assessable_result = _make_not_assessable_r002()

        generator = MinEvidenceRequestGenerator.from_yaml(_GUIDANCE_PATH)
        requests = generator.generate_requests([not_assessable_result])

        assert len(requests) == 1, "One EvidenceRequest expected for one NOT_ASSESSABLE rule"

        req: EvidenceRequest = requests[0]
        assert req.rule_id == "R002"
        assert len(req.missing) == 1

        missing_item = req.missing[0]
        assert missing_item.attribute == "rear_garden_depth"
        # Guidance text should be non-empty and loaded from the YAML
        assert len(missing_item.guidance) > 0
        assert "rear_garden" in missing_item.guidance.lower() or "site plan" in missing_item.guidance.lower()

    def test_assessable_results_are_skipped(self) -> None:
        """ASSESSABLE results produce no evidence requests."""
        assessable = _make_assessable("R001")
        not_assessable = _make_not_assessable_r002()

        generator = MinEvidenceRequestGenerator.from_yaml(_GUIDANCE_PATH)
        requests = generator.generate_requests([assessable, not_assessable])

        # Only the NOT_ASSESSABLE entry generates a request
        assert len(requests) == 1
        assert requests[0].rule_id == "R002"

    def test_unknown_attribute_falls_back_to_generic_guidance(self) -> None:
        """Attributes not in the YAML receive a generic fallback message."""
        unknown_req = AssessabilityResult(
            rule_id="R099",
            status="NOT_ASSESSABLE",
            blocking_reason=BlockingReason.MISSING_EVIDENCE,
            missing_evidence=[
                EvidenceRequirement(
                    attribute="unknown_exotic_attribute",
                    acceptable_sources=["FORM"],
                    min_confidence=0.8,
                )
            ],
            conflicts=[],
        )

        generator = MinEvidenceRequestGenerator.from_yaml(_GUIDANCE_PATH)
        requests = generator.generate_requests([unknown_req])

        assert len(requests) == 1
        assert "unknown_exotic_attribute" in requests[0].missing[0].guidance


class TestEvidenceRequestsWithInlineGuidance:
    """MinEvidenceRequestGenerator with inline guidance (no YAML dependency)."""

    def test_evidence_requests_with_inline_guidance(self) -> None:
        guidance = {
            "rear_garden_depth": (
                "Provide a dimensioned site plan showing the rear garden depth "
                "from building rear wall to rear boundary."
            )
        }
        not_assessable_result = _make_not_assessable_r002()

        generator = MinEvidenceRequestGenerator(guidance=guidance)
        requests = generator.generate_requests([not_assessable_result])

        assert len(requests) == 1
        req = requests[0]
        assert req.rule_id == "R002"
        assert req.missing[0].attribute == "rear_garden_depth"
        assert "dimensioned site plan" in req.missing[0].guidance


# ---------------------------------------------------------------------------
# Test 3: Markdown output — complete rendering
# ---------------------------------------------------------------------------


class TestMarkdownOutputComplete:
    """MarkdownReportRenderer produces the expected sections and strings."""

    def _build_report_and_requests(self):
        height_entity = _make_measurement_entity(7.5, "elevation_DRAWING.pdf")
        garden_entity = _make_measurement_entity(12.0, "site_plan_DRAWING.pdf")

        verdicts = [
            _make_r001_verdict(height_entity),
            _make_r002_verdict(garden_entity),
        ]
        not_assessable_r003 = AssessabilityResult(
            rule_id="R003",
            status="NOT_ASSESSABLE",
            blocking_reason=BlockingReason.MISSING_EVIDENCE,
            missing_evidence=[
                EvidenceRequirement(
                    attribute="site_coverage",
                    acceptable_sources=["DRAWING", "REPORT"],
                    min_confidence=0.80,
                )
            ],
            conflicts=[],
        )
        assessability = [
            _make_assessable("R001"),
            _make_assessable("R002"),
            not_assessable_r003,
        ]

        scorer = ComplianceScorer(application_id="APP-2025-003")
        report = scorer.generate(verdicts, assessability)

        guidance = {
            "site_coverage": (
                "Provide floor plans with dimensions, or state the building "
                "footprint area and total site area."
            )
        }
        generator = MinEvidenceRequestGenerator(guidance=guidance)
        evidence_requests = generator.generate_requests(assessability)

        return report, evidence_requests

    def test_markdown_output_complete(self) -> None:
        report, evidence_requests = self._build_report_and_requests()

        renderer = MarkdownReportRenderer()
        md = renderer.render(report, evidence_requests)

        # Summary table present
        assert "## Summary" in md
        assert "| Total Rules |" in md

        # Verdict section present with PASS outcomes
        assert "## Rule Verdicts" in md
        assert "PASS" in md

        # NOT_ASSESSABLE section present
        assert "NOT_ASSESSABLE" in md

        # Evidence requests section present with "What's needed"
        assert "## Evidence Requests" in md
        assert "What's needed" in md

        # Application header present
        assert "APP-2025-003" in md

    def test_markdown_contains_rule_ids(self) -> None:
        report, evidence_requests = self._build_report_and_requests()

        renderer = MarkdownReportRenderer()
        md = renderer.render(report, evidence_requests)

        assert "R001" in md
        assert "R002" in md
        assert "R003" in md

    def test_markdown_contains_evidence_source_info(self) -> None:
        report, evidence_requests = self._build_report_and_requests()

        renderer = MarkdownReportRenderer()
        md = renderer.render(report, evidence_requests)

        # Renderer includes source_document and extraction_method from entity
        assert "elevation_DRAWING.pdf" in md or "OCR_LLM" in md

    def test_markdown_without_evidence_requests(self) -> None:
        """Rendering without evidence requests omits that section."""
        height_entity = _make_measurement_entity(7.5, "elevation_DRAWING.pdf")
        verdicts = [_make_r001_verdict(height_entity)]
        assessability = [_make_assessable("R001")]

        scorer = ComplianceScorer(application_id="APP-2025-004")
        report = scorer.generate(verdicts, assessability)

        renderer = MarkdownReportRenderer()
        md = renderer.render(report, evidence_requests=None)

        assert "## Evidence Requests" not in md
        # But verdicts and summary should still be present
        assert "## Summary" in md
        assert "## Rule Verdicts" in md


# ---------------------------------------------------------------------------
# Test 4: Empty pipeline output
# ---------------------------------------------------------------------------


class TestEmptyPipelineOutput:
    """Empty verdicts and empty assessability → minimal but valid report."""

    def test_empty_pipeline_output(self) -> None:
        scorer = ComplianceScorer(application_id="APP-EMPTY")
        report = scorer.generate(verdicts=[], assessability_results=[])

        # Report structure is valid
        assert report.application_id == "APP-EMPTY"
        assert report.verdicts == []
        assert report.assessability_results == []
        assert report.summary.total_rules == 0
        assert report.summary.passed == 0
        assert report.summary.failed == 0
        assert report.summary.not_assessable == 0
        assert isinstance(report.generated_at, datetime)

    def test_empty_pipeline_markdown_renders(self) -> None:
        """Empty report renders to valid Markdown without errors."""
        scorer = ComplianceScorer(application_id="APP-EMPTY")
        report = scorer.generate(verdicts=[], assessability_results=[])

        renderer = MarkdownReportRenderer()
        md = renderer.render(report, evidence_requests=[])

        # Must contain at least the header and summary
        assert "APP-EMPTY" in md
        assert "## Summary" in md
        # Should not raise
        assert isinstance(md, str)
        assert len(md) > 0

    def test_empty_evidence_requests(self) -> None:
        """No NOT_ASSESSABLE results → no evidence requests generated."""
        generator = MinEvidenceRequestGenerator(guidance={})
        requests = generator.generate_requests([])

        assert requests == []
