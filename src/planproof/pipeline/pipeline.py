"""Pipeline orchestrator with step-registry pattern.

The ``Pipeline`` class is the main entry point for running a planning
application through PlanProof's processing stages.
"""
from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

from planproof.infrastructure.logging import get_logger
from planproof.interfaces.pipeline import PipelineContext, PipelineStep, StepResult
from planproof.schemas.config import PipelineConfig
from planproof.schemas.pipeline import (
    ComplianceReport,
    ReportSummary,
    StepStatus,
)
from planproof.schemas.pipeline import (
    StepResult as StepTelemetry,
)

logger = get_logger(__name__)


class Pipeline:
    """Orchestrator that runs registered steps in sequence.

    # DESIGN: Steps are registered, not hardcoded. Ablation toggles in
    # bootstrap.py control which steps are registered. No if-checks inside.
    """

    def __init__(self, config: PipelineConfig) -> None:
        self._steps: list[PipelineStep] = []
        self._config = config

    def register(self, step: PipelineStep) -> None:
        """Add a step to the end of the pipeline."""
        self._steps.append(step)
        logger.info("step_registered", step_name=step.name)

    def run(self, input_dir: Path) -> ComplianceReport:
        """Execute all registered steps and return a compliance report.

        Parameters
        ----------
        input_dir:
            Directory containing the planning application documents.

        Returns
        -------
        ComplianceReport:
            The final compliance report assembled from pipeline context.
        """
        context: PipelineContext = {
            "entities": [],
            "verdicts": [],
            "assessability_results": [],
            "metadata": {"input_dir": str(input_dir)},
        }

        step_telemetry: list[StepTelemetry] = []

        for step in self._steps:
            logger.info("step_started", step_name=step.name)
            start = time.perf_counter()

            try:
                result: StepResult = step.execute(context)
                elapsed_ms = (time.perf_counter() - start) * 1000

                step_telemetry.append(
                    StepTelemetry(
                        step_name=step.name,
                        status=StepStatus.SUCCESS,
                        outputs=[result.get("artifacts", {})],
                        errors=[],
                        duration_ms=elapsed_ms,
                    )
                )
                logger.info(
                    "step_completed",
                    step_name=step.name,
                    duration_ms=round(elapsed_ms, 2),
                    success=result.get("success", True),
                )

            except Exception as exc:
                elapsed_ms = (time.perf_counter() - start) * 1000
                error_msg = f"{type(exc).__name__}: {exc}"

                step_telemetry.append(
                    StepTelemetry(
                        step_name=step.name,
                        status=StepStatus.FAILED,
                        outputs=[],
                        errors=[error_msg],
                        duration_ms=elapsed_ms,
                    )
                )
                logger.error(
                    "step_failed",
                    step_name=step.name,
                    duration_ms=round(elapsed_ms, 2),
                    error=error_msg,
                )

        # Assemble final report from context
        verdicts = context.get("verdicts", [])
        assessability_results = context.get("assessability_results", [])

        passed = sum(1 for v in verdicts if v.outcome.value == "PASS")
        failed = sum(1 for v in verdicts if v.outcome.value == "FAIL")
        not_assessable = sum(
            1 for a in assessability_results if a.status == "NOT_ASSESSABLE"
        )

        return ComplianceReport(
            application_id=context.get("metadata", {}).get(
                "application_id", "unknown"
            ),
            verdicts=verdicts,
            assessability_results=assessability_results,
            summary=ReportSummary(
                total_rules=len(verdicts) + not_assessable,
                passed=passed,
                failed=failed,
                not_assessable=not_assessable,
            ),
            generated_at=datetime.now(UTC),
        )
