"""Compliance report generator: aggregate verdicts into a ComplianceReport."""
from __future__ import annotations

from datetime import UTC, datetime

from planproof.schemas.assessability import AssessabilityResult
from planproof.schemas.pipeline import ComplianceReport, ReportSummary
from planproof.schemas.rules import RuleOutcome, RuleVerdict


class ComplianceScorer:
    """Assemble rule verdicts and assessability results into a ComplianceReport.

    Implements the ``ReportGenerator`` protocol from
    ``planproof.interfaces.output``.
    """

    def __init__(self, application_id: str = "unknown") -> None:
        self._application_id = application_id

    def generate(
        self,
        verdicts: list[RuleVerdict],
        assessability_results: list[AssessabilityResult],
    ) -> ComplianceReport:
        """Build a ComplianceReport from verdicts and assessability results.

        Args:
            verdicts: Rule verdicts produced by the rule evaluation step.
            assessability_results: Assessability results for all rules checked.

        Returns:
            A fully-populated ComplianceReport with aggregate summary counts.
        """
        not_assessable_results = [
            r for r in assessability_results if r.status == "NOT_ASSESSABLE"
        ]

        passed = sum(1 for v in verdicts if v.outcome == RuleOutcome.PASS)
        failed = sum(1 for v in verdicts if v.outcome == RuleOutcome.FAIL)
        not_assessable = len(not_assessable_results)
        total_rules = len(verdicts) + not_assessable

        summary = ReportSummary(
            total_rules=total_rules,
            passed=passed,
            failed=failed,
            not_assessable=not_assessable,
        )

        return ComplianceReport(
            application_id=self._application_id,
            verdicts=verdicts,
            assessability_results=assessability_results,
            summary=summary,
            generated_at=datetime.now(UTC),
        )
