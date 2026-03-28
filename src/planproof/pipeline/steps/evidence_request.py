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
        """Generate evidence requests for NOT_ASSESSABLE rules.

        Retrieves assessability results from the context, filters to
        status=="NOT_ASSESSABLE", calls the generator to produce requests,
        and stores them in context["metadata"]["evidence_requests"].

        Args:
            context: Pipeline context containing assessability_results.

        Returns:
            StepResult with success=True and request count in artifacts.
        """
        # Extract assessability results from context
        assessability_results = context.get("assessability_results", [])

        # Filter to NOT_ASSESSABLE results only
        not_assessable = [
            result for result in assessability_results
            if result.status == "NOT_ASSESSABLE"
        ]

        # Generate evidence requests
        requests = self._generator.generate_requests(not_assessable)

        # Store requests in context
        context["metadata"]["evidence_requests"] = requests

        # Return success with request count as artifacts
        return {
            "success": True,
            "message": f"Generated {len(requests)} evidence requests",
            "artifacts": {
                "request_count": len(requests),
            },
        }
