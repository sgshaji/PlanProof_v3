"""Pipeline step: aggregate rule verdicts into application-level scores."""
from __future__ import annotations

from planproof.interfaces.pipeline import PipelineContext, StepResult
from planproof.output.scoring import ComplianceScorer


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
        """Generate a ComplianceReport from verdicts and assessability results.

        Retrieves verdicts and assessability results from the context,
        creates a ComplianceScorer with the application_id, generates
        the report, and stores it in context["metadata"]["compliance_report"].

        Args:
            context: Pipeline context containing verdicts and assessability_results.

        Returns:
            StepResult with success=True and summary counts in artifacts.
        """
        # Extract data from context
        verdicts = context.get("verdicts", [])
        assessability_results = context.get("assessability_results", [])
        metadata = context.get("metadata", {})
        application_id = metadata.get("application_id", "unknown")

        # Create scorer and generate report
        scorer = ComplianceScorer(application_id=application_id)
        report = scorer.generate(verdicts, assessability_results)

        # Store report in context
        context["metadata"]["compliance_report"] = report

        # Return success with summary counts as artifacts
        return {
            "success": True,
            "message": f"Generated compliance report for {application_id}",
            "artifacts": {
                "total_rules": report.summary.total_rules,
                "passed": report.summary.passed,
                "failed": report.summary.failed,
                "not_assessable": report.summary.not_assessable,
            },
        }
