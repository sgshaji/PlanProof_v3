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
                belief=0.0,
                plausibility=1.0,
                conflict_mass=0.0,
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
                belief=0.0,
                plausibility=1.0,
                conflict_mass=0.0,
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

            met_entities[req.attribute] = trusted

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

        # ----- Step 2b: Dempster-Shafer evidence sufficiency scoring -----
        requirement_beliefs: list[tuple[float, float, float]] = []
        for req in rule.required_evidence:
            entities = met_entities.get(req.attribute)
            if entities:
                bel, pl, k = self._compute_requirement_belief(entities, req)
                requirement_beliefs.append((bel, pl, k))

        if requirement_beliefs:
            combined_belief = min(b[0] for b in requirement_beliefs)
            combined_plausibility = min(b[1] for b in requirement_beliefs)
            combined_conflict = max(b[2] for b in requirement_beliefs)
        else:
            combined_belief, combined_plausibility, combined_conflict = 0.0, 1.0, 0.0

        # ----- Step 3: Final decision (priority ordering) -----
        # Priority: MISSING > CONFLICTING > LOW_CONFIDENCE > NONE
        if missing:
            return AssessabilityResult(
                rule_id=rule_id,
                status="NOT_ASSESSABLE",
                blocking_reason=BlockingReason.MISSING_EVIDENCE,
                missing_evidence=missing,
                conflicts=[],
                belief=combined_belief,
                plausibility=combined_plausibility,
                conflict_mass=combined_conflict,
            )

        if conflicts:
            return AssessabilityResult(
                rule_id=rule_id,
                status="NOT_ASSESSABLE",
                blocking_reason=BlockingReason.CONFLICTING_EVIDENCE,
                missing_evidence=[],
                conflicts=conflicts,
                belief=combined_belief,
                plausibility=combined_plausibility,
                conflict_mass=combined_conflict,
            )

        if low_confidence_requirements:
            return AssessabilityResult(
                rule_id=rule_id,
                status="NOT_ASSESSABLE",
                blocking_reason=BlockingReason.LOW_CONFIDENCE,
                missing_evidence=[],
                conflicts=[],
                belief=combined_belief,
                plausibility=combined_plausibility,
                conflict_mass=combined_conflict,
            )

        # All requirements met, no conflicts, sufficient confidence
        _log.info("assessability.rule_assessable", rule_id=rule_id)
        return AssessabilityResult(
            rule_id=rule_id,
            status="ASSESSABLE",
            blocking_reason=BlockingReason.NONE,
            missing_evidence=[],
            conflicts=[],
            belief=combined_belief,
            plausibility=combined_plausibility,
            conflict_mass=combined_conflict,
        )

    # ------------------------------------------------------------------
    # Private helpers — Dempster-Shafer evidence theory (M8)
    # ------------------------------------------------------------------

    def _get_reliability_weight(self, entity: ExtractedEntity) -> float:
        """Map extraction method to a reliability weight via the confidence gate.

        Uses the ConfidenceGate's per-method, per-type thresholds as a proxy
        for method reliability.  The threshold represents the *minimum*
        acceptable confidence; we treat it as the reliability weight so that
        methods with stricter thresholds (i.e. higher bars) contribute more
        to the belief mass.

        Falls back to 0.8 when the gate has no threshold configured.
        """
        method_key = entity.extraction_method.value
        type_key = entity.entity_type.value

        thresholds = getattr(self._confidence_gate, "_thresholds", None)
        if thresholds is None:
            return 0.8

        method_thresholds = thresholds.get(method_key)
        if method_thresholds is None:
            return 0.8

        threshold = method_thresholds.get(type_key)
        if threshold is None:
            return 0.8

        return float(threshold)

    @staticmethod
    def _dempster_combine(
        m1: dict[str, float],
        m2: dict[str, float],
    ) -> tuple[dict[str, float], float]:
        """Dempster's rule of combination for two mass functions.

        Frame of discernment: {sufficient, insufficient}.
        Returns (combined_mass, conflict_K).
        """
        raw: dict[str, float] = {}
        conflict_k = 0.0

        for hyp1, mass1 in m1.items():
            for hyp2, mass2 in m2.items():
                product = mass1 * mass2
                if hyp1 == hyp2:
                    raw[hyp1] = raw.get(hyp1, 0.0) + product
                else:
                    conflict_k += product

        # Total conflict — return m1 unchanged
        if conflict_k >= 1.0:
            return dict(m1), 1.0

        # Normalise by (1 - K)
        normaliser = 1.0 - conflict_k
        combined = {hyp: mass / normaliser for hyp, mass in raw.items()}
        return combined, conflict_k

    def _compute_requirement_belief(
        self,
        entities: list[ExtractedEntity],
        requirement: EvidenceRequirement,
    ) -> tuple[float, float, float]:
        """Compute D-S belief, plausibility, and conflict for one requirement.

        Each entity contributes a mass function over {sufficient, insufficient},
        weighted by extraction-method reliability and entity confidence.
        Mass functions are combined left-to-right using Dempster's rule.

        Returns (belief, plausibility, accumulated_conflict).
        """
        if not entities:
            return (0.0, 1.0, 0.0)

        # Build per-entity mass functions
        mass_functions: list[dict[str, float]] = []
        for entity in entities:
            reliability = self._get_reliability_weight(entity)
            support = max(0.0, min(1.0, reliability * entity.confidence))
            mass_functions.append({
                "sufficient": support,
                "insufficient": 1.0 - support,
            })

        # Fold-left combination
        combined = mass_functions[0]
        accumulated_k = 0.0
        for m_next in mass_functions[1:]:
            combined, k = self._dempster_combine(combined, m_next)
            accumulated_k = max(accumulated_k, k)

        belief = max(0.0, min(1.0, combined.get("sufficient", 0.0)))
        plausibility = max(0.0, min(1.0, 1.0 - combined.get("insufficient", 0.0)))

        return (belief, plausibility, accumulated_k)

    # ------------------------------------------------------------------
    # Private helpers — source filtering
    # ------------------------------------------------------------------

    @staticmethod
    def _filter_by_source(
        entities: list[ExtractedEntity],
        requirement: EvidenceRequirement,
    ) -> list[ExtractedEntity]:
        """Filter entities by acceptable source and matching attribute name.

        Pragmatic approach: check if any acceptable_source string appears in
        the entity's source_document filename (e.g. "DRAWING" in
        "site_plan_DRAWING.pdf").

        When the entity carries an ``attribute`` value (non-None), it must
        also match the requirement's ``attribute`` name.  Legacy entities
        without an attribute set fall back to source-only matching for
        backward compatibility.
        """
        matched: list[ExtractedEntity] = []
        for entity in entities:
            # Source document check
            source_ok = any(
                source in entity.source_document
                for source in requirement.acceptable_sources
            )
            if not source_ok:
                continue

            # Attribute check — only enforced when entity has attribute set
            if (
                entity.attribute is not None
                and entity.attribute != requirement.attribute
            ):
                continue

            matched.append(entity)
        return matched
