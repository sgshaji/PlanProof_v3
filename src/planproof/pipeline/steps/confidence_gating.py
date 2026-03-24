"""Pipeline step: filter low-confidence extractions."""
from __future__ import annotations

from planproof.interfaces.pipeline import PipelineContext, StepResult
from planproof.interfaces.reasoning import ConfidenceGate


class ConfidenceGatingStep:
    """Remove entities whose confidence falls below method-specific thresholds.

    Uses the ``ConfidenceGate`` Protocol so that gating logic is
    testable independently of the concrete threshold configuration.
    """

    def __init__(self, gate: ConfidenceGate) -> None:
        self._gate = gate

    @property
    def name(self) -> str:
        return "confidence_gating"

    def execute(self, context: PipelineContext) -> StepResult:
        raise NotImplementedError("Implemented in Phase 4")
