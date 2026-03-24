"""Evaluator: absolute numeric threshold comparison (R001, R002)."""
from __future__ import annotations

from typing import Any

from planproof.schemas.reconciliation import ReconciledEvidence
from planproof.schemas.rules import RuleVerdict


class NumericThresholdEvaluator:
    """Evaluate whether a numeric value meets a maximum or minimum threshold.

    Used for rules like R001 (max building height) and R002 (min rear garden
    depth) where a single numeric measurement is compared against a fixed
    regulatory limit.

    Parameters (from YAML)
    ----------------------
    attribute : str
        The entity attribute to evaluate.
    operator : str
        Comparison operator (``"<="`` or ``">="``).
    threshold : float
        The regulatory limit value.
    unit : str
        Expected unit of measurement (e.g. ``"metres"``).
    """

    def __init__(self, parameters: dict[str, Any]) -> None:
        self._params = parameters

    def evaluate(
        self, evidence: ReconciledEvidence, params: dict[str, Any]
    ) -> RuleVerdict:
        raise NotImplementedError("Implemented in Phase 4")
