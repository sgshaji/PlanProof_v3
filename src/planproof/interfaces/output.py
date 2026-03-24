"""Protocols for output generation (Layer 4).

Covers the final compliance report and evidence-request generation for
rules that could not be assessed.
"""
from __future__ import annotations

from typing import Protocol

from planproof.schemas.assessability import AssessabilityResult
from planproof.schemas.pipeline import ComplianceReport, EvidenceRequest
from planproof.schemas.rules import RuleVerdict


class ReportGenerator(Protocol):
    """Contract: assemble verdicts and assessability results into a report."""

    def generate(
        self,
        verdicts: list[RuleVerdict],
        assessability_results: list[AssessabilityResult],
    ) -> ComplianceReport: ...


class EvidenceRequestGenerator(Protocol):
    """Contract: produce actionable requests for missing evidence.

    # DESIGN: Only called for rules classified as NOT_ASSESSABLE or
    # PARTIALLY_ASSESSABLE.  Each request tells the applicant *exactly*
    # which document / attribute is needed to unblock assessment.
    """

    def generate_requests(
        self, not_assessable: list[AssessabilityResult]
    ) -> list[EvidenceRequest]: ...
