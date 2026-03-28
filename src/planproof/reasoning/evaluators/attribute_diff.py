"""Evaluator: cross-attribute difference check (C4)."""
from __future__ import annotations

from typing import Any

from planproof.schemas.reconciliation import ReconciledEvidence
from planproof.schemas.rules import RuleOutcome, RuleVerdict


class AttributeDiffEvaluator:
    """Evaluate whether proposed plan attributes differ materially from approved.

    Used for cross-document consistency checks like C4, where key attributes
    (building_height, building_footprint_area, number_of_storeys) in a proposed
    plan are compared against the same attributes in a previously approved plan.

    ``evidence.best_value`` must be a dict mapping each attribute name to a
    nested dict with keys ``"proposed"`` and ``"approved"``::

        {
            "building_height": {"proposed": 7.5, "approved": 7.5},
            "number_of_storeys": {"proposed": 2, "approved": 2},
        }

    Parameters (from YAML)
    ----------------------
    attributes : list[str]
        List of attribute names to compare.
    tolerances : dict[str, float] | None
        Per-attribute tolerance as an absolute difference. Defaults to 0
        (exact equality required).
    """

    def __init__(self, parameters: dict[str, Any]) -> None:
        self._params = parameters

    def evaluate(
        self, evidence: ReconciledEvidence, params: dict[str, Any]
    ) -> RuleVerdict:
        rule_id: str = self._params.get("rule_id", params.get("rule_id", "unknown"))
        attributes: list[str] = self._params.get("attributes", [])
        tolerances: dict[str, float] = self._params.get("tolerances", {})

        if evidence.best_value is None:
            return RuleVerdict(
                rule_id=rule_id,
                outcome=RuleOutcome.FAIL,
                evidence_used=evidence.sources,
                explanation="Insufficient evidence: no value available for evaluation.",
                evaluated_value=None,
                threshold=tolerances,
            )

        best: dict[str, Any] = evidence.best_value  # type: ignore[assignment]

        diffs: dict[str, dict[str, Any]] = {}
        violations: list[str] = []

        for attr in attributes:
            if attr not in best:
                continue
            pair = best[attr]
            proposed = float(pair.get("proposed", 0))
            approved = float(pair.get("approved", 0))
            diff = abs(proposed - approved)
            tol = float(tolerances.get(attr, 0))
            exceeds = diff > tol
            diffs[attr] = {
                "proposed": proposed,
                "approved": approved,
                "diff": diff,
                "tolerance": tol,
                "exceeds": exceeds,
            }
            if exceeds:
                violations.append(
                    f"{attr}: proposed={proposed} approved={approved} "
                    f"diff={diff} > {tol}"
                )

        passed = len(violations) == 0
        outcome = RuleOutcome.PASS if passed else RuleOutcome.FAIL

        if passed:
            explanation = (
                "All checked attributes match between proposed and approved plans."
            )
        else:
            explanation = (
                f"Material differences detected in {len(violations)} attribute(s): "
                + "; ".join(violations)
            )

        return RuleVerdict(
            rule_id=rule_id,
            outcome=outcome,
            evidence_used=evidence.sources,
            explanation=explanation,
            evaluated_value=diffs,
            threshold=tolerances,
        )
