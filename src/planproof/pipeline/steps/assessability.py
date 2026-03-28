"""Pipeline step: determine whether rules can be evaluated."""
from __future__ import annotations

from planproof.infrastructure.logging import get_logger
from planproof.interfaces.pipeline import PipelineContext, StepResult
from planproof.interfaces.reasoning import AssessabilityEvaluator

logger = get_logger(__name__)


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
        rule_ids: list[str] = context.get("metadata", {}).get("rule_ids", [])

        results = []
        for rule_id in rule_ids:
            result = self._evaluator.evaluate(rule_id)
            results.append(result)

        context["assessability_results"] = results

        assessable_count = sum(1 for r in results if r.status == "ASSESSABLE")
        not_assessable_count = len(results) - assessable_count

        logger.info(
            "assessability_complete",
            total_rules=len(results),
            assessable=assessable_count,
            not_assessable=not_assessable_count,
        )

        return {
            "success": True,
            "message": (
                f"Evaluated {len(results)} rules: "
                f"{assessable_count} assessable, "
                f"{not_assessable_count} not assessable"
            ),
            "artifacts": {
                "total_rules": len(results),
                "assessable_count": assessable_count,
                "not_assessable_count": not_assessable_count,
            },
        }
