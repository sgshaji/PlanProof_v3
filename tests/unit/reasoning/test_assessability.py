"""Tests for DefaultAssessabilityEvaluator — core assessability engine.

This is the most important test suite in PlanProof: the assessability engine
is the core research contribution that distinguishes PlanProof from simple
pass/fail compliance checkers.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import MagicMock

from planproof.reasoning.assessability import DefaultAssessabilityEvaluator
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
from planproof.schemas.reconciliation import ReconciledEvidence, ReconciliationStatus
from planproof.schemas.rules import RuleConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS = datetime(2024, 1, 1, 12, 0, 0)


def _entity(
    value: Any = 6.5,
    source: str = "site_plan_DRAWING.pdf",
    confidence: float = 0.95,
    entity_type: EntityType = EntityType.MEASUREMENT,
    method: ExtractionMethod = ExtractionMethod.OCR_LLM,
) -> ExtractedEntity:
    return ExtractedEntity(
        entity_type=entity_type,
        value=value,
        unit="m",
        confidence=confidence,
        source_document=source,
        extraction_method=method,
        timestamp=_TS,
    )


def _requirement(
    attribute: str = "setback",
    acceptable_sources: list[str] | None = None,
    min_confidence: float = 0.8,
    spatial_grounding: str | None = None,
) -> EvidenceRequirement:
    return EvidenceRequirement(
        attribute=attribute,
        acceptable_sources=acceptable_sources or ["DRAWING"],
        min_confidence=min_confidence,
        spatial_grounding=spatial_grounding,
    )


def _rule(
    rule_id: str = "R001",
    required_evidence: list[EvidenceRequirement] | None = None,
) -> RuleConfig:
    return RuleConfig(
        rule_id=rule_id,
        description="Test rule",
        policy_source="Test Policy",
        evaluation_type="numeric_threshold",
        parameters={"threshold": 6.0},
        required_evidence=(
            [_requirement()] if required_evidence is None
            else required_evidence
        ),
    )


def _reconciled(
    attribute: str = "setback",
    status: ReconciliationStatus = ReconciliationStatus.AGREED,
    entities: list[ExtractedEntity] | None = None,
) -> ReconciledEvidence:
    return ReconciledEvidence(
        attribute=attribute,
        status=status,
        best_value=6.5,
        sources=entities or [],
        conflict_details=None,
    )


def _make_evaluator(
    rules: dict[str, RuleConfig] | None = None,
    evidence: list[ExtractedEntity] | None = None,
    trustworthy: bool = True,
    reconciled_status: ReconciliationStatus = ReconciliationStatus.AGREED,
) -> tuple[
    DefaultAssessabilityEvaluator,
    MagicMock,
    MagicMock,
    MagicMock,
]:
    """Create evaluator with mocked dependencies.

    Returns a tuple of (evaluator, evidence_provider, confidence_gate, reconciler).
    """
    evidence_provider = MagicMock()
    evidence_provider.get_evidence_for_rule.return_value = evidence or []

    confidence_gate = MagicMock()
    confidence_gate.is_trustworthy.return_value = trustworthy

    reconciler = MagicMock()
    reconciler.reconcile.return_value = _reconciled(status=reconciled_status)

    evaluator = DefaultAssessabilityEvaluator(
        evidence_provider=evidence_provider,
        confidence_gate=confidence_gate,
        reconciler=reconciler,
        rules=rules or {},
    )
    return evaluator, evidence_provider, confidence_gate, reconciler


# ---------------------------------------------------------------------------
# 1. All evidence present + trustworthy + agreed -> ASSESSABLE
# ---------------------------------------------------------------------------


class TestAllEvidencePresent:
    def test_assessable_when_all_requirements_met(self) -> None:
        rule = _rule(
            required_evidence=[_requirement(attribute="setback")],
        )
        entity = _entity(source="site_plan_DRAWING.pdf")

        evaluator, ep, cg, rec = _make_evaluator(
            rules={"R001": rule},
            evidence=[entity],
            trustworthy=True,
            reconciled_status=ReconciliationStatus.AGREED,
        )

        result = evaluator.evaluate("R001")

        assert result.status == "ASSESSABLE"
        assert result.blocking_reason == BlockingReason.NONE
        assert result.missing_evidence == []
        assert result.conflicts == []

    def test_assessable_with_multiple_requirements_all_met(self) -> None:
        rule = _rule(
            required_evidence=[
                _requirement(attribute="setback", acceptable_sources=["DRAWING"]),
                _requirement(attribute="height", acceptable_sources=["FORM"]),
            ],
        )
        entities = [
            _entity(source="plan_DRAWING.pdf", value=6.5),
            _entity(source="application_FORM.pdf", value=8.0),
        ]

        evaluator, ep, cg, rec = _make_evaluator(
            rules={"R001": rule},
            evidence=entities,
            trustworthy=True,
            reconciled_status=ReconciliationStatus.AGREED,
        )

        result = evaluator.evaluate("R001")

        assert result.status == "ASSESSABLE"
        assert result.blocking_reason == BlockingReason.NONE

    def test_assessable_with_single_source_reconciliation(self) -> None:
        """SINGLE_SOURCE is not a conflict — rule should still be ASSESSABLE."""
        rule = _rule(required_evidence=[_requirement()])
        entity = _entity()

        evaluator, ep, cg, rec = _make_evaluator(
            rules={"R001": rule},
            evidence=[entity],
            trustworthy=True,
            reconciled_status=ReconciliationStatus.SINGLE_SOURCE,
        )

        result = evaluator.evaluate("R001")

        assert result.status == "ASSESSABLE"
        assert result.blocking_reason == BlockingReason.NONE


# ---------------------------------------------------------------------------
# 2. Missing evidence -> NOT_ASSESSABLE + MISSING_EVIDENCE
# ---------------------------------------------------------------------------


class TestMissingEvidence:
    def test_not_assessable_when_no_evidence_at_all(self) -> None:
        rule = _rule(required_evidence=[_requirement(attribute="setback")])

        evaluator, ep, cg, rec = _make_evaluator(
            rules={"R001": rule},
            evidence=[],  # no evidence
        )

        result = evaluator.evaluate("R001")

        assert result.status == "NOT_ASSESSABLE"
        assert result.blocking_reason == BlockingReason.MISSING_EVIDENCE
        assert len(result.missing_evidence) == 1
        assert result.missing_evidence[0].attribute == "setback"

    def test_not_assessable_when_source_mismatch(self) -> None:
        """Evidence exists but from wrong document type."""
        rule = _rule(
            required_evidence=[
                _requirement(attribute="setback", acceptable_sources=["DRAWING"]),
            ],
        )
        # Entity from a FORM document, but rule requires DRAWING
        entity = _entity(source="application_FORM.pdf")

        evaluator, ep, cg, rec = _make_evaluator(
            rules={"R001": rule},
            evidence=[entity],
        )

        result = evaluator.evaluate("R001")

        assert result.status == "NOT_ASSESSABLE"
        assert result.blocking_reason == BlockingReason.MISSING_EVIDENCE
        assert len(result.missing_evidence) == 1
        assert result.missing_evidence[0].attribute == "setback"


# ---------------------------------------------------------------------------
# 3. Low confidence -> NOT_ASSESSABLE + LOW_CONFIDENCE
# ---------------------------------------------------------------------------


class TestLowConfidence:
    def test_not_assessable_when_confidence_below_gate(self) -> None:
        rule = _rule(required_evidence=[_requirement()])
        entity = _entity(source="plan_DRAWING.pdf")

        evaluator, ep, cg, rec = _make_evaluator(
            rules={"R001": rule},
            evidence=[entity],
            trustworthy=False,  # confidence gate rejects
        )

        result = evaluator.evaluate("R001")

        assert result.status == "NOT_ASSESSABLE"
        assert result.blocking_reason == BlockingReason.LOW_CONFIDENCE

    def test_low_confidence_when_all_entities_rejected(self) -> None:
        """Multiple entities exist but all are below confidence threshold."""
        rule = _rule(required_evidence=[_requirement()])
        entities = [
            _entity(source="plan1_DRAWING.pdf", confidence=0.3),
            _entity(source="plan2_DRAWING.pdf", confidence=0.4),
        ]

        evaluator, ep, cg, rec = _make_evaluator(
            rules={"R001": rule},
            evidence=entities,
            trustworthy=False,
        )

        result = evaluator.evaluate("R001")

        assert result.status == "NOT_ASSESSABLE"
        assert result.blocking_reason == BlockingReason.LOW_CONFIDENCE


# ---------------------------------------------------------------------------
# 4. Conflicting evidence -> NOT_ASSESSABLE + CONFLICTING_EVIDENCE
# ---------------------------------------------------------------------------


class TestConflictingEvidence:
    def test_not_assessable_when_reconciler_reports_conflict(self) -> None:
        rule = _rule(required_evidence=[_requirement(attribute="setback")])
        entities = [
            _entity(source="plan1_DRAWING.pdf", value=6.0),
            _entity(source="plan2_DRAWING.pdf", value=8.0),
        ]

        evaluator, ep, cg, rec = _make_evaluator(
            rules={"R001": rule},
            evidence=entities,
            trustworthy=True,
            reconciled_status=ReconciliationStatus.CONFLICTING,
        )

        result = evaluator.evaluate("R001")

        assert result.status == "NOT_ASSESSABLE"
        assert result.blocking_reason == BlockingReason.CONFLICTING_EVIDENCE
        assert len(result.conflicts) >= 1

    def test_conflict_detail_populated(self) -> None:
        """The conflict detail should capture attribute, values, and sources."""
        rule = _rule(required_evidence=[_requirement(attribute="setback")])
        e1 = _entity(source="plan1_DRAWING.pdf", value=6.0)
        e2 = _entity(source="plan2_DRAWING.pdf", value=8.0)

        evaluator, ep, cg, rec = _make_evaluator(
            rules={"R001": rule},
            evidence=[e1, e2],
            trustworthy=True,
        )
        # Set reconciler to return CONFLICTING with details
        rec.reconcile.return_value = ReconciledEvidence(
            attribute="setback",
            status=ReconciliationStatus.CONFLICTING,
            best_value=None,
            sources=[e1, e2],
            conflict_details="Values 6.0 and 8.0 differ",
        )

        result = evaluator.evaluate("R001")

        assert result.status == "NOT_ASSESSABLE"
        assert result.blocking_reason == BlockingReason.CONFLICTING_EVIDENCE
        assert any(c.attribute == "setback" for c in result.conflicts)


# ---------------------------------------------------------------------------
# 5. Multiple requirements, partial met -> NOT_ASSESSABLE listing missing
# ---------------------------------------------------------------------------


class TestPartialRequirements:
    def test_partial_met_lists_missing_requirements(self) -> None:
        rule = _rule(
            required_evidence=[
                _requirement(attribute="setback", acceptable_sources=["DRAWING"]),
                _requirement(attribute="height", acceptable_sources=["REPORT"]),
            ],
        )
        # Only setback evidence available (from DRAWING), not height (from REPORT)
        entity = _entity(source="plan_DRAWING.pdf")

        evaluator, ep, cg, rec = _make_evaluator(
            rules={"R001": rule},
            evidence=[entity],
            trustworthy=True,
            reconciled_status=ReconciliationStatus.AGREED,
        )

        result = evaluator.evaluate("R001")

        assert result.status == "NOT_ASSESSABLE"
        assert result.blocking_reason == BlockingReason.MISSING_EVIDENCE
        missing_attrs = [m.attribute for m in result.missing_evidence]
        assert "height" in missing_attrs
        # setback should NOT be in missing
        assert "setback" not in missing_attrs

    def test_three_requirements_two_missing(self) -> None:
        rule = _rule(
            required_evidence=[
                _requirement(attribute="setback", acceptable_sources=["DRAWING"]),
                _requirement(attribute="height", acceptable_sources=["REPORT"]),
                _requirement(attribute="fsr", acceptable_sources=["FORM"]),
            ],
        )
        entity = _entity(source="plan_DRAWING.pdf")

        evaluator, ep, cg, rec = _make_evaluator(
            rules={"R001": rule},
            evidence=[entity],
            trustworthy=True,
        )

        result = evaluator.evaluate("R001")

        assert result.status == "NOT_ASSESSABLE"
        missing_attrs = [m.attribute for m in result.missing_evidence]
        assert "height" in missing_attrs
        assert "fsr" in missing_attrs
        assert len(result.missing_evidence) == 2


# ---------------------------------------------------------------------------
# 6. Unknown rule_id -> NOT_ASSESSABLE
# ---------------------------------------------------------------------------


class TestUnknownRule:
    def test_unknown_rule_returns_not_assessable(self) -> None:
        evaluator, _, _, _ = _make_evaluator(rules={})

        result = evaluator.evaluate("NONEXISTENT")

        assert result.status == "NOT_ASSESSABLE"
        assert result.blocking_reason == BlockingReason.MISSING_EVIDENCE
        assert result.rule_id == "NONEXISTENT"

    def test_unknown_rule_has_empty_conflicts_and_missing(self) -> None:
        evaluator, _, _, _ = _make_evaluator(rules={})

        result = evaluator.evaluate("NONEXISTENT")

        assert result.conflicts == []
        assert result.missing_evidence == []


# ---------------------------------------------------------------------------
# 7. Rule with no required_evidence -> ASSESSABLE (vacuously true)
# ---------------------------------------------------------------------------


class TestVacuouslyTrue:
    def test_no_requirements_is_assessable(self) -> None:
        rule = _rule(required_evidence=[])

        evaluator, _, _, _ = _make_evaluator(rules={"R001": rule})

        result = evaluator.evaluate("R001")

        assert result.status == "ASSESSABLE"
        assert result.blocking_reason == BlockingReason.NONE
        assert result.missing_evidence == []
        assert result.conflicts == []


# ---------------------------------------------------------------------------
# 8. Mixed: some met, one has low confidence -> NOT_ASSESSABLE + LOW_CONFIDENCE
# ---------------------------------------------------------------------------


class TestMixedConfidence:
    def test_one_requirement_low_confidence(self) -> None:
        """One requirement met with good confidence, another has low confidence."""
        rule = _rule(
            required_evidence=[
                _requirement(attribute="setback", acceptable_sources=["DRAWING"]),
                _requirement(attribute="height", acceptable_sources=["FORM"]),
            ],
        )
        e1 = _entity(source="plan_DRAWING.pdf", confidence=0.95)
        e2 = _entity(source="app_FORM.pdf", confidence=0.3)

        evidence_provider = MagicMock()
        evidence_provider.get_evidence_for_rule.return_value = [e1, e2]

        confidence_gate = MagicMock()
        # e1 is trustworthy, e2 is not
        confidence_gate.is_trustworthy.side_effect = lambda e: e.confidence >= 0.8

        reconciler = MagicMock()
        reconciler.reconcile.return_value = _reconciled(
            status=ReconciliationStatus.AGREED,
        )

        evaluator = DefaultAssessabilityEvaluator(
            evidence_provider=evidence_provider,
            confidence_gate=confidence_gate,
            reconciler=reconciler,
            rules={"R001": rule},
        )

        result = evaluator.evaluate("R001")

        assert result.status == "NOT_ASSESSABLE"
        assert result.blocking_reason == BlockingReason.LOW_CONFIDENCE


# ---------------------------------------------------------------------------
# Edge cases and priority ordering
# ---------------------------------------------------------------------------


class TestBlockingReasonPriority:
    """MISSING_EVIDENCE should take priority over LOW_CONFIDENCE when both exist."""

    def test_missing_takes_priority_over_low_confidence(self) -> None:
        rule = _rule(
            required_evidence=[
                _requirement(attribute="setback", acceptable_sources=["DRAWING"]),
                _requirement(attribute="height", acceptable_sources=["REPORT"]),
            ],
        )
        # setback available but low confidence, height completely missing
        e1 = _entity(source="plan_DRAWING.pdf", confidence=0.3)

        evidence_provider = MagicMock()
        evidence_provider.get_evidence_for_rule.return_value = [e1]

        confidence_gate = MagicMock()
        confidence_gate.is_trustworthy.return_value = False

        reconciler = MagicMock()
        reconciler.reconcile.return_value = _reconciled()

        evaluator = DefaultAssessabilityEvaluator(
            evidence_provider=evidence_provider,
            confidence_gate=confidence_gate,
            reconciler=reconciler,
            rules={"R001": rule},
        )

        result = evaluator.evaluate("R001")

        assert result.status == "NOT_ASSESSABLE"
        # Missing evidence is more fundamental than low confidence
        assert result.blocking_reason == BlockingReason.MISSING_EVIDENCE

    def test_conflict_takes_priority_over_low_confidence(self) -> None:
        """If evidence conflicts AND has low confidence, report conflict."""
        rule = _rule(
            required_evidence=[_requirement(attribute="setback")],
        )
        entities = [
            _entity(source="plan1_DRAWING.pdf", value=6.0),
            _entity(source="plan2_DRAWING.pdf", value=8.0),
        ]

        evaluator, ep, cg, rec = _make_evaluator(
            rules={"R001": rule},
            evidence=entities,
            trustworthy=True,
            reconciled_status=ReconciliationStatus.CONFLICTING,
        )

        result = evaluator.evaluate("R001")

        assert result.blocking_reason == BlockingReason.CONFLICTING_EVIDENCE


class TestSpatialGrounding:
    def test_spatial_grounding_met_when_evidence_exists(self) -> None:
        """For now, spatial grounding is met if evidence exists (deferred)."""
        rule = _rule(
            required_evidence=[
                _requirement(
                    attribute="setback",
                    spatial_grounding="site boundary on Block Plan",
                ),
            ],
        )
        entity = _entity(source="block_plan_DRAWING.pdf")

        evaluator, _, _, _ = _make_evaluator(
            rules={"R001": rule},
            evidence=[entity],
            trustworthy=True,
            reconciled_status=ReconciliationStatus.AGREED,
        )

        result = evaluator.evaluate("R001")

        assert result.status == "ASSESSABLE"


class TestResultSchema:
    """Verify the result always has the correct shape."""

    def test_result_has_rule_id(self) -> None:
        rule = _rule(rule_id="R042", required_evidence=[])
        evaluator, _, _, _ = _make_evaluator(rules={"R042": rule})

        result = evaluator.evaluate("R042")

        assert result.rule_id == "R042"

    def test_result_is_assessability_result(self) -> None:
        rule = _rule(required_evidence=[])
        evaluator, _, _, _ = _make_evaluator(rules={"R001": rule})

        result = evaluator.evaluate("R001")

        assert isinstance(result, AssessabilityResult)
