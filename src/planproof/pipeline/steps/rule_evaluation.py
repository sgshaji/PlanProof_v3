"""Pipeline step: evaluate compliance rules against reconciled evidence."""
from __future__ import annotations

from pathlib import Path
from typing import cast

from planproof.infrastructure.logging import get_logger
from planproof.interfaces.pipeline import PipelineContext, StepResult
from planproof.reasoning.evaluators.factory import RuleFactory
from planproof.schemas.reconciliation import ReconciledEvidence, ReconciliationStatus

logger = get_logger(__name__)


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
        rules = self._rule_factory.load_rules(self._rules_dir)

        assessability_results = context.get("assessability_results", [])
        reconciled_evidence: dict[str, ReconciledEvidence] = cast(
            dict[str, ReconciledEvidence],
            context.get("reconciled_evidence", {}),
        )

        # Build a set of assessable rule IDs; if no assessability step ran,
        # treat all rules as assessable.
        if assessability_results:
            assessable_ids = {
                r.rule_id for r in assessability_results if r.status == "ASSESSABLE"
            }
        else:
            assessable_ids = {config.rule_id for config, _ in rules}

        verdicts = []
        skipped = 0
        for config, evaluator in rules:
            if config.rule_id not in assessable_ids:
                skipped += 1
                logger.debug(
                    "rule_skipped_not_assessable",
                    rule_id=config.rule_id,
                )
                continue

            fallback = ReconciledEvidence(
                attribute=config.rule_id,
                status=ReconciliationStatus.MISSING,
                sources=[],
            )
            evidence: ReconciledEvidence = reconciled_evidence.get(
                config.rule_id, fallback
            )
            verdict = evaluator.evaluate(evidence, config.parameters)
            verdicts.append(verdict)

        context["verdicts"] = verdicts

        pass_count = sum(1 for v in verdicts if v.outcome == "PASS")
        fail_count = len(verdicts) - pass_count

        logger.info(
            "rule_evaluation_complete",
            evaluated=len(verdicts),
            skipped=skipped,
            passed=pass_count,
            failed=fail_count,
        )

        return {
            "success": True,
            "message": (
                f"Evaluated {len(verdicts)} rules "
                f"({pass_count} pass, {fail_count} fail, {skipped} skipped)"
            ),
            "artifacts": {
                "evaluated_count": len(verdicts),
                "pass_count": pass_count,
                "fail_count": fail_count,
                "skipped_count": skipped,
            },
        }
