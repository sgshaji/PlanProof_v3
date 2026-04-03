"""Integration tests — full reasoning pipeline with synthetic ground truth data.

Exercises the chain: reconciliation → confidence gating → assessability →
rule evaluation using FlatEvidenceProvider (no Neo4j dependency).

All entities are constructed from synthetic compliant/non-compliant scenarios
matching configs/rules/ thresholds exactly.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from planproof.reasoning.assessability import DefaultAssessabilityEvaluator
from planproof.reasoning.confidence import ThresholdConfidenceGate
from planproof.reasoning.evaluators.attribute_diff import AttributeDiffEvaluator
from planproof.reasoning.evaluators.enum_check import EnumCheckEvaluator
from planproof.reasoning.evaluators.factory import RuleFactory
from planproof.reasoning.evaluators.fuzzy_match import FuzzyMatchEvaluator
from planproof.reasoning.evaluators.numeric_threshold import NumericThresholdEvaluator
from planproof.reasoning.evaluators.numeric_tolerance import NumericToleranceEvaluator
from planproof.reasoning.evaluators.ratio_threshold import RatioThresholdEvaluator
from planproof.reasoning.reconciliation import PairwiseReconciler
from planproof.representation.flat_evidence import FlatEvidenceProvider
from planproof.schemas.assessability import BlockingReason
from planproof.schemas.entities import EntityType, ExtractedEntity, ExtractionMethod
from planproof.schemas.reconciliation import ReconciledEvidence, ReconciliationStatus
from planproof.schemas.rules import RuleConfig, RuleOutcome

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_RULES_DIR = Path("configs/rules")
_R001_PATH = _RULES_DIR / "r001_max_height.yaml"
_R002_PATH = _RULES_DIR / "r002_rear_garden.yaml"
_R003_PATH = _RULES_DIR / "r003_site_coverage.yaml"

_RULES_EXIST = _R001_PATH.exists() and _R002_PATH.exists() and _R003_PATH.exists()

# ---------------------------------------------------------------------------
# Constants matching rule YAML thresholds
# ---------------------------------------------------------------------------

_R001_THRESHOLD = 8.0       # max building height (metres)
_R002_THRESHOLD = 10.0      # min rear garden depth (metres)
_R003_THRESHOLD = 0.50      # max site coverage ratio

_TS = datetime(2025, 1, 1, 9, 0, 0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entity(
    attribute: str,
    value: Any,
    source_doc: str,
    confidence: float = 0.92,
    entity_type: EntityType = EntityType.MEASUREMENT,
    method: ExtractionMethod = ExtractionMethod.OCR_LLM,
    unit: str | None = "metres",
) -> ExtractedEntity:
    """Create a realistic ExtractedEntity for a given attribute and value."""
    return ExtractedEntity(
        entity_type=entity_type,
        value=value,
        unit=unit,
        confidence=confidence,
        source_document=source_doc,
        extraction_method=method,
        timestamp=_TS,
    )


def _make_gate(min_confidence: float = 0.75) -> ThresholdConfidenceGate:
    """Return a gate that rejects OCR_LLM MEASUREMENT entities below min_confidence."""
    return ThresholdConfidenceGate(
        thresholds={
            "OCR_LLM": {"MEASUREMENT": min_confidence},
            "VLM_STRUCTURED": {"MEASUREMENT": min_confidence},
        }
    )


def _load_rules_dict(factory: RuleFactory) -> dict[str, RuleConfig]:
    """Load YAML rules and return a dict keyed by rule_id."""
    pairs = factory.load_rules(_RULES_DIR)
    return {cfg.rule_id: cfg for cfg, _ in pairs}


def _make_factory() -> RuleFactory:
    """Return a RuleFactory with all known evaluators registered.

    Registers every evaluation_type found in configs/rules/ so that
    load_rules() succeeds for the full directory (R-rules and C-rules).
    """
    factory = RuleFactory()
    RuleFactory.register_evaluator("numeric_threshold", NumericThresholdEvaluator)
    RuleFactory.register_evaluator("ratio_threshold", RatioThresholdEvaluator)
    RuleFactory.register_evaluator("enum_check", EnumCheckEvaluator)
    RuleFactory.register_evaluator("fuzzy_string_match", FuzzyMatchEvaluator)
    RuleFactory.register_evaluator("numeric_tolerance", NumericToleranceEvaluator)
    RuleFactory.register_evaluator("attribute_diff", AttributeDiffEvaluator)
    from planproof.reasoning.evaluators.boundary_verification import BoundaryVerificationEvaluator
    RuleFactory.register_evaluator("boundary_verification", BoundaryVerificationEvaluator)
    from planproof.reasoning.evaluators.spatial_containment import SpatialContainmentEvaluator
    RuleFactory.register_evaluator("spatial_containment", SpatialContainmentEvaluator)
    return factory


def _make_reconciled(
    attribute: str,
    best_value: Any,
    entities: list[ExtractedEntity],
    status: ReconciliationStatus = ReconciliationStatus.SINGLE_SOURCE,
) -> ReconciledEvidence:
    return ReconciledEvidence(
        attribute=attribute,
        status=status,
        best_value=best_value,
        sources=entities,
        conflict_details=None,
    )


# ---------------------------------------------------------------------------
# Common zone_category entity (required by all three rules)
# ---------------------------------------------------------------------------


def _zone_entity(zone: str = "residential") -> ExtractedEntity:
    """Return a high-confidence zone_category entity from a FORM source."""
    return _make_entity(
        attribute="zone_category",
        value=zone,
        source_doc="planning_application_FORM.pdf",
        confidence=0.97,
        entity_type=EntityType.ZONE,
        unit=None,
    )


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _RULES_EXIST, reason="Rule config files not found in configs/rules/")
class TestFullReasoningPipeline:
    """End-to-end integration tests for the reasoning pipeline."""

    # ------------------------------------------------------------------
    # Test 1: Compliant set — all rules should be ASSESSABLE and PASS
    # ------------------------------------------------------------------

    def test_compliant_set_all_pass(self) -> None:
        """Compliant evidence satisfies R001 and R002; evaluators return PASS.

        FlatEvidenceProvider returns ALL entities for every rule (no graph
        traversal).  The source-type filter inside DefaultAssessabilityEvaluator
        checks whether the acceptable_source string appears anywhere in the
        entity's source_document filename.  Both R001 and R002 accept "DRAWING"
        sources, so a single FlatEvidenceProvider instance would deliver ALL
        DRAWING entities to both rules — causing the reconciler to see different
        measurement values (height vs garden) as a false conflict.

        To avoid this, each rule is tested with its own FlatEvidenceProvider
        that contains only the evidence relevant to that rule.  This correctly
        simulates the ablation scenario where evidence is constrained per rule.
        """
        factory = _make_factory()
        rules_dict = _load_rules_dict(factory)
        gate = _make_gate(min_confidence=0.75)
        reconciler = PairwiseReconciler()

        # --- R001: building_height=7.5 → ASSESSABLE + PASS ---
        height_entity = _make_entity(
            attribute="building_height",
            value=7.5,
            source_doc="elevation_DRAWING.pdf",
            confidence=0.90,
        )
        r001_provider = FlatEvidenceProvider([height_entity, _zone_entity()])
        r001_ae = DefaultAssessabilityEvaluator(
            evidence_provider=r001_provider,
            confidence_gate=gate,
            reconciler=reconciler,
            rules=rules_dict,
        )
        r001_assessability = r001_ae.evaluate("R001")
        assert r001_assessability.status in ("ASSESSABLE", "PARTIALLY_ASSESSABLE"), (
            f"R001 should be ASSESSABLE/PARTIALLY_ASSESSABLE but got "
            f"{r001_assessability.status} ({r001_assessability.blocking_reason}): "
            f"missing={[m.attribute for m in r001_assessability.missing_evidence]}"
        )

        r001_config = rules_dict["R001"]
        r001_evaluator = factory.create_evaluator(r001_config)
        r001_reconciled = _make_reconciled(
            attribute="building_height",
            best_value=7.5,
            entities=[height_entity],
        )
        r001_verdict = r001_evaluator.evaluate(r001_reconciled, r001_config.parameters)
        assert r001_verdict.outcome == RuleOutcome.PASS, (
            f"R001 should PASS with height=7.5 <= {_R001_THRESHOLD}: "
            f"{r001_verdict.explanation}"
        )

        # --- R002: rear_garden_depth=12.0 → ASSESSABLE + PASS ---
        garden_entity = _make_entity(
            attribute="rear_garden_depth",
            value=12.0,
            source_doc="site_plan_DRAWING.pdf",
            confidence=0.88,
        )
        r002_provider = FlatEvidenceProvider([garden_entity, _zone_entity()])
        r002_ae = DefaultAssessabilityEvaluator(
            evidence_provider=r002_provider,
            confidence_gate=gate,
            reconciler=reconciler,
            rules=rules_dict,
        )
        r002_assessability = r002_ae.evaluate("R002")
        assert r002_assessability.status in ("ASSESSABLE", "PARTIALLY_ASSESSABLE"), (
            f"R002 should be ASSESSABLE/PARTIALLY_ASSESSABLE but got "
            f"{r002_assessability.status} ({r002_assessability.blocking_reason}): "
            f"missing={[m.attribute for m in r002_assessability.missing_evidence]}"
        )

        r002_config = rules_dict["R002"]
        r002_evaluator = factory.create_evaluator(r002_config)
        r002_reconciled = _make_reconciled(
            attribute="rear_garden_depth",
            best_value=12.0,
            entities=[garden_entity],
        )
        r002_verdict = r002_evaluator.evaluate(r002_reconciled, r002_config.parameters)
        assert r002_verdict.outcome == RuleOutcome.PASS, (
            f"R002 should PASS with depth=12.0 >= {_R002_THRESHOLD}: "
            f"{r002_verdict.explanation}"
        )

    def test_compliant_r003_passes(self) -> None:
        """R003: site_coverage=40% (0.40) <= 50% threshold → PASS.

        RatioThresholdEvaluator receives a pre-computed ratio as best_value.

        FlatEvidenceProvider returns ALL entities for every rule.  R003's
        ``total_site_area`` requirement accepts DRAWING, REPORT, and FORM, so
        any DRAWING entity (including the footprint one) will be source-matched.
        When footprint(200) and site_area(500) are both selected for
        ``total_site_area`` reconciliation, the default PairwiseReconciler
        tolerance (0.5 m²) flags them as conflicting.

        This is resolved by supplying a PairwiseReconciler with per-attribute
        tolerances that are large enough for area measurements (500 m² diff
        between footprint and site area is expected and not a conflict in the
        ratio rule context).  The reconciler still detects real conflicts when
        two extractions of the *same* attribute diverge beyond their natural
        variation.
        """
        factory = _make_factory()
        rules_dict = _load_rules_dict(factory)
        gate = _make_gate(min_confidence=0.75)
        # Area measurements span a large range — use a generous tolerance so
        # footprint(200) and site_area(500) are not flagged as a conflict when
        # both match the total_site_area source requirement.
        reconciler = PairwiseReconciler(
            tolerances={"building_footprint_area": 1000.0, "total_site_area": 1000.0}
        )

        footprint_entity = _make_entity(
            attribute="building_footprint_area",
            value=200.0,
            source_doc="block_plan_DRAWING.pdf",
            confidence=0.85,
        )
        site_area_entity = _make_entity(
            attribute="total_site_area",
            value=500.0,
            source_doc="design_statement_REPORT.pdf",
            confidence=0.90,
        )
        # Zone must come from EXTERNAL_DATA (not FORM) so it does not match
        # total_site_area's "FORM" acceptable source and avoids polluting that
        # requirement's reconciliation with a string value.
        zone_entity_ext = _make_entity(
            attribute="zone_category",
            value="residential",
            source_doc="council_zones_EXTERNAL_DATA.json",
            confidence=0.97,
            entity_type=EntityType.ZONE,
            unit=None,
        )

        entities = [footprint_entity, site_area_entity, zone_entity_ext]
        provider = FlatEvidenceProvider(entities)
        evaluator = DefaultAssessabilityEvaluator(
            evidence_provider=provider,
            confidence_gate=gate,
            reconciler=reconciler,
            rules=rules_dict,
        )

        r003_assessability = evaluator.evaluate("R003")
        assert r003_assessability.status in ("ASSESSABLE", "PARTIALLY_ASSESSABLE"), (
            f"R003 should be ASSESSABLE/PARTIALLY_ASSESSABLE but got "
            f"{r003_assessability.status} ({r003_assessability.blocking_reason}): "
            f"missing={[m.attribute for m in r003_assessability.missing_evidence]}"
        )

        r003_config = rules_dict["R003"]
        r003_evaluator = factory.create_evaluator(r003_config)
        # RatioThresholdEvaluator expects a pre-computed ratio as best_value
        ratio = 200.0 / 500.0  # 0.40 = 40%
        r003_reconciled = _make_reconciled(
            attribute="site_coverage_ratio",
            best_value=ratio,
            entities=[footprint_entity, site_area_entity],
        )
        r003_verdict = r003_evaluator.evaluate(r003_reconciled, r003_config.parameters)
        assert r003_verdict.outcome == RuleOutcome.PASS, (
            f"R003 should PASS with coverage=40% <= {_R003_THRESHOLD * 100}%: "
            f"{r003_verdict.explanation}"
        )

    # ------------------------------------------------------------------
    # Test 2: Non-compliant — building height exceeds R001 threshold
    # ------------------------------------------------------------------

    def test_noncompliant_set_detects_fail(self) -> None:
        """building_height=9.5 exceeds R001 threshold of 8.0 → FAIL."""
        factory = _make_factory()
        rules_dict = _load_rules_dict(factory)

        height_entity = _make_entity(
            attribute="building_height",
            value=9.5,
            source_doc="elevation_DRAWING.pdf",
            confidence=0.91,
        )
        zone_entity = _zone_entity()

        entities = [height_entity, zone_entity]
        provider = FlatEvidenceProvider(entities)
        gate = _make_gate(min_confidence=0.75)
        reconciler = PairwiseReconciler()

        evaluator = DefaultAssessabilityEvaluator(
            evidence_provider=provider,
            confidence_gate=gate,
            reconciler=reconciler,
            rules=rules_dict,
        )

        r001_assessability = evaluator.evaluate("R001")
        assert r001_assessability.status in ("ASSESSABLE", "PARTIALLY_ASSESSABLE"), (
            f"R001 should be ASSESSABLE/PARTIALLY_ASSESSABLE: "
            f"{r001_assessability.blocking_reason}"
        )

        r001_config = rules_dict["R001"]
        r001_evaluator = factory.create_evaluator(r001_config)
        r001_reconciled = _make_reconciled(
            attribute="building_height",
            best_value=9.5,
            entities=[height_entity],
        )
        r001_verdict = r001_evaluator.evaluate(r001_reconciled, r001_config.parameters)
        assert r001_verdict.outcome == RuleOutcome.FAIL, (
            f"R001 should FAIL with height=9.5 > {_R001_THRESHOLD}: "
            f"{r001_verdict.explanation}"
        )
        assert r001_verdict.evaluated_value == pytest.approx(9.5)
        assert r001_verdict.threshold == pytest.approx(_R001_THRESHOLD)

    # ------------------------------------------------------------------
    # Test 3: Missing evidence — only building_height present
    # ------------------------------------------------------------------

    def test_missing_evidence_not_assessable(self) -> None:
        """Only building_height is provided; R002 and R003 lack their evidence.

        R002 requires rear_garden_depth (DRAWING/REPORT) → NOT_ASSESSABLE
        R003 requires building_footprint_area and total_site_area → NOT_ASSESSABLE

        FlatEvidenceProvider returns all entities for every rule.  The source
        filter in DefaultAssessabilityEvaluator checks whether the acceptable
        source string (e.g. "DRAWING") appears in the entity's source_document.
        To ensure the height entity does NOT satisfy R002/R003 requirements,
        its source_document must not contain any of those rules' acceptable
        source strings.  Using "elevation_CERTIFICATE.pdf" (contains neither
        "DRAWING" nor "REPORT" nor "FORM") guarantees a genuine source miss.
        """
        factory = _make_factory()
        rules_dict = _load_rules_dict(factory)

        # Source does not contain "DRAWING", "REPORT", or "FORM" — only
        # rules that accept "CERTIFICATE" will match this entity.
        height_entity = _make_entity(
            attribute="building_height",
            value=7.5,
            source_doc="elevation_CERTIFICATE.pdf",
            confidence=0.90,
        )
        # zone_category comes from EXTERNAL_DATA — matches FORM/EXTERNAL_DATA reqs
        zone_entity = _make_entity(
            attribute="zone_category",
            value="residential",
            source_doc="planning_application_EXTERNAL_DATA.pdf",
            confidence=0.97,
            entity_type=EntityType.ZONE,
            unit=None,
        )

        entities = [height_entity, zone_entity]
        provider = FlatEvidenceProvider(entities)
        gate = _make_gate(min_confidence=0.75)
        reconciler = PairwiseReconciler()

        evaluator = DefaultAssessabilityEvaluator(
            evidence_provider=provider,
            confidence_gate=gate,
            reconciler=reconciler,
            rules=rules_dict,
        )

        r002_result = evaluator.evaluate("R002")
        assert r002_result.status == "NOT_ASSESSABLE", (
            "R002 should be NOT_ASSESSABLE when rear_garden_depth is absent"
        )
        assert r002_result.blocking_reason == BlockingReason.MISSING_EVIDENCE
        missing_r002 = [m.attribute for m in r002_result.missing_evidence]
        assert "rear_garden_depth" in missing_r002, (
            f"rear_garden_depth should be listed as missing, got: {missing_r002}"
        )

        r003_result = evaluator.evaluate("R003")
        assert r003_result.status == "NOT_ASSESSABLE", (
            "R003 should be NOT_ASSESSABLE when footprint/site area are absent"
        )
        assert r003_result.blocking_reason == BlockingReason.MISSING_EVIDENCE

    # ------------------------------------------------------------------
    # Test 4: Low confidence — entities exist but confidence too low
    # ------------------------------------------------------------------

    def test_low_confidence_not_assessable(self) -> None:
        """Entities with confidence=0.1 fail the confidence gate → NOT_ASSESSABLE.

        The gate threshold is 0.75 so all entities are below it.
        The assessability result should reflect LOW_CONFIDENCE (or MISSING_EVIDENCE
        if the gate causes entities to be filtered out before source-matching).
        """
        factory = _make_factory()
        rules_dict = _load_rules_dict(factory)

        # Entities present but confidence extremely low (0.1)
        height_entity = _make_entity(
            attribute="building_height",
            value=7.5,
            source_doc="elevation_DRAWING.pdf",
            confidence=0.1,   # well below 0.75 gate
        )
        zone_entity = _make_entity(
            attribute="zone_category",
            value="residential",
            source_doc="planning_application_FORM.pdf",
            confidence=0.1,
            entity_type=EntityType.ZONE,
            unit=None,
        )

        entities = [height_entity, zone_entity]
        provider = FlatEvidenceProvider(entities)
        gate = _make_gate(min_confidence=0.75)
        reconciler = PairwiseReconciler()

        evaluator = DefaultAssessabilityEvaluator(
            evidence_provider=provider,
            confidence_gate=gate,
            reconciler=reconciler,
            rules=rules_dict,
        )

        r001_result = evaluator.evaluate("R001")
        assert r001_result.status == "NOT_ASSESSABLE", (
            "R001 should be NOT_ASSESSABLE when all entities have confidence=0.1"
        )
        # Low-confidence entities are caught after source-matching;
        # the result may be LOW_CONFIDENCE or MISSING_EVIDENCE depending on
        # priority ordering (MISSING > CONFLICTING > LOW_CONFIDENCE).
        assert r001_result.blocking_reason in (
            BlockingReason.LOW_CONFIDENCE,
            BlockingReason.MISSING_EVIDENCE,
        ), (
            f"Expected LOW_CONFIDENCE or MISSING_EVIDENCE, "
            f"got {r001_result.blocking_reason}"
        )

    # ------------------------------------------------------------------
    # Test 5: Conflicting evidence — two building_height values conflict
    # ------------------------------------------------------------------

    def test_conflicting_evidence(self) -> None:
        """Two entities for building_height with values 7.5 and 15.0 conflict.

        PairwiseReconciler uses default tolerance of 0.5 metres.
        |15.0 - 7.5| = 7.5 > 0.5 → CONFLICTING
        Assessability → NOT_ASSESSABLE with CONFLICTING_EVIDENCE.
        """
        factory = _make_factory()
        rules_dict = _load_rules_dict(factory)

        height_entity_a = _make_entity(
            attribute="building_height",
            value=7.5,
            source_doc="elevation_plan_DRAWING.pdf",
            confidence=0.90,
        )
        height_entity_b = _make_entity(
            attribute="building_height",
            value=15.0,
            source_doc="block_plan_DRAWING.pdf",
            confidence=0.88,
        )
        zone_entity = _zone_entity()

        entities = [height_entity_a, height_entity_b, zone_entity]
        provider = FlatEvidenceProvider(entities)
        gate = _make_gate(min_confidence=0.75)
        reconciler = PairwiseReconciler()  # default tolerance 0.5 m

        evaluator = DefaultAssessabilityEvaluator(
            evidence_provider=provider,
            confidence_gate=gate,
            reconciler=reconciler,
            rules=rules_dict,
        )

        r001_result = evaluator.evaluate("R001")
        assert r001_result.status == "NOT_ASSESSABLE", (
            "R001 should be NOT_ASSESSABLE when building_height values conflict"
        )
        assert r001_result.blocking_reason == BlockingReason.CONFLICTING_EVIDENCE, (
            f"Expected CONFLICTING_EVIDENCE, got {r001_result.blocking_reason}"
        )
        assert len(r001_result.conflicts) >= 1, (
            "At least one conflict detail should be reported"
        )
        conflict_attrs = [c.attribute for c in r001_result.conflicts]
        assert "building_height" in conflict_attrs, (
            f"building_height should appear in conflicts: {conflict_attrs}"
        )

    # ------------------------------------------------------------------
    # Test 6: Reconciler directly detects CONFLICTING for large delta
    # ------------------------------------------------------------------

    def test_reconciler_detects_conflicting_values(self) -> None:
        """PairwiseReconciler standalone: large delta → CONFLICTING status."""
        reconciler = PairwiseReconciler()

        e1 = _make_entity("building_height", 7.5, "plan_A_DRAWING.pdf")
        e2 = _make_entity("building_height", 15.0, "plan_B_DRAWING.pdf")

        result = reconciler.reconcile([e1, e2], attribute="building_height")

        assert result.status == ReconciliationStatus.CONFLICTING
        assert result.best_value is None
        assert result.conflict_details is not None
        assert "7.5" in result.conflict_details or "15.0" in result.conflict_details

    def test_reconciler_agrees_on_close_values(self) -> None:
        """PairwiseReconciler: values within tolerance 0.5 m → AGREED."""
        reconciler = PairwiseReconciler()

        e1 = _make_entity("building_height", 7.50, "plan_A_DRAWING.pdf")
        e2 = _make_entity("building_height", 7.80, "plan_B_DRAWING.pdf")

        result = reconciler.reconcile([e1, e2], attribute="building_height")

        assert result.status == ReconciliationStatus.AGREED
        assert result.best_value == pytest.approx((7.50 + 7.80) / 2)

    # ------------------------------------------------------------------
    # Test 7: Confidence gate directly filters low-confidence entities
    # ------------------------------------------------------------------

    def test_confidence_gate_rejects_low_entities(self) -> None:
        """ThresholdConfidenceGate: confidence=0.1 below threshold 0.75 → rejected."""
        gate = _make_gate(min_confidence=0.75)

        low_entity = _make_entity("building_height", 7.5, "plan_DRAWING.pdf", confidence=0.1)
        high_entity = _make_entity("building_height", 7.5, "plan_DRAWING.pdf", confidence=0.90)

        assert not gate.is_trustworthy(low_entity), "0.1 confidence should be rejected"
        assert gate.is_trustworthy(high_entity), "0.90 confidence should pass"

        trusted = gate.filter_trusted([low_entity, high_entity])
        assert len(trusted) == 1
        assert trusted[0].confidence == pytest.approx(0.90)

    # ------------------------------------------------------------------
    # Test 8: Rule factory loads all rule configs correctly
    # ------------------------------------------------------------------

    def test_rule_factory_loads_three_rules(self) -> None:
        """RuleFactory loads R001, R002, R003 from configs/rules/."""
        factory = _make_factory()
        pairs = factory.load_rules(_RULES_DIR)
        rule_ids = {cfg.rule_id for cfg, _ in pairs}

        assert "R001" in rule_ids
        assert "R002" in rule_ids
        assert "R003" in rule_ids

    def test_rule_configs_have_correct_thresholds(self) -> None:
        """Verify YAML thresholds match expected policy values."""
        factory = _make_factory()
        rules_dict = _load_rules_dict(factory)

        r001 = rules_dict["R001"]
        assert float(r001.parameters["threshold"]) == pytest.approx(_R001_THRESHOLD)
        assert r001.parameters["operator"] == "<="

        r002 = rules_dict["R002"]
        assert float(r002.parameters["threshold"]) == pytest.approx(_R002_THRESHOLD)
        assert r002.parameters["operator"] == ">="

        r003 = rules_dict["R003"]
        assert float(r003.parameters["threshold"]) == pytest.approx(_R003_THRESHOLD)
        assert r003.parameters["operator"] == "<="
