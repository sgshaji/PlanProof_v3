"""Evaluator: fuzzy string matching for cross-document consistency (C2)."""
from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from planproof.schemas.reconciliation import ReconciledEvidence
from planproof.schemas.rules import RuleOutcome, RuleVerdict


def _similarity(a: str, b: str) -> float:
    """Return similarity ratio between two strings.

    Uses rapidfuzz if available, falls back to difflib.SequenceMatcher.
    """
    try:
        from rapidfuzz import fuzz  # type: ignore[import-not-found]

        result: float = fuzz.ratio(a, b) / 100.0
        return result
    except ImportError:
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()


class FuzzyMatchEvaluator:
    """Evaluate whether string values from different sources are equivalent.

    Used for cross-document consistency checks like C2, where addresses
    or names extracted from different documents must refer to the same
    entity despite minor formatting differences (abbreviations, typos,
    word order).

    Parameters (from YAML)
    ----------------------
    attribute_a : str
        First attribute name (e.g. form_address).
    attribute_b : str
        Second attribute name (e.g. drawing_address).
    min_similarity : float
        Minimum similarity score (0.0-1.0) to consider a match.
    """

    def __init__(self, parameters: dict[str, Any]) -> None:
        self._params = parameters

    def evaluate(
        self, evidence: ReconciledEvidence, params: dict[str, Any]
    ) -> RuleVerdict:
        rule_id: str = self._params.get("rule_id", params.get("rule_id", "unknown"))
        min_ratio: float = float(
            self._params.get(
                "min_similarity", self._params.get("min_ratio", 0.85)
            )
        )

        if evidence.best_value is None:
            return RuleVerdict(
                rule_id=rule_id,
                outcome=RuleOutcome.FAIL,
                evidence_used=evidence.sources,
                explanation="Insufficient evidence: no value available for evaluation.",
                evaluated_value=None,
                threshold=min_ratio,
            )

        # best_value is either a dict keyed by attribute_a / attribute_b,
        # or a tuple/list of (value_a, value_b).
        best: Any = evidence.best_value
        if isinstance(best, dict):
            key_a: str = self._params.get("attribute_a", "")
            key_b: str = self._params.get("attribute_b", "")
            value_a: str = str(best[key_a])
            value_b: str = str(best[key_b])
        else:
            # Fallback: treat as (value_a, value_b) sequence
            seq: list[Any] = list(best)
            value_a = str(seq[0])
            value_b = str(seq[1])

        ratio: float = _similarity(value_a, value_b)
        passed = ratio >= min_ratio
        outcome = RuleOutcome.PASS if passed else RuleOutcome.FAIL

        if passed:
            explanation = (
                f"Strings are sufficiently similar "
                f"(similarity={ratio:.2f} >= {min_ratio})."
            )
        else:
            explanation = (
                f"Strings differ too much "
                f"(similarity={ratio:.2f} < {min_ratio}): "
                f"{value_a!r} vs {value_b!r}."
            )

        return RuleVerdict(
            rule_id=rule_id,
            outcome=outcome,
            evidence_used=evidence.sources,
            explanation=explanation,
            evaluated_value=ratio,
            threshold=min_ratio,
        )
