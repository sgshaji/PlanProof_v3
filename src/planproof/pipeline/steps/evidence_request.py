"""Pipeline step: generate evidence requests for non-assessable rules."""
from __future__ import annotations

from planproof.interfaces.output import EvidenceRequestGenerator
from planproof.interfaces.pipeline import PipelineContext, StepResult


class EvidenceRequestStep:
    """Generate actionable evidence requests for NOT_ASSESSABLE rules.

    For each rule that cannot be assessed, produces a structured request
    telling the applicant exactly which documents or measurements are
    needed to unblock evaluation.
    """

    def __init__(self, generator: EvidenceRequestGenerator) -> None:
        self._generator = generator

    @property
    def name(self) -> str:
        return "evidence_request"

    def execute(self, context: PipelineContext) -> StepResult:
        raise NotImplementedError("Implemented in Phase 5")
