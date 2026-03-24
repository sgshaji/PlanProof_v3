"""Pipeline step: evaluate compliance rules against reconciled evidence."""
from __future__ import annotations

from pathlib import Path

from planproof.interfaces.pipeline import PipelineContext, StepResult
from planproof.reasoning.evaluators.factory import RuleFactory


class RuleEvaluationStep:
    """Evaluate each assessable rule and produce PASS/FAIL verdicts.

    Only rules classified as ASSESSABLE by the preceding step are evaluated.
    The RuleFactory loads rule definitions from YAML and dispatches to the
    correct evaluator based on ``evaluation_type``.
    """

    def __init__(
        self,
        rule_factory: RuleFactory,
        rules_dir: Path,
    ) -> None:
        self._rule_factory = rule_factory
        self._rules_dir = rules_dir

    @property
    def name(self) -> str:
        return "rule_evaluation"

    def execute(self, context: PipelineContext) -> StepResult:
        raise NotImplementedError("Implemented in Phase 4")
