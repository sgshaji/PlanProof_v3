"""Pipeline step: cross-source evidence reconciliation."""
from __future__ import annotations

from planproof.infrastructure.logging import get_logger
from planproof.interfaces.graph import EvidenceProvider
from planproof.interfaces.pipeline import PipelineContext, StepResult
from planproof.interfaces.reasoning import Reconciler
from planproof.schemas.entities import ExtractedEntity
from planproof.schemas.reconciliation import ReconciledEvidence

logger = get_logger(__name__)


class ReconciliationStep:
    """Reconcile evidence for each attribute across multiple document sources.

    Queries the knowledge graph for conflicting evidence and uses the
    ``Reconciler`` Protocol to determine which value to trust.
    """

    def __init__(
        self,
        reconciler: Reconciler,
        evidence_provider: EvidenceProvider,
    ) -> None:
        self._reconciler = reconciler
        self._evidence_provider = evidence_provider

    @property
    def name(self) -> str:
        return "reconciliation"

    def execute(self, context: PipelineContext) -> StepResult:
        entities = context.get("entities", [])

        # Group entities by entity_type
        groups: dict[str, list[ExtractedEntity]] = {}
        for entity in entities:
            key = entity.entity_type.value
            groups.setdefault(key, []).append(entity)

        reconciled: dict[str, ReconciledEvidence] = {}
        for attribute_name, group_entities in groups.items():
            reconciled[attribute_name] = self._reconciler.reconcile(
                group_entities, attribute_name
            )

        context["reconciled_evidence"] = reconciled  # type: ignore[typeddict-unknown-key]

        logger.info(
            "reconciliation_complete",
            attributes_reconciled=len(reconciled),
            total_entities=len(entities),
        )

        return {
            "success": True,
            "message": (
                f"Reconciled {len(reconciled)} attribute groups "
                f"from {len(entities)} entities"
            ),
            "artifacts": {
                "attributes_reconciled": len(reconciled),
                "entity_count": len(entities),
            },
        }
