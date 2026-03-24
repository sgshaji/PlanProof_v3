"""Schemas for rule definitions, evaluation, and verdicts.

Rules represent individual planning policy requirements. They are defined
declaratively in YAML configuration files and evaluated by the rule engine
against reconciled evidence.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from planproof.schemas.assessability import EvidenceRequirement
from planproof.schemas.entities import ExtractedEntity


class RuleOutcome(StrEnum):
    """Binary outcome of evaluating a single rule."""

    PASS = "PASS"
    FAIL = "FAIL"


class RuleVerdict(BaseModel):
    """The result of evaluating a single rule against extracted evidence."""

    rule_id: str
    outcome: RuleOutcome
    evidence_used: list[ExtractedEntity]
    explanation: str
    evaluated_value: Any
    threshold: Any

    model_config = {"from_attributes": True}


class RuleConfig(BaseModel):
    """Declarative rule definition loaded from YAML configuration files.

    # WHY: Separating rule definitions from rule logic allows domain experts
    # to author new rules without touching Python code. The evaluation_type
    # field dispatches to the appropriate evaluation strategy at runtime.
    """

    rule_id: str
    description: str
    policy_source: str
    evaluation_type: str
    parameters: dict[str, Any]
    required_evidence: list[EvidenceRequirement]

    model_config = {"from_attributes": True}
