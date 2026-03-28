"""DefaultAssessabilityEvaluator — core research contribution of PlanProof.

Determines whether a compliance rule *can* be evaluated given the available
evidence, before attempting evaluation.  This prevents the system from
issuing false FAIL verdicts when evidence is simply missing, unreliable,
or conflicting across sources.

The tri-state logic (ASSESSABLE / NOT_ASSESSABLE) is the key differentiator
from traditional binary pass/fail compliance checkers.
"""
from __future__ import annotations

from planproof.infrastructure.logging import get_logger
from planproof.interfaces.graph import EvidenceProvider
from planproof.interfaces.reasoning import ConfidenceGate, Reconciler
from planproof.schemas.assessability import (
    AssessabilityResult,
    BlockingReason,
    ConflictDetail,
    EvidenceRequirement,
)
from planproof.schemas.entities import ExtractedEntity
from planproof.schemas.reconciliation import ReconciliationStatus
from planproof.schemas.rules import RuleConfig

_log = get_logger(__name__)


class DefaultAssessabilityEvaluator:
    """Evaluate whether a rule can be assessed given current evidence.

    Implements the ``AssessabilityEvaluator`` Protocol from
    ``planproof.interfaces.reasoning``.

    Parameters
    ----------
    evidence_provider:
        Queries available evidence for a rule.
    confidence_gate:
        Checks whether an entity's extraction confidence is trustworthy.
    reconciler:
        Checks for conflicts between multiple sources for one attribute.
    rules:
        Pre-loaded rule configurations keyed by rule_id.
    """

    def __init__(
        self,
        evidence_provider: EvidenceProvider,
        confidence_gate: ConfidenceGate,
        reconciler: Reconciler,
        rules: dict[str, RuleConfig],
    ) -> None:
        self._evidence_provider = evidence_provider
        self._confidence_gate = confidence_gate
        self._reconciler = reconciler
        self._rules = rules

    # ------------------------------------------------------------------
    # Public API — satisfies AssessabilityEvaluator Protocol
    # ------------------------------------------------------------------

    def evaluate(self, rule_id: str) -> AssessabilityResult:
        """Determine whether *rule_id* can be assessed.

        Returns an ``AssessabilityResult`` with status ASSESSABLE or
        NOT_ASSESSABLE, plus details about what is missing or conflicting.
        """
        rule = self._rules.get(rule_id)
        if rule is None:
            _log.warning("assessability.rule_not_found", rule_id=rule_id)
            return AssessabilityResult(
                rule_id=rule_id,
                status="NOT_ASSESSABLE",
                blocking_reason=BlockingReason.MISSING_EVIDENCE,
                missing_evidence=[],
                conflicts=[],
            )

        # Vacuously true: no evidence required
        if not rule.required_evidence:
            _log.debug("assessability.vacuously_assessable", rule_id=rule_id)
            return AssessabilityResult(
                rule_id=rule_id,
                status="ASSESSABLE",
                blocking_reason=BlockingReason.NONE,
                missing_evidence=[],
                conflicts=[],
            )

        all_evidence = self._evidence_provider.get_evidence_for_rule(rule_id)
        _log.debug(
            "assessability.evidence_retrieved",
            rule_id=rule_id,
            n_entities=len(all_evidence),
        )

        missing: list[EvidenceRequirement] = []
        low_confidence_requirements: list[EvidenceRequirement] = []
        conflicts: list[ConflictDetail] = []
        # Entities that passed source-matching and confidence gating, per requirement
        met_entities: dict[str, list[ExtractedEntity]] = {}

        # ----- Step 1: Check each requirement -----
        for req in rule.required_evidence:
            # (a) Filter by acceptable sources — pragmatic filename match
            source_matched = self._filter_by_source(all_evidence, req)

            if not source_matched:
                _log.debug(
                    "assessability.requirement_missing",
                    rule_id=rule_id,
                    attribute=req.attribute,
                    reason="no_source_match",
                )
                missing.append(req)
                continue

            # (b) Confidence gating
            trusted = [
                e for e in source_matched
                if self._confidence_gate.is_trustworthy(e)
            ]

            if not trusted:
                _log.debug(
                    "assessability.requirement_low_confidence",
                    rule_id=rule_id,
                    attribute=req.attribute,
                )
                low_confidence_requirements.append(req)
                continue

            # (c) Spatial grounding check (deferred — met if evidence exists)
            # Future: verify spatial coordinates match the expected region.

            # (d) Attribute-tag filtering: the ablation runner stores the
            # extraction attribute name in entity.unit using the special prefix
            # "attr:" (e.g. "attr:building_height").  When such tags are present
            # we filter to only entities whose tag matches req.attribute.
            # If tags are present but none match, treat this as missing evidence.
            # Entities with real unit strings (e.g. "metres") or unit=None are
            # left unaffected so production pipeline behaviour is preserved.
            _ATTR_TAG_PREFIX = "attr:"
            attribute_tagged = [
                e for e in trusted
                if e.unit is not None
                and e.unit.startswith(_ATTR_TAG_PREFIX)
                and e.unit[len(_ATTR_TAG_PREFIX):] == req.attribute
            ]
            has_any_tagged = any(
                e.unit is not None and e.unit.startswith(_ATTR_TAG_PREFIX)
                for e in trusted
            )
            if has_any_tagged and not attribute_tagged:
                # Attribute-tagged pool but no entity matches this requirement.
                _log.debug(
                    "assessability.requirement_missing",
                    rule_id=rule_id,
                    attribute=req.attribute,
                    reason="no_attribute_tag_match",
                )
                missing.append(req)
                continue
            met_entities[req.attribute] = attribute_tagged if attribute_tagged else trusted

        # ----- Step 2: Reconciliation for met requirements -----
        for req in rule.required_evidence:
            entities = met_entities.get(req.attribute)
            if entities is None:
                continue

            reconciled = self._reconciler.reconcile(entities, req.attribute)

            if reconciled.status == ReconciliationStatus.CONFLICTING:
                _log.info(
                    "assessability.conflict_detected",
                    rule_id=rule_id,
                    attribute=req.attribute,
                )
                values = [e.value for e in entities]
                sources = [e.source_document for e in entities]
                conflicts.append(
                    ConflictDetail(
                        attribute=req.attribute,
                        values=values,
                        sources=sources,
                    )
                )

        # ----- Step 3: Final decision (priority ordering) -----
        # Priority: MISSING > CONFLICTING > LOW_CONFIDENCE > NONE
        if missing:
            return AssessabilityResult(
                rule_id=rule_id,
                status="NOT_ASSESSABLE",
                blocking_reason=BlockingReason.MISSING_EVIDENCE,
                missing_evidence=missing,
                conflicts=[],
            )

        if conflicts:
            return AssessabilityResult(
                rule_id=rule_id,
                status="NOT_ASSESSABLE",
                blocking_reason=BlockingReason.CONFLICTING_EVIDENCE,
                missing_evidence=[],
                conflicts=conflicts,
            )

        if low_confidence_requirements:
            return AssessabilityResult(
                rule_id=rule_id,
                status="NOT_ASSESSABLE",
                blocking_reason=BlockingReason.LOW_CONFIDENCE,
                missing_evidence=[],
                conflicts=[],
            )

        # All requirements met, no conflicts, sufficient confidence
        _log.info("assessability.rule_assessable", rule_id=rule_id)
        return AssessabilityResult(
            rule_id=rule_id,
            status="ASSESSABLE",
            blocking_reason=BlockingReason.NONE,
            missing_evidence=[],
            conflicts=[],
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _filter_by_source(
        entities: list[ExtractedEntity],
        requirement: EvidenceRequirement,
    ) -> list[ExtractedEntity]:
        """Filter entities whose source_document filename matches acceptable sources.

        Pragmatic approach: check if any acceptable_source string appears in
        the entity's source_document filename (e.g. "DRAWING" in
        "site_plan_DRAWING.pdf").
        """
        matched: list[ExtractedEntity] = []
        for entity in entities:
            for source in requirement.acceptable_sources:
                if source in entity.source_document:
                    matched.append(entity)
                    break
        return matched
