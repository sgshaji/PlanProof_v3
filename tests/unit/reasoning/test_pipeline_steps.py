"""Tests for all four reasoning pipeline steps.

Covers: ReconciliationStep, ConfidenceGatingStep, AssessabilityStep,
RuleEvaluationStep — each using mocked dependencies.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

from planproof.interfaces.pipeline import PipelineContext
from planproof.pipeline.steps.assessability import AssessabilityStep
from planproof.pipeline.steps.confidence_gating import ConfidenceGatingStep
from planproof.pipeline.steps.reconciliation import ReconciliationStep
from planproof.pipeline.steps.rule_evaluation import RuleEvaluationStep
from planproof.schemas.assessability import (
    AssessabilityResult,
    BlockingReason,
)
from planproof.schemas.entities import EntityType, ExtractedEntity, ExtractionMethod
from planproof.schemas.reconciliation import ReconciledEvidence, ReconciliationStatus
from planproof.schemas.rules import RuleConfig, RuleOutcome, RuleVerdict

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_TS = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)


def _make_entity(
    entity_type: EntityType = EntityType.MEASUREMENT,
    value: object = 7.5,
    confidence: float = 0.90,
    source: str = "doc.pdf",
) -> ExtractedEntity:
    return ExtractedEntity(
        entity_type=entity_type,
        value=value,
        confidence=confidence,
        source_document=source,
        extraction_method=ExtractionMethod.OCR_LLM,
        timestamp=_TS,
    )


def _make_reconciled(attribute: str = "MEASUREMENT") -> ReconciledEvidence:
    return ReconciledEvidence(
        attribute=attribute,
        status=ReconciliationStatus.SINGLE_SOURCE,
        best_value=7.5,
        sources=[],
    )


def _make_assessability(
    rule_id: str, status: str = "ASSESSABLE"
) -> AssessabilityResult:
    return AssessabilityResult(
        rule_id=rule_id,
        status=status,  # type: ignore[arg-type]
        blocking_reason=BlockingReason.NONE,
        missing_evidence=[],
        conflicts=[],
    )


def _make_rule_config(rule_id: str = "R001") -> RuleConfig:
    from planproof.schemas.assessability import EvidenceRequirement

    return RuleConfig(
        rule_id=rule_id,
        description="Test rule",
        policy_source="LEP 2020",
        evaluation_type="numeric_threshold",
        parameters={"threshold": 8.5},
        required_evidence=[
            EvidenceRequirement(
                attribute="height",
                acceptable_sources=["DRAWING"],
                min_confidence=0.7,
            )
        ],
    )


def _make_verdict(rule_id: str, outcome: RuleOutcome = RuleOutcome.PASS) -> RuleVerdict:
    return RuleVerdict(
        rule_id=rule_id,
        outcome=outcome,
        evidence_used=[],
        explanation="ok",
        evaluated_value=7.5,
        threshold=8.5,
    )


# ---------------------------------------------------------------------------
# ReconciliationStep
# ---------------------------------------------------------------------------


class TestReconciliationStep:
    def test_groups_entities_by_type_and_calls_reconciler(self) -> None:
        """Reconciler is called once per entity_type group."""
        reconciler = MagicMock()
        evidence_provider = MagicMock()

        measurement_entity = _make_entity(EntityType.MEASUREMENT)
        zone_entity = _make_entity(EntityType.ZONE, value="R2")

        reconciler.reconcile.side_effect = [
            _make_reconciled("MEASUREMENT"),
            _make_reconciled("ZONE"),
        ]

        step = ReconciliationStep(reconciler, evidence_provider)
        context: PipelineContext = {
            "entities": [measurement_entity, zone_entity],
        }

        result = step.execute(context)

        assert result["success"] is True
        assert reconciler.reconcile.call_count == 2

    def test_stores_reconciled_evidence_in_context(self) -> None:
        """context['reconciled_evidence'] is keyed by entity_type.value."""
        reconciler = MagicMock()
        evidence_provider = MagicMock()

        entities = [
            _make_entity(EntityType.MEASUREMENT),
            _make_entity(EntityType.MEASUREMENT, value=8.0, source="doc2.pdf"),
        ]
        reconciler.reconcile.return_value = _make_reconciled("MEASUREMENT")

        step = ReconciliationStep(reconciler, evidence_provider)
        context: PipelineContext = {"entities": entities}

        step.execute(context)

        reconciled = context["reconciled_evidence"]  # type: ignore[typeddict-item]
        assert "MEASUREMENT" in reconciled
        assert reconciled["MEASUREMENT"].attribute == "MEASUREMENT"

    def test_empty_entities_produces_no_groups(self) -> None:
        """With no entities, reconciler is not called and result is empty."""
        reconciler = MagicMock()
        evidence_provider = MagicMock()

        step = ReconciliationStep(reconciler, evidence_provider)
        context: PipelineContext = {"entities": []}

        result = step.execute(context)

        reconciler.reconcile.assert_not_called()
        assert result["success"] is True
        assert result["artifacts"]["attributes_reconciled"] == 0

    def test_step_name(self) -> None:
        step = ReconciliationStep(MagicMock(), MagicMock())
        assert step.name == "reconciliation"

    def test_hydrates_flat_evidence_provider_before_reconciling(self) -> None:
        """ReconciliationStep calls update_entities on FlatEvidenceProvider."""
        from planproof.representation.flat_evidence import FlatEvidenceProvider

        reconciler = MagicMock()
        flat_provider = FlatEvidenceProvider([])
        reconciler.reconcile.return_value = _make_reconciled("MEASUREMENT")

        entity = _make_entity(EntityType.MEASUREMENT)
        step = ReconciliationStep(reconciler, flat_provider)
        context: PipelineContext = {"entities": [entity]}
        step.execute(context)

        # After execution the flat provider should hold the pipeline entities
        assert flat_provider.get_evidence_for_rule("any") == [entity]


# ---------------------------------------------------------------------------
# ConfidenceGatingStep
# ---------------------------------------------------------------------------


class TestConfidenceGatingStep:
    def test_filters_low_confidence_entities(self) -> None:
        """filter_trusted is called and low-confidence entities are removed."""
        gate = MagicMock()

        high_conf = _make_entity(confidence=0.95)
        low_conf = _make_entity(confidence=0.30)
        gate.filter_trusted.return_value = [high_conf]

        step = ConfidenceGatingStep(gate)
        context: PipelineContext = {"entities": [high_conf, low_conf]}

        result = step.execute(context)

        assert result["success"] is True
        assert context["entities"] == [high_conf]
        assert result["artifacts"]["removed_count"] == 1
        assert result["artifacts"]["retained_count"] == 1

    def test_all_entities_retained_when_all_trusted(self) -> None:
        """When all entities pass gating, nothing is removed."""
        gate = MagicMock()
        entities = [_make_entity(confidence=0.95), _make_entity(confidence=0.88)]
        gate.filter_trusted.return_value = entities

        step = ConfidenceGatingStep(gate)
        context: PipelineContext = {"entities": entities}

        result = step.execute(context)

        assert result["artifacts"]["removed_count"] == 0
        assert len(context["entities"]) == 2

    def test_empty_entity_list_is_handled(self) -> None:
        """Empty entity list produces zero removed, zero retained."""
        gate = MagicMock()
        gate.filter_trusted.return_value = []

        step = ConfidenceGatingStep(gate)
        context: PipelineContext = {"entities": []}

        result = step.execute(context)

        assert result["success"] is True
        assert result["artifacts"]["removed_count"] == 0

    def test_step_name(self) -> None:
        step = ConfidenceGatingStep(MagicMock())
        assert step.name == "confidence_gating"


# ---------------------------------------------------------------------------
# AssessabilityStep
# ---------------------------------------------------------------------------


class TestAssessabilityStep:
    def test_evaluates_each_rule_id_from_metadata(self) -> None:
        """evaluate() is called once per rule_id from context metadata."""
        evaluator = MagicMock()
        evaluator.evaluate.side_effect = [
            _make_assessability("R001", "ASSESSABLE"),
            _make_assessability("R002", "NOT_ASSESSABLE"),
        ]

        step = AssessabilityStep(evaluator)
        context: PipelineContext = {
            "metadata": {"rule_ids": ["R001", "R002"]},
        }

        result = step.execute(context)

        assert result["success"] is True
        assert evaluator.evaluate.call_count == 2
        assert result["artifacts"]["assessable_count"] == 1
        assert result["artifacts"]["not_assessable_count"] == 1

    def test_stores_results_in_context(self) -> None:
        """context['assessability_results'] holds AssessabilityResult objects."""
        evaluator = MagicMock()
        ar = _make_assessability("R001")
        evaluator.evaluate.return_value = ar

        step = AssessabilityStep(evaluator)
        context: PipelineContext = {"metadata": {"rule_ids": ["R001"]}}

        step.execute(context)

        stored = context["assessability_results"]
        assert len(stored) == 1
        assert stored[0].rule_id == "R001"

    def test_no_rule_ids_produces_empty_results(self) -> None:
        """Missing rule_ids in metadata results in no evaluations."""
        evaluator = MagicMock()

        step = AssessabilityStep(evaluator)
        context: PipelineContext = {}

        result = step.execute(context)

        evaluator.evaluate.assert_not_called()
        assert result["success"] is True
        assert result["artifacts"]["total_rules"] == 0

    def test_step_name(self) -> None:
        step = AssessabilityStep(MagicMock())
        assert step.name == "assessability"


# ---------------------------------------------------------------------------
# RuleEvaluationStep
# ---------------------------------------------------------------------------


class TestRuleEvaluationStep:
    def _make_factory(
        self,
        rules: list[tuple[RuleConfig, MagicMock]],
    ) -> MagicMock:
        factory = MagicMock()
        factory.load_rules.return_value = rules
        return factory

    def test_only_assessable_rules_are_evaluated(self) -> None:
        """Rules marked NOT_ASSESSABLE are skipped; only ASSESSABLE ones evaluated."""
        config_a = _make_rule_config("R001")
        config_b = _make_rule_config("R002")
        evaluator_a = MagicMock()
        evaluator_b = MagicMock()
        evaluator_a.evaluate.return_value = _make_verdict("R001", RuleOutcome.PASS)

        factory = self._make_factory([(config_a, evaluator_a), (config_b, evaluator_b)])

        step = RuleEvaluationStep(factory, Path("/rules"))
        context: PipelineContext = {
            "assessability_results": [
                _make_assessability("R001", "ASSESSABLE"),
                _make_assessability("R002", "NOT_ASSESSABLE"),
            ],
            "reconciled_evidence": {},  # type: ignore[typeddict-item]
        }

        result = step.execute(context)

        evaluator_a.evaluate.assert_called_once()
        evaluator_b.evaluate.assert_not_called()
        assert result["artifacts"]["evaluated_count"] == 1
        assert result["artifacts"]["skipped_count"] == 1

    def test_stores_verdicts_in_context(self) -> None:
        """Verdicts are stored in context['verdicts']."""
        config = _make_rule_config("R001")
        evaluator = MagicMock()
        verdict = _make_verdict("R001", RuleOutcome.PASS)
        evaluator.evaluate.return_value = verdict

        factory = self._make_factory([(config, evaluator)])

        step = RuleEvaluationStep(factory, Path("/rules"))
        context: PipelineContext = {
            "assessability_results": [_make_assessability("R001", "ASSESSABLE")],
            "reconciled_evidence": {},  # type: ignore[typeddict-item]
        }

        step.execute(context)

        assert context["verdicts"] == [verdict]

    def test_all_rules_evaluated_when_no_assessability_results(self) -> None:
        """When no assessability step ran, all loaded rules are evaluated."""
        config_a = _make_rule_config("R001")
        config_b = _make_rule_config("R002")
        evaluator_a = MagicMock()
        evaluator_b = MagicMock()
        evaluator_a.evaluate.return_value = _make_verdict("R001")
        evaluator_b.evaluate.return_value = _make_verdict("R002")

        factory = self._make_factory([(config_a, evaluator_a), (config_b, evaluator_b)])

        step = RuleEvaluationStep(factory, Path("/rules"))
        context: PipelineContext = {}

        result = step.execute(context)

        evaluator_a.evaluate.assert_called_once()
        evaluator_b.evaluate.assert_called_once()
        assert result["artifacts"]["evaluated_count"] == 2
        assert result["artifacts"]["skipped_count"] == 0

    def test_pass_fail_counts_in_artifacts(self) -> None:
        """Artifacts correctly count pass and fail verdicts."""
        config_a = _make_rule_config("R001")
        config_b = _make_rule_config("R002")
        ev_a = MagicMock()
        ev_b = MagicMock()
        ev_a.evaluate.return_value = _make_verdict("R001", RuleOutcome.PASS)
        ev_b.evaluate.return_value = _make_verdict("R002", RuleOutcome.FAIL)

        factory = self._make_factory([(config_a, ev_a), (config_b, ev_b)])

        step = RuleEvaluationStep(factory, Path("/rules"))
        context: PipelineContext = {}

        result = step.execute(context)

        assert result["artifacts"]["pass_count"] == 1
        assert result["artifacts"]["fail_count"] == 1

    def test_step_name(self) -> None:
        step = RuleEvaluationStep(MagicMock(), Path("/rules"))
        assert step.name == "rule_evaluation"
