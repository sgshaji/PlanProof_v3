"""Evaluator: enumeration membership check (C1)."""
from __future__ import annotations

from typing import Any

from planproof.schemas.reconciliation import ReconciledEvidence
from planproof.schemas.rules import RuleVerdict


class EnumCheckEvaluator:
    """Evaluate whether a categorical value belongs to an allowed set.

    Used for cross-document consistency checks like C1, where a value
    extracted from one document must match one of a set of permitted
    values defined by another document or reference data.

    Parameters (from YAML)
    ----------------------
    attribute : str
        The entity attribute to check.
    valid_values : list[str]
        The set of permitted values.
    """

    def __init__(self, parameters: dict[str, Any]) -> None:
        self._params = parameters

    def evaluate(
        self, evidence: ReconciledEvidence, params: dict[str, Any]
    ) -> RuleVerdict:
        raise NotImplementedError("Implemented in Phase 4")
