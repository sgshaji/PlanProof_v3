"""Schemas for pipeline orchestration and compliance reporting.

These models capture the output of each pipeline step, the final compliance
report, and evidence request generation for incomplete applications.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from planproof.schemas.assessability import AssessabilityResult
from planproof.schemas.rules import RuleVerdict


class StepStatus(StrEnum):
    """Outcome of a single pipeline step."""

    SUCCESS = "SUCCESS"
    # WHY: PARTIAL allows the pipeline to continue when some documents fail
    # extraction but others succeed — a single corrupted PDF should not block
    # the entire application from being assessed.
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class StepResult(BaseModel):
    """Telemetry and output for a single pipeline step execution."""

    step_name: str
    status: StepStatus
    outputs: list[Any]
    errors: list[str]
    duration_ms: float

    model_config = {"from_attributes": True}


class ReportSummary(BaseModel):
    """Aggregate counts for the compliance report."""

    total_rules: int
    passed: int
    failed: int
    not_assessable: int

    model_config = {"from_attributes": True}


class MissingEvidence(BaseModel):
    """Describes a single piece of evidence the applicant should provide."""

    attribute: str
    acceptable_document_types: list[str]
    guidance: str

    model_config = {"from_attributes": True}


class EvidenceRequest(BaseModel):
    """A request for additional evidence to make a rule assessable.

    # WHY: Rather than just saying "NOT_ASSESSABLE", we generate actionable
    # guidance telling the applicant exactly what documents or measurements
    # are needed and where to find them.
    """

    rule_id: str
    missing: list[MissingEvidence]

    model_config = {"from_attributes": True}


class ComplianceReport(BaseModel):
    """Final output of the PlanProof pipeline for one planning application."""

    application_id: str
    verdicts: list[RuleVerdict]
    assessability_results: list[AssessabilityResult]
    summary: ReportSummary
    generated_at: datetime

    model_config = {"from_attributes": True}
