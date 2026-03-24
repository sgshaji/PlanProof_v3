"""Evaluator: cross-attribute difference check (C4)."""
from __future__ import annotations

from typing import Any

from planproof.schemas.reconciliation import ReconciledEvidence
from planproof.schemas.rules import RuleVerdict


class AttributeDiffEvaluator:
    """Evaluate whether the difference between two attributes is within bounds.

    Used for cross-document consistency checks like C4, where derived
    attributes must be consistent with their constituent values (e.g.
    total floor area should equal the sum of individual floor areas).

    Parameters (from YAML)
    ----------------------
    attribute_a : str
        First attribute.
    attribute_b : str
        Second attribute (or a computed aggregate).
    max_diff : float
        Maximum allowed absolute difference.
    """

    def __init__(self, parameters: dict[str, Any]) -> None:
        self._params = parameters

    def evaluate(
        self, evidence: ReconciledEvidence, params: dict[str, Any]
    ) -> RuleVerdict:
        raise NotImplementedError("Implemented in Phase 4")
