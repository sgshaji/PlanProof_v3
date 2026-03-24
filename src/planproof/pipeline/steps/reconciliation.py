"""Pipeline step: cross-source evidence reconciliation."""
from __future__ import annotations

from planproof.interfaces.graph import EvidenceProvider
from planproof.interfaces.pipeline import PipelineContext, StepResult
from planproof.interfaces.reasoning import Reconciler


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
        raise NotImplementedError("Implemented in Phase 4")
