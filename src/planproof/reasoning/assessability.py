"""DefaultAssessabilityEvaluator — implements the SABLE algorithm.

SABLE (Semantically-Augmented Belief Logic for Evidence) determines whether
a compliance rule *can* be evaluated given the available evidence, before
attempting evaluation.  This prevents the system from issuing false FAIL
verdicts when evidence is missing, unreliable, or conflicting across sources.

The tri-state logic (ASSESSABLE / PARTIALLY_ASSESSABLE / NOT_ASSESSABLE) is
the key differentiator from traditional binary pass/fail compliance checkers.

Algorithm reference: docs/SABLE_ALGORITHM.md
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

# SABLE Section 3.4 — concordance factors by reconciliation status.
# These multiply the Dempster-combined belief to account for cross-source
# agreement.  See docs/SABLE_ALGORITHM.md, Subroutine 5.2.
_CONCORDANCE_FACTORS: dict[ReconciliationStatus, float] = {
    ReconciliationStatus.AGREED: 1.0,
    ReconciliationStatus.SINGLE_SOURCE: 0.7,
    ReconciliationStatus.CONFLICTING: 0.3,
    ReconciliationStatus.MISSING: 0.0,
}


class DefaultAssessabilityEvaluator:
    """Evaluate whether a rule can be assessed given current evidence.

    Implements the full SABLE algorithm (docs/SABLE_ALGORITHM.md):

    1. Source filtering and semantic relevance gating
    2. Confidence gating
    3. Four-factor mass function construction (reliability, confidence,
       relevance, ignorance)
    4. Dempster combination over three focal elements {sufficient, insufficient, Theta}
    5. Concordance adjustment via reconciliation status
    6. Weakest-link aggregation across requirements
    7. Three-state decision (ASSESSABLE / PARTIALLY_ASSESSABLE / NOT_ASSESSABLE)

    Hard blocking reasons (MISSING_EVIDENCE, CONFLICTING_EVIDENCE,
    LOW_CONFIDENCE) still override the D-S/SABLE continuous metrics.

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
    semantic_similarity:
        Optional ``SemanticSimilarity`` instance for embedding-based
        attribute matching.  Created lazily with defaults if ``None``.
    relevance_threshold:
        Minimum semantic relevance for an entity to contribute to a
        requirement's mass function (SABLE tau_relevance, default 0.5).
    belief_threshold_high:
        Belief >= this value -> ASSESSABLE (SABLE theta_high, default 0.7).
    belief_threshold_low:
        Plausibility <= this value -> NOT_ASSESSABLE (SABLE theta_low, default 0.3).
    """

    def __init__(
        self,
        evidence_provider: EvidenceProvider,
        confidence_gate: ConfidenceGate,
        reconciler: Reconciler,
        rules: dict[str, RuleConfig],
        semantic_similarity: object | None = None,
        relevance_threshold: float = 0.5,
        belief_threshold_high: float = 0.7,
        belief_threshold_low: float = 0.3,
    ) -> None:
        self._evidence_provider = evidence_provider
        self._confidence_gate = confidence_gate
        self._reconciler = reconciler
        self._rules = rules
        self._relevance_threshold = relevance_threshold
        self._theta_high = belief_threshold_high
        self._theta_low = belief_threshold_low

        # Lazy-initialise SemanticSimilarity if not provided
        if semantic_similarity is not None:
            self._similarity = semantic_similarity
        else:
            try:
                from planproof.reasoning.semantic_similarity import SemanticSimilarity

                self._similarity = SemanticSimilarity()
            except Exception:  # noqa: BLE001
                self._similarity = None

    # ------------------------------------------------------------------
    # Public API — satisfies AssessabilityEvaluator Protocol
    # ------------------------------------------------------------------

    def evaluate(self, rule_id: str) -> AssessabilityResult:
        """Determine whether *rule_id* can be assessed.

        Implements the full SABLE algorithm (docs/SABLE_ALGORITHM.md,
        Section 4 pseudocode).

        Returns an ``AssessabilityResult`` with status ASSESSABLE,
        PARTIALLY_ASSESSABLE, or NOT_ASSESSABLE, plus details about what
        is missing or conflicting.
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

        # ----- SABLE Step 1: Check each requirement -----
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

        # ----- SABLE Step 2: Reconciliation for met requirements -----
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

        # ----- SABLE Steps 3-5: Evidence sufficiency scoring -----
        requirement_beliefs: list[tuple[float, float, float]] = []
        for req in rule.required_evidence:
            entities = met_entities.get(req.attribute)
            if entities:
                bel, pl, k = self._compute_requirement_belief(entities, req)
                requirement_beliefs.append((bel, pl, k))

        # SABLE Step 6: Weakest-link aggregation (Section 3.5)
        if requirement_beliefs:
            combined_belief = min(b[0] for b in requirement_beliefs)
            combined_plausibility = min(b[1] for b in requirement_beliefs)
            combined_conflict = max(b[2] for b in requirement_beliefs)
        else:
            combined_belief, combined_plausibility, combined_conflict = 0.0, 1.0, 0.0

        # ----- SABLE Step 7: Final decision (priority ordering) -----
        # IMPORTANT: Hard blocking reasons override the D-S/SABLE continuous
        # metrics.  Missing evidence still forces NOT_ASSESSABLE regardless of
        # belief score.
        # Priority: MISSING > CONFLICTING > LOW_CONFIDENCE > D-S thresholds
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

        # SABLE Step 7: Three-state decision (Section 3.6)
        # Bel(R) >= theta_high -> ASSESSABLE
        # Pl(R) <= theta_low  -> NOT_ASSESSABLE
        # Otherwise           -> PARTIALLY_ASSESSABLE
        if combined_belief >= self._theta_high:
            computed_status = "ASSESSABLE"
        elif combined_plausibility <= self._theta_low:
            computed_status = "NOT_ASSESSABLE"
        else:
            computed_status = "PARTIALLY_ASSESSABLE"

        _log.info(
            "assessability.sable_decision",
            rule_id=rule_id,
            status=computed_status,
            belief=combined_belief,
            plausibility=combined_plausibility,
            conflict_mass=combined_conflict,
        )

        return AssessabilityResult(
            rule_id=rule_id,
            status=computed_status,
            blocking_reason=BlockingReason.NONE,
            missing_evidence=[],
            conflicts=[],
            belief=combined_belief,
            plausibility=combined_plausibility,
            conflict_mass=combined_conflict,
        )

    # ------------------------------------------------------------------
    # Private helpers — SABLE mass function construction
    # ------------------------------------------------------------------

    def _get_reliability_weight(self, entity: ExtractedEntity) -> float:
        """SABLE Step 1: Map extraction method to a reliability weight.

        Formula (Section 3.2):
            rho_i = threshold[e_i.extraction_method][e_i.entity_type]

        Uses the ConfidenceGate's per-method, per-type thresholds as a proxy
        for method reliability.  Falls back to 0.8 when unconfigured.
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

    def _get_semantic_relevance(
        self,
        entity: ExtractedEntity,
        requirement: EvidenceRequirement,
    ) -> float:
        """SABLE Step 3: Compute semantic relevance between entity and requirement.

        Formula (Section 3.2):
            r_i = cosine_similarity(embed(e_i.attribute), embed(R_j.attribute))

        Returns 1.0 when:
        - No similarity model is available (backward compat)
        - Entity has no attribute set (legacy entity — no semantic filtering)
        """
        # Legacy entities without attribute bypass semantic filtering
        if entity.attribute is None:
            return 1.0

        if self._similarity is None:
            return 1.0

        sim_fn = getattr(self._similarity, "similarity", None)
        if sim_fn is None:
            return 1.0

        return float(sim_fn(entity.attribute, requirement.attribute))

    @staticmethod
    def _dempster_combine(
        m1: dict[str, float],
        m2: dict[str, float],
    ) -> tuple[dict[str, float], float]:
        """Dempster's rule of combination for three-valued mass functions.

        Implements SABLE Subroutine 5.1 (docs/SABLE_ALGORITHM.md).

        Frame of discernment: {sufficient, insufficient}.
        Focal elements: {sufficient}, {insufficient}, Theta (full frame).

        Intersection rules (Section 5.1 table):
            sufficient  n sufficient   = sufficient
            insufficient n insufficient = insufficient
            Theta       n anything     = that thing
            sufficient  n insufficient = empty set (conflict)

        Parameters
        ----------
        m1, m2:
            Mass functions with keys "sufficient", "insufficient", "theta".

        Returns
        -------
        tuple:
            (combined_mass, conflict_K)
        """
        # Intersection lookup — None means empty set (conflict)
        _INTERSECTIONS: dict[tuple[str, str], str | None] = {
            ("sufficient", "sufficient"): "sufficient",
            ("insufficient", "insufficient"): "insufficient",
            ("theta", "theta"): "theta",
            ("sufficient", "theta"): "sufficient",
            ("theta", "sufficient"): "sufficient",
            ("insufficient", "theta"): "insufficient",
            ("theta", "insufficient"): "insufficient",
            ("sufficient", "insufficient"): None,
            ("insufficient", "sufficient"): None,
        }

        raw: dict[str, float] = {}
        conflict_k = 0.0

        for hyp1, mass1 in m1.items():
            for hyp2, mass2 in m2.items():
                product = mass1 * mass2
                intersection = _INTERSECTIONS.get((hyp1, hyp2))
                if intersection is None:
                    # Empty set — contributes to conflict mass K
                    conflict_k += product
                else:
                    raw[intersection] = raw.get(intersection, 0.0) + product

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
        """Compute SABLE belief, plausibility, and conflict for one requirement.

        Implements SABLE Steps 3-5 (Section 3.2-3.4):

        For each entity:
            1. rho_i  = reliability weight (extraction method)
            2. c_i    = extraction confidence
            3. r_i    = semantic relevance (embedding cosine similarity)
            4. Mass function:
               m({sufficient})   = rho_i * c_i * r_i
               m({insufficient}) = (1-rho_i) * (1-c_i) * (1-r_i)
               m(Theta)          = 1 - m({sufficient}) - m({insufficient})

        Mass functions are combined via Dempster's rule, then adjusted
        by the concordance factor gamma_j.

        Returns (belief, plausibility, accumulated_conflict).
        """
        if not entities:
            return (0.0, 1.0, 0.0)

        # SABLE Step 3-4: Build per-entity mass functions with semantic relevance
        mass_functions: list[dict[str, float]] = []
        for entity in entities:
            # SABLE Step 1: Source reliability
            reliability = self._get_reliability_weight(entity)

            # SABLE Step 2: Extraction confidence
            confidence = entity.confidence

            # SABLE Step 3: Semantic relevance
            relevance = self._get_semantic_relevance(entity, requirement)

            # Skip entities below the relevance threshold (Section 3.2, Step 3)
            if relevance < self._relevance_threshold:
                continue

            # SABLE Step 4: Three-valued mass function construction (Section 3.2)
            m_suf = reliability * confidence * relevance
            m_ins = (1.0 - reliability) * (1.0 - confidence) * (1.0 - relevance)
            m_theta = 1.0 - m_suf - m_ins

            # Clamp for numerical safety
            m_theta = max(0.0, m_theta)

            mass_functions.append({
                "sufficient": m_suf,
                "insufficient": m_ins,
                "theta": m_theta,
            })

        if not mass_functions:
            return (0.0, 1.0, 0.0)

        # SABLE Step 5: Dempster combination (Section 3.3)
        combined = mass_functions[0]
        accumulated_k = 0.0
        for m_next in mass_functions[1:]:
            combined, k = self._dempster_combine(combined, m_next)
            accumulated_k = max(accumulated_k, k)

        belief = max(0.0, min(1.0, combined.get("sufficient", 0.0)))
        plausibility = max(0.0, min(1.0, 1.0 - combined.get("insufficient", 0.0)))

        # SABLE Step 5: Concordance adjustment (Section 3.4)
        # Adjust belief by the concordance factor based on reconciliation status.
        reconciled = self._reconciler.reconcile(entities, requirement.attribute)
        gamma = _CONCORDANCE_FACTORS.get(reconciled.status, 0.5)
        belief = belief * gamma

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
