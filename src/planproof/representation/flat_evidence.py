"""Flat (non-graph) evidence provider for Ablation B.

# WHY: The full SNKG uses Neo4j to traverse spatial relationships and link
# entities to rules via graph edges.  In the ablation study (use_snkg=False)
# we deliberately degrade this to a simple flat list lookup so we can measure
# the contribution of the graph structure.  FlatEvidenceProvider satisfies the
# EvidenceProvider Protocol without requiring a Neo4j connection.
"""
from __future__ import annotations

from itertools import combinations

from planproof.infrastructure.logging import get_logger
from planproof.schemas.entities import ExtractedEntity

_log = get_logger(__name__)


class FlatEvidenceProvider:
    """Evidence provider backed by a flat in-memory entity list.

    Implements the ``EvidenceProvider`` Protocol.  Used when
    ``config.ablation.use_snkg = False``.

    Because there is no graph structure, ``get_evidence_for_rule`` returns
    *all* entities (no rule linkage).  ``get_conflicting_evidence`` uses a
    simple pairwise value comparison restricted to entities of the requested
    type from different source documents.
    """

    def __init__(self, entities: list[ExtractedEntity]) -> None:
        self._entities = entities
        _log.debug("FlatEvidenceProvider initialised", entity_count=len(entities))

    def get_evidence_for_rule(self, rule_id: str) -> list[ExtractedEntity]:
        """Return all stored entities.

        # WHY: Without graph traversal there is no way to determine which
        # entities are relevant to a specific rule, so we return everything
        # and let the evaluator filter by type/attribute itself.  This is the
        # intentional degradation that the ablation study measures.
        """
        _log.debug(
            "get_evidence_for_rule (flat)", rule_id=rule_id, count=len(self._entities)
        )
        return list(self._entities)

    def update_entities(self, entities: list[ExtractedEntity]) -> None:
        """Replace the internal entity list after construction.

        # WHY: Bootstrap creates FlatEvidenceProvider([]) before the pipeline
        # runs (entities not yet available).  ReconciliationStep calls this
        # once extraction is complete so downstream queries see real data.
        # update_entities is intentionally NOT on the EvidenceProvider Protocol
        # — it is an implementation detail of the flat ablation path only.
        """
        self._entities = entities
        _log.debug("FlatEvidenceProvider entities updated", entity_count=len(entities))

    def get_conflicting_evidence(
        self, attribute: str
    ) -> list[tuple[ExtractedEntity, ExtractedEntity]]:
        """Find entity pairs with the same type but conflicting values.

        Conflicts are detected when:
        - Both entities have ``entity_type`` matching *attribute* (case-insensitive).
        - Their ``value`` fields differ.
        - They come from different ``source_document`` files.

        # WHY: No spatial joins or graph edges are used — this is the flat
        # approximation.  Without Neo4j we cannot exploit location data to
        # resolve whether two measurements refer to the same physical feature,
        # so all value mismatches between documents are reported as potential
        # conflicts.
        """
        candidates = [
            e for e in self._entities
            if str(e.entity_type).upper() == attribute.upper()
        ]

        conflicts: list[tuple[ExtractedEntity, ExtractedEntity]] = []
        for e1, e2 in combinations(candidates, 2):
            if e1.source_document == e2.source_document:
                continue
            if e1.value != e2.value:
                conflicts.append((e1, e2))

        _log.debug(
            "get_conflicting_evidence (flat)",
            attribute=attribute,
            candidates=len(candidates),
            conflicts=len(conflicts),
        )
        return conflicts
