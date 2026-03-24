"""Pipeline step: determine whether rules can be evaluated."""
from __future__ import annotations

from planproof.interfaces.pipeline import PipelineContext, StepResult
from planproof.interfaces.reasoning import AssessabilityEvaluator


class AssessabilityStep:
    """Classify each rule as ASSESSABLE or NOT_ASSESSABLE.

    This is the core research contribution of PlanProof.  Rules that lack
    sufficient evidence are explicitly flagged rather than being forced into
    a binary PASS/FAIL verdict.
    """

    def __init__(self, evaluator: AssessabilityEvaluator) -> None:
        self._evaluator = evaluator

    @property
    def name(self) -> str:
        return "assessability"

    def execute(self, context: PipelineContext) -> StepResult:
        raise NotImplementedError("Implemented in Phase 4")
