"""Integration tests — end-to-end reasoning+output pipeline on synthetic data.

These tests run the full reasoning and output pipeline on pre-extracted
entities constructed from ground truth, verifying correct PASS/FAIL/
NOT_ASSESSABLE verdicts without requiring LLM calls or Neo4j.

Approach:
1. Load ground truth from data/synthetic_diverse/compliant/SET_COMPLIANT_100000/
2. Construct ExtractedEntity objects from ground truth extraction values
3. Feed into reasoning pipeline steps:
   normalisation → confidence gating → assessability → rule evaluation
   → scoring → evidence requests
4. Verify outputs match expected verdicts

Note on ReconciliationStep: that step groups entities by entity_type (e.g.
"MEASUREMENT"), not by rule ID.  RuleEvaluationStep looks up reconciled
evidence by rule_id (R001, R002, R003).  To exercise the full chain without
introducing a gap, reconciled_evidence is populated directly in the context
keyed by rule_id — which is the contract that RuleEvaluationStep consumes.
This correctly reflects how the pipeline is wired in bootstrap.py.

Note on verdict rule_id: RuleFactory.load_rules() injects rule_id into the
evaluator parameters dict, so verdicts now carry the correct rule_id.
Assessability results also carry the correct rule_id since they are produced
by DefaultAssessabilityEvaluator which receives rule_id explicitly.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from planproof.output.evidence_request import MinEvidenceRequestGenerator
from planproof.output.markdown_renderer import MarkdownReportRenderer
from planproof.pipeline.steps.confidence_gating import ConfidenceGatingStep
from planproof.pipeline.steps.evidence_request import EvidenceRequestStep
from planproof.pipeline.steps.normalisation import NormalisationStep
from planproof.pipeline.steps.rule_evaluation import RuleEvaluationStep
from planproof.pipeline.steps.scoring import ScoringStep
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
from planproof.schemas.assessability import AssessabilityResult, BlockingReason
from planproof.schemas.entities import EntityType, ExtractedEntity, ExtractionMethod
from planproof.schemas.reconciliation import ReconciledEvidence, ReconciliationStatus
from planproof.schemas.rules import RuleConfig

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parent.parent.parent
_RULES_DIR = _REPO_ROOT / "configs" / "rules"
_CONFIDENCE_THRESHOLDS_PATH = _REPO_ROOT / "configs" / "confidence_thresholds.yaml"
_GT_PATH = (
    _REPO_ROOT
    / "data"
    / "synthetic_diverse"
    / "compliant"
    / "SET_COMPLIANT_100000"
    / "ground_truth.json"
)

_RULES_EXIST = (
    (_RULES_DIR / "r001_max_height.yaml").exists()
    and (_RULES_DIR / "r002_rear_garden.yaml").exists()
    and (_RULES_DIR / "r003_site_coverage.yaml").exists()
)
_GT_EXISTS = _GT_PATH.exists()
_CONFIGS_EXIST = _CONFIDENCE_THRESHOLDS_PATH.exists() and _RULES_EXIST

_TS = datetime(2025, 1, 1, 9, 0, 0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entity(
    value: Any,
    source_doc: str,
    unit: str | None = "metres",
    confidence: float = 0.92,
    entity_type: EntityType = EntityType.MEASUREMENT,
    method: ExtractionMethod = ExtractionMethod.VLM_ZEROSHOT,
) -> ExtractedEntity:
    """Create an ExtractedEntity with realistic defaults for E2E testing."""
    return ExtractedEntity(
        entity_type=entity_type,
        value=value,
        unit=unit,
        confidence=confidence,
        source_document=source_doc,
        extraction_method=method,
        timestamp=_TS,
    )


def _make_factory() -> RuleFactory:
    """Return a RuleFactory with all known evaluators registered."""
    factory = RuleFactory()
    RuleFactory.register_evaluator("numeric_threshold", NumericThresholdEvaluator)
    RuleFactory.register_evaluator("ratio_threshold", RatioThresholdEvaluator)
    RuleFactory.register_evaluator("enum_check", EnumCheckEvaluator)
    RuleFactory.register_evaluator("fuzzy_string_match", FuzzyMatchEvaluator)
    RuleFactory.register_evaluator("numeric_tolerance", NumericToleranceEvaluator)
    RuleFactory.register_evaluator("attribute_diff", AttributeDiffEvaluator)
    return factory


def _load_rules_dict(factory: RuleFactory) -> dict[str, RuleConfig]:
    """Load YAML rules and return a dict keyed by rule_id."""
    pairs = factory.load_rules(_RULES_DIR)
    return {cfg.rule_id: cfg for cfg, _ in pairs}


def _make_reconciled(
    rule_id: str,
    best_value: Any,
    sources: list[ExtractedEntity],
    status: ReconciliationStatus = ReconciliationStatus.SINGLE_SOURCE,
) -> ReconciledEvidence:
    """Build a ReconciledEvidence keyed for a rule_id."""
    return ReconciledEvidence(
        attribute=rule_id,
        status=status,
        best_value=best_value,
        sources=sources,
        conflict_details=None,
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


def _make_gate_from_yaml() -> ThresholdConfidenceGate:
    """Load ThresholdConfidenceGate from the project confidence_thresholds.yaml."""
    return ThresholdConfidenceGate.from_yaml(_CONFIDENCE_THRESHOLDS_PATH)


def _zone_entity(source_doc: str = "planning_application_FORM.pdf") -> ExtractedEntity:
    """Return a high-confidence zone_category entity from a FORM source."""
    return _make_entity(
        value="residential",
        source_doc=source_doc,
        unit=None,
        confidence=0.97,
        entity_type=EntityType.ZONE,
        method=ExtractionMethod.OCR_LLM,
    )


def _base_context(
    entities: list[ExtractedEntity],
    rule_ids: list[str],
    application_id: str = "E2E-TEST-001",
) -> dict:
    """Build a minimal PipelineContext with entities and metadata."""
    return {
        "entities": list(entities),
        "metadata": {
            "application_id": application_id,
            "rule_ids": rule_ids,
        },
    }


# ---------------------------------------------------------------------------
# Ground truth loader
# ---------------------------------------------------------------------------


def _load_ground_truth() -> dict:
    with open(_GT_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _entities_from_ground_truth(gt: dict) -> dict[str, float]:
    """Extract {attribute: value} from GT 'values' list."""
    return {item["attribute"]: item["value"] for item in gt["values"]}


# ---------------------------------------------------------------------------
# Shared assessability helper
# ---------------------------------------------------------------------------


def _build_assessability(
    rule_id: str,
    entities: list[ExtractedEntity],
    gate: ThresholdConfidenceGate,
    reconciler: PairwiseReconciler,
    rules_dict: dict[str, RuleConfig],
) -> AssessabilityResult:
    """Evaluate assessability for a single rule using a dedicated evidence provider."""
    provider = FlatEvidenceProvider(entities)
    ae = DefaultAssessabilityEvaluator(
        evidence_provider=provider,
        confidence_gate=gate,
        reconciler=reconciler,
        rules=rules_dict,
    )
    return ae.evaluate(rule_id)


# ---------------------------------------------------------------------------
# Test class — requires synthetic data and config files
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not (_GT_EXISTS and _CONFIGS_EXIST),
    reason=(
        "Synthetic ground truth or config files not found; "
        "run datagen to generate data/synthetic_diverse/compliant/SET_COMPLIANT_100000/"
    ),
)
class TestE2EPipeline:
    """End-to-end pipeline integration tests using synthetic ground truth data.

    Each test constructs a PipelineContext from ExtractedEntity objects and
    runs through the reasoning+output pipeline steps, verifying final verdicts
    match expectations without any LLM or database calls.
    """

    # ------------------------------------------------------------------
    # Test 1: compliant set → all rules ASSESSABLE + PASS
    # ------------------------------------------------------------------

    def test_compliant_set_produces_pass_verdicts(self) -> None:
        """Ground truth compliant values run through pipeline → all PASS.

        Loads building_height, rear_garden_depth, site_coverage from
        SET_COMPLIANT_100000 ground truth.  All values are within their
        respective policy thresholds so R001, R002, and R003 must PASS.

        R003 uses a ratio (coverage %), so its reconciled evidence is
        populated directly as a pre-computed ratio value (0–1 scale).

        The assessability results for all three rules are set to ASSESSABLE
        so RuleEvaluationStep does not skip any rule.  Verdicts are verified
        by outcome count and evaluated_value rather than rule_id (see module
        docstring for rationale).
        """
        gt = _load_ground_truth()
        values = _entities_from_ground_truth(gt)

        factory = _make_factory()
        gate = _make_gate_from_yaml()
        reconciler = PairwiseReconciler()
        rules_dict = _load_rules_dict(factory)

        # --- Build entities from GT ---
        height_entity = _make_entity(
            value=values["building_height"],
            source_doc="SET_COMPLIANT_100000-elevation_DRAWING.png",
            unit="metres",
            confidence=0.92,
        )
        garden_entity = _make_entity(
            value=values["rear_garden_depth"],
            source_doc="SET_COMPLIANT_100000-site_plan_DRAWING.pdf",
            unit="metres",
            confidence=0.91,
        )
        # site_coverage in GT is a percent (e.g. 37.65); R003 expects a ratio [0,1]
        coverage_ratio = values["site_coverage"] / 100.0
        coverage_entity = _make_entity(
            value=coverage_ratio,
            source_doc="SET_COMPLIANT_100000-site_plan_DRAWING.pdf",
            unit=None,
            confidence=0.88,
        )
        zone_entity = _zone_entity()

        entities = [height_entity, garden_entity, coverage_entity, zone_entity]

        # --- Step 1: Normalisation ---
        context = _base_context(entities, rule_ids=["R001", "R002", "R003"])
        norm_result = NormalisationStep().execute(context)
        assert norm_result["success"] is True

        # --- Step 2: Confidence gating ---
        gate_result = ConfidenceGatingStep(gate=gate).execute(context)
        assert gate_result["success"] is True
        assert len(context["entities"]) > 0, "All GT entities should pass confidence gate"

        # --- Step 3: Assessability — each rule with its own scoped provider ---
        # Using _make_assessable() directly is equivalent here because entity
        # confidence is well above thresholds and sources match.  We still call
        # DefaultAssessabilityEvaluator for R001/R002 to prove it detects evidence.
        r001_assess = _build_assessability(
            "R001", [height_entity, zone_entity], gate, reconciler, rules_dict
        )
        assert r001_assess.status in ("ASSESSABLE", "PARTIALLY_ASSESSABLE"), (
            f"R001 should be ASSESSABLE/PARTIALLY_ASSESSABLE; "
            f"blocking={r001_assess.blocking_reason}, "
            f"missing={[m.attribute for m in r001_assess.missing_evidence]}"
        )

        r002_assess = _build_assessability(
            "R002", [garden_entity, zone_entity], gate, reconciler, rules_dict
        )
        assert r002_assess.status in ("ASSESSABLE", "PARTIALLY_ASSESSABLE"), (
            f"R002 should be ASSESSABLE/PARTIALLY_ASSESSABLE; "
            f"blocking={r002_assess.blocking_reason}, "
            f"missing={[m.attribute for m in r002_assess.missing_evidence]}"
        )

        # R003 needs footprint+site_area; we bypass assessability by using
        # _make_assessable() and providing the pre-computed ratio in reconciled_evidence.
        r003_assess = _make_assessable("R003")

        # --- Step 4: Rule evaluation via RuleEvaluationStep ---
        # reconciled_evidence keyed by attribute name (matching rule parameters)
        context["reconciled_evidence"] = {
            "building_height": _make_reconciled("building_height", values["building_height"], [height_entity]),
            "rear_garden_depth": _make_reconciled("rear_garden_depth", values["rear_garden_depth"], [garden_entity]),
            "R003": _make_reconciled("R003", coverage_ratio, [coverage_entity]),
        }
        context["assessability_results"] = [r001_assess, r002_assess, r003_assess]

        rule_result = RuleEvaluationStep(
            rule_factory=factory, rules_dir=_RULES_DIR
        ).execute(context)
        assert rule_result["success"] is True

        verdicts = context["verdicts"]

        # All three R-rules must produce PASS verdicts (C-rules are skipped)
        pass_verdicts = [v for v in verdicts if v.outcome == "PASS"]
        fail_verdicts = [v for v in verdicts if v.outcome == "FAIL"]
        assert len(fail_verdicts) == 0, (
            f"No FAIL verdicts expected for compliant GT set; "
            f"got FAIL values: {[v.evaluated_value for v in fail_verdicts]}"
        )
        assert len(pass_verdicts) >= 3, (
            f"Expected at least 3 PASS verdicts (R001, R002, R003); "
            f"got {len(pass_verdicts)} PASS"
        )

        # Verify evaluated values match GT
        evaluated_values = {v.evaluated_value for v in pass_verdicts}
        assert values["building_height"] in evaluated_values, (
            f"building_height={values['building_height']} not found in verdicts: "
            f"{evaluated_values}"
        )
        assert values["rear_garden_depth"] in evaluated_values, (
            f"rear_garden_depth={values['rear_garden_depth']} not found in verdicts: "
            f"{evaluated_values}"
        )
        assert any(
            abs(v - coverage_ratio) < 1e-6 for v in evaluated_values
        ), (
            f"coverage_ratio={coverage_ratio:.4f} not found in verdicts: {evaluated_values}"
        )

        # --- Step 5: Scoring ---
        score_result = ScoringStep().execute(context)
        assert score_result["success"] is True
        report = context["metadata"]["compliance_report"]
        assert report.summary.passed >= 3
        assert report.summary.failed == 0

    # ------------------------------------------------------------------
    # Test 2: non-compliant values → at least one FAIL
    # ------------------------------------------------------------------

    def test_noncompliant_values_produce_fail(self) -> None:
        """building_height=9.5 exceeds R001 threshold of 8.0 → FAIL verdict.

        Uses VLM_ZEROSHOT extraction method with confidence above the 0.70
        threshold from configs/confidence_thresholds.yaml.
        """
        factory = _make_factory()
        gate = _make_gate_from_yaml()
        reconciler = PairwiseReconciler()
        rules_dict = _load_rules_dict(factory)

        # Exceeds R001 threshold (8.0 m)
        height_entity = _make_entity(
            value=9.5,
            source_doc="elevation_DRAWING.pdf",
            unit="metres",
            confidence=0.85,
            method=ExtractionMethod.VLM_ZEROSHOT,
        )
        zone_entity = _zone_entity()

        entities = [height_entity, zone_entity]

        # Normalisation
        context = _base_context(entities, rule_ids=["R001"])
        NormalisationStep().execute(context)

        # Confidence gating
        gate_result = ConfidenceGatingStep(gate=gate).execute(context)
        assert gate_result["success"] is True
        assert len(context["entities"]) > 0

        # Assessability
        r001_assess = _build_assessability(
            "R001", [height_entity, zone_entity], gate, reconciler, rules_dict
        )
        assert r001_assess.status in ("ASSESSABLE", "PARTIALLY_ASSESSABLE"), (
            f"R001 should be ASSESSABLE/PARTIALLY_ASSESSABLE: {r001_assess.blocking_reason}"
        )

        # Rule evaluation — keyed by attribute name matching rule parameters
        context["reconciled_evidence"] = {
            "building_height": _make_reconciled("building_height", 9.5, [height_entity]),
        }
        context["assessability_results"] = [r001_assess]

        rule_result = RuleEvaluationStep(
            rule_factory=factory, rules_dir=_RULES_DIR
        ).execute(context)
        assert rule_result["success"] is True

        verdicts = context["verdicts"]
        assert len(verdicts) >= 1, "At least one verdict should be produced"

        fail_verdicts = [v for v in verdicts if v.outcome == "FAIL"]
        assert len(fail_verdicts) >= 1, (
            f"At least one FAIL verdict expected for height=9.5; "
            f"got outcomes: {[v.outcome for v in verdicts]}"
        )

        # The failing verdict should have evaluated_value=9.5 and threshold=8.0
        r001_fail = next(
            (v for v in fail_verdicts if v.evaluated_value == pytest.approx(9.5)), None
        )
        assert r001_fail is not None, (
            f"FAIL verdict with evaluated_value=9.5 not found; "
            f"fail verdicts: {[(v.evaluated_value, v.threshold) for v in fail_verdicts]}"
        )
        assert r001_fail.threshold == pytest.approx(8.0)

    # ------------------------------------------------------------------
    # Test 3: missing entities → some rules NOT_ASSESSABLE
    # ------------------------------------------------------------------

    def test_missing_entities_produce_not_assessable(self) -> None:
        """Only building_height provided → R002 and R003 are NOT_ASSESSABLE.

        FlatEvidenceProvider returns ALL entities for every rule; the source
        filter inside DefaultAssessabilityEvaluator checks whether an
        acceptable_source string appears in source_document.

        To prevent the height entity from satisfying R002's rear_garden_depth
        source requirement (also DRAWING/REPORT), its source_document must not
        contain "DRAWING" or "REPORT".  Using "elevation_CERTIFICATE.pdf" ensures
        the entity is invisible to DRAWING/REPORT source filters.

        Consequence: R001 (building_height also requires DRAWING/REPORT) is also
        NOT_ASSESSABLE in this scenario.  This is intentional and correct for the
        flat evidence model — it cannot distinguish measurement types by attribute
        name, only by source type.  The test verifies at least two rules are
        NOT_ASSESSABLE (R002 and R003), and that rear_garden_depth is explicitly
        listed in R002's missing evidence.  R001 assessability with proper evidence
        is covered in test_compliant_set_produces_pass_verdicts.
        """
        factory = _make_factory()
        gate = _make_gate_from_yaml()
        reconciler = PairwiseReconciler()
        rules_dict = _load_rules_dict(factory)

        # Source document must NOT contain "DRAWING" or "REPORT" so that it
        # does not accidentally satisfy R001/R002 acceptable_sources filters.
        # This is the same approach used in test_reasoning_pipeline.py test 3.
        height_entity = _make_entity(
            value=3.47,
            source_doc="elevation_CERTIFICATE.pdf",
            unit="metres",
            confidence=0.92,
            method=ExtractionMethod.VLM_ZEROSHOT,
        )
        # Zone from EXTERNAL_DATA — satisfies FORM/EXTERNAL_DATA acceptable sources
        zone_entity = _zone_entity(source_doc="council_zones_EXTERNAL_DATA.json")

        entities = [height_entity, zone_entity]

        # Normalisation + gating
        context = _base_context(entities, rule_ids=["R001", "R002", "R003"])
        NormalisationStep().execute(context)
        ConfidenceGatingStep(gate=gate).execute(context)

        r001_assess = _build_assessability("R001", entities, gate, reconciler, rules_dict)
        r002_assess = _build_assessability("R002", entities, gate, reconciler, rules_dict)
        r003_assess = _build_assessability("R003", entities, gate, reconciler, rules_dict)

        # R002: rear_garden_depth has no entity from DRAWING/REPORT → NOT_ASSESSABLE
        assert r002_assess.status == "NOT_ASSESSABLE", (
            "R002 should be NOT_ASSESSABLE when rear_garden_depth is absent"
        )
        assert r002_assess.blocking_reason == BlockingReason.MISSING_EVIDENCE
        missing_r002 = [m.attribute for m in r002_assess.missing_evidence]
        assert "rear_garden_depth" in missing_r002, (
            f"rear_garden_depth should be listed as missing; got {missing_r002}"
        )

        # R003: building_footprint_area missing → NOT_ASSESSABLE
        assert r003_assess.status == "NOT_ASSESSABLE", (
            "R003 should be NOT_ASSESSABLE when site area entities are absent"
        )
        assert r003_assess.blocking_reason == BlockingReason.MISSING_EVIDENCE

        # At least two of the three R-rules are NOT_ASSESSABLE
        all_assessments = [r001_assess, r002_assess, r003_assess]
        not_assessable_count = sum(
            1 for r in all_assessments if r.status == "NOT_ASSESSABLE"
        )
        assert not_assessable_count >= 2, (
            f"R002 and R003 must be NOT_ASSESSABLE; "
            f"got {not_assessable_count} not-assessable out of 3"
        )

        # Run ScoringStep to confirm counts propagate to report
        context["assessability_results"] = all_assessments
        context["reconciled_evidence"] = {}
        RuleEvaluationStep(rule_factory=factory, rules_dir=_RULES_DIR).execute(context)
        ScoringStep().execute(context)

        report = context["metadata"]["compliance_report"]
        assert report.summary.not_assessable >= 2

    # ------------------------------------------------------------------
    # Test 4: markdown report rendered with summary table + verdict sections
    # ------------------------------------------------------------------

    def test_markdown_report_generated(self) -> None:
        """After pipeline completes, MarkdownReportRenderer produces expected sections.

        Builds a complete pipeline run from GT entities → verdicts → report,
        then renders to Markdown and checks for required structural markers.

        R003 is intentionally left NOT_ASSESSABLE (no site area entities) to
        verify the NOT_ASSESSABLE section appears in the rendered output.
        """
        gt = _load_ground_truth()
        values = _entities_from_ground_truth(gt)

        factory = _make_factory()
        gate = _make_gate_from_yaml()
        reconciler = PairwiseReconciler()
        rules_dict = _load_rules_dict(factory)

        # Entities from GT — no coverage entity so R003 stays NOT_ASSESSABLE
        height_entity = _make_entity(
            value=values["building_height"],
            source_doc="elevation_DRAWING.png",
            unit="metres",
            confidence=0.93,
        )
        garden_entity = _make_entity(
            value=values["rear_garden_depth"],
            source_doc="site_plan_DRAWING.pdf",
            unit="metres",
            confidence=0.91,
        )
        zone_entity = _zone_entity()

        entities = [height_entity, garden_entity, zone_entity]

        # Pipeline: normalisation → gating
        context = _base_context(
            entities, rule_ids=["R001", "R002", "R003"], application_id="GT-SET-100000"
        )
        NormalisationStep().execute(context)
        ConfidenceGatingStep(gate=gate).execute(context)

        # Assessability
        r001_assess = _build_assessability(
            "R001", [height_entity, zone_entity], gate, reconciler, rules_dict
        )
        r002_assess = _build_assessability(
            "R002", [garden_entity, zone_entity], gate, reconciler, rules_dict
        )
        # R003: zone entity is from FORM (matches total_site_area acceptable source),
        # but building_footprint_area has no entity → MISSING_EVIDENCE
        r003_assess = _build_assessability(
            "R003", [zone_entity], gate, reconciler, rules_dict
        )

        assert r001_assess.status in ("ASSESSABLE", "PARTIALLY_ASSESSABLE")
        assert r002_assess.status in ("ASSESSABLE", "PARTIALLY_ASSESSABLE")
        assert r003_assess.status == "NOT_ASSESSABLE"

        context["assessability_results"] = [r001_assess, r002_assess, r003_assess]
        context["reconciled_evidence"] = {
            "building_height": _make_reconciled("building_height", values["building_height"], [height_entity]),
            "rear_garden_depth": _make_reconciled("rear_garden_depth", values["rear_garden_depth"], [garden_entity]),
        }

        RuleEvaluationStep(rule_factory=factory, rules_dir=_RULES_DIR).execute(context)
        ScoringStep().execute(context)

        # Evidence request step
        guidance = {
            "rear_garden_depth": "Provide a dimensioned site plan showing rear garden depth.",
            "building_footprint_area": "Provide a floor plan with building footprint dimensions.",
            "total_site_area": "Provide site plan with total site area annotated.",
            "zone_category": "Confirm zoning classification on application form.",
        }
        ev_step = EvidenceRequestStep(
            generator=MinEvidenceRequestGenerator(guidance=guidance)
        )
        ev_step.execute(context)

        report = context["metadata"]["compliance_report"]
        evidence_requests = context["metadata"].get("evidence_requests", [])

        # --- Render Markdown ---
        renderer = MarkdownReportRenderer()
        md = renderer.render(report, evidence_requests)

        assert isinstance(md, str), "Renderer must return a string"
        assert len(md) > 0, "Rendered Markdown must be non-empty"

        # Application header
        assert "GT-SET-100000" in md, "Application ID must appear in report header"

        # Summary table
        assert "## Summary" in md, "Summary section must be present"
        assert "| Total Rules |" in md, "Summary must include a Total Rules row"
        assert "| Passed |" in md, "Summary must include a Passed row"

        # Verdict section with PASS outcomes
        assert "## Rule Verdicts" in md, "Verdict section must be present"
        assert "PASS" in md, "At least one PASS verdict must appear"

        # GT evaluated values appear in the rendered verdicts
        assert str(values["building_height"]) in md, (
            f"building_height value {values['building_height']} should appear in report"
        )
        assert str(values["rear_garden_depth"]) in md, (
            f"rear_garden_depth value {values['rear_garden_depth']} should appear in report"
        )

        # NOT_ASSESSABLE section (R003 has no site area evidence)
        assert "NOT_ASSESSABLE" in md, "NOT_ASSESSABLE section must appear for R003"
        assert "R003" in md, "R003 rule_id must appear in NOT_ASSESSABLE section"

        # Evidence requests section (R003 missing evidence)
        assert "## Evidence Requests" in md, "Evidence Requests section must be present"
        assert "R003" in md, "R003 must appear in evidence requests"

        # Summary counts are consistent
        assert report.summary.total_rules >= 3
        assert report.summary.passed >= 2
        assert report.summary.not_assessable >= 1

    # ------------------------------------------------------------------
    # Test 5: YAML confidence gate filters low-confidence VLM entities
    # ------------------------------------------------------------------

    def test_confidence_gate_from_yaml_filters_low_confidence(self) -> None:
        """VLM_ZEROSHOT MEASUREMENT entities below 0.70 threshold are filtered out.

        confidence_thresholds.yaml sets VLM_ZEROSHOT MEASUREMENT to 0.70.
        An entity with confidence=0.50 must be removed by ConfidenceGatingStep;
        an entity with confidence=0.85 must be retained.
        """
        gate = _make_gate_from_yaml()

        low_conf_entity = _make_entity(
            value=5.0,
            source_doc="elevation_DRAWING.pdf",
            unit="metres",
            confidence=0.50,  # below VLM_ZEROSHOT MEASUREMENT threshold (0.70)
            method=ExtractionMethod.VLM_ZEROSHOT,
        )
        high_conf_entity = _make_entity(
            value=5.0,
            source_doc="elevation_DRAWING.pdf",
            unit="metres",
            confidence=0.85,  # above threshold
            method=ExtractionMethod.VLM_ZEROSHOT,
        )

        context = _base_context([low_conf_entity, high_conf_entity], rule_ids=[])
        result = ConfidenceGatingStep(gate=gate).execute(context)

        assert result["success"] is True
        retained = context["entities"]
        assert len(retained) == 1, (
            f"Only high-confidence entity should be retained; got {len(retained)}"
        )
        assert retained[0].confidence == pytest.approx(0.85)

    # ------------------------------------------------------------------
    # Test 6: ground truth values reproduce GT rule verdicts
    # ------------------------------------------------------------------

    def test_ground_truth_values_match_gt_verdicts(self) -> None:
        """GT values fed directly to evaluators reproduce the GT rule verdicts.

        Verifies consistency between the ground truth JSON rule_verdicts and
        the actual evaluator output for R001 and R002.  R003 is not directly
        verified here because it requires a pre-computed ratio not available
        as a raw GT value.
        """
        gt = _load_ground_truth()
        values = _entities_from_ground_truth(gt)
        gt_verdicts = {v["rule_id"]: v for v in gt["rule_verdicts"]}

        factory = _make_factory()
        rules_dict = _load_rules_dict(factory)

        # R001 — building_height
        height_entity = _make_entity(
            value=values["building_height"],
            source_doc="elevation_DRAWING.png",
            unit="metres",
            confidence=0.92,
        )
        r001_config = rules_dict["R001"]
        r001_evaluator = factory.create_evaluator(r001_config)
        r001_reconciled = _make_reconciled("R001", values["building_height"], [height_entity])
        r001_verdict = r001_evaluator.evaluate(r001_reconciled, r001_config.parameters)

        expected_r001 = gt_verdicts["R001"]["outcome"]
        assert r001_verdict.outcome == expected_r001, (
            f"R001 evaluator outcome {r001_verdict.outcome!r} does not match "
            f"GT verdict {expected_r001!r} for height={values['building_height']}"
        )
        assert r001_verdict.evaluated_value == pytest.approx(values["building_height"])
        assert r001_verdict.threshold == pytest.approx(gt_verdicts["R001"]["threshold"])

        # R002 — rear_garden_depth
        garden_entity = _make_entity(
            value=values["rear_garden_depth"],
            source_doc="site_plan_DRAWING.pdf",
            unit="metres",
            confidence=0.91,
        )
        r002_config = rules_dict["R002"]
        r002_evaluator = factory.create_evaluator(r002_config)
        r002_reconciled = _make_reconciled("R002", values["rear_garden_depth"], [garden_entity])
        r002_verdict = r002_evaluator.evaluate(r002_reconciled, r002_config.parameters)

        expected_r002 = gt_verdicts["R002"]["outcome"]
        assert r002_verdict.outcome == expected_r002, (
            f"R002 evaluator outcome {r002_verdict.outcome!r} does not match "
            f"GT verdict {expected_r002!r} for depth={values['rear_garden_depth']}"
        )
        assert r002_verdict.evaluated_value == pytest.approx(values["rear_garden_depth"])
        # Note: gt_verdicts["R002"]["threshold"] is the scenario's constraint
        # (30.0 m in this GT set), not the rule YAML threshold (10.0 m from
        # r002_rear_garden.yaml policy DM32).  The evaluator uses the rule config
        # threshold, so we verify against the known policy value.
        assert r002_verdict.threshold == pytest.approx(10.0)
