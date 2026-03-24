"""Evaluator: numeric equality within tolerance (C3)."""
from __future__ import annotations

from typing import Any

from planproof.schemas.reconciliation import ReconciledEvidence
from planproof.schemas.rules import RuleVerdict


class NumericToleranceEvaluator:
    """Evaluate whether numeric values from different sources agree within tolerance.

    Used for cross-document consistency checks like C3, where the same
    measurement (e.g. site area) appears in multiple documents and must
    agree within an acceptable margin of error.

    Parameters (from YAML)
    ----------------------
    attribute : str
        The entity attribute to compare across sources.
    tolerance_pct : float
        Maximum allowed percentage difference between values.
    tolerance_abs : float | None
        Optional absolute tolerance (used when percentage is too coarse).
    """

    def __init__(self, parameters: dict[str, Any]) -> None:
        self._params = parameters

    def evaluate(
        self, evidence: ReconciledEvidence, params: dict[str, Any]
    ) -> RuleVerdict:
        raise NotImplementedError("Implemented in Phase 4")
