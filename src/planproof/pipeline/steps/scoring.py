"""Pipeline step: aggregate rule verdicts into application-level scores."""
from __future__ import annotations

from planproof.interfaces.pipeline import PipelineContext, StepResult


class ScoringStep:
    """Compute aggregate compliance scores from individual rule verdicts.

    Produces summary statistics (total, passed, failed, not_assessable)
    that are included in the final ``ComplianceReport``.
    """

    def __init__(self) -> None:
        pass

    @property
    def name(self) -> str:
        return "scoring"

    def execute(self, context: PipelineContext) -> StepResult:
        raise NotImplementedError("Implemented in Phase 5")
