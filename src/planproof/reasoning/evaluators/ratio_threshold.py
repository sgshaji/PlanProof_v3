"""Evaluator: ratio-based threshold comparison (R003)."""
from __future__ import annotations

from typing import Any

from planproof.schemas.reconciliation import ReconciledEvidence
from planproof.schemas.rules import RuleVerdict


class RatioThresholdEvaluator:
    """Evaluate whether a computed ratio meets a regulatory threshold.

    Used for rules like R003 (site coverage) where two measurements
    (e.g. building footprint area and total site area) are combined into
    a ratio that must not exceed a limit.

    Parameters (from YAML)
    ----------------------
    numerator_attribute : str
        The attribute providing the numerator value.
    denominator_attribute : str
        The attribute providing the denominator value.
    operator : str
        Comparison operator (``"<="`` or ``">="``).
    threshold : float
        The maximum or minimum allowed ratio.
    """

    def __init__(self, parameters: dict[str, Any]) -> None:
        self._params = parameters

    def evaluate(
        self, evidence: ReconciledEvidence, params: dict[str, Any]
    ) -> RuleVerdict:
        raise NotImplementedError("Implemented in Phase 4")
