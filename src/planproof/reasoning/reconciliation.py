"""PairwiseReconciler: resolve conflicting evidence across document sources.

Implements the ``Reconciler`` protocol from ``planproof.interfaces.reasoning``
by comparing every pair of extracted values for a given attribute and
deciding whether they AGREE, CONFLICT, come from a SINGLE_SOURCE, or are
MISSING entirely.
"""
from __future__ import annotations

from typing import Any

from planproof.infrastructure.logging import get_logger
from planproof.schemas.entities import ExtractedEntity
from planproof.schemas.reconciliation import ReconciledEvidence, ReconciliationStatus

logger = get_logger(__name__)

# Default absolute tolerance for numeric comparisons (in the attribute's unit).
_DEFAULT_NUMERIC_TOLERANCE: float = 0.5


class PairwiseReconciler:
    """Resolve conflicting extractions for a single attribute by pairwise comparison.

    For each pair of extracted values the reconciler checks whether they agree
    within a configurable tolerance (numeric) or are identical (string).
    If **all** pairs agree the status is AGREED and ``best_value`` is the mean
    (numeric) or the shared value (string).  If **any** pair disagrees the
    status is CONFLICTING and ``conflict_details`` describes the first
    conflicting pair found.

    Parameters
    ----------
    tolerances:
        Per-attribute absolute numeric tolerances.  Attributes not listed fall
        back to ``_DEFAULT_NUMERIC_TOLERANCE``.
    """

    def __init__(
        self,
        tolerances: dict[str, float] | None = None,
    ) -> None:
        self._tolerances: dict[str, float] = tolerances or {}

    # ------------------------------------------------------------------
    # Public API — satisfies the Reconciler Protocol
    # ------------------------------------------------------------------

    def reconcile(
        self, entities: list[ExtractedEntity], attribute: str
    ) -> ReconciledEvidence:
        """Reconcile all evidence for *attribute*.

        Parameters
        ----------
        entities:
            All extracted entities that speak to this attribute.
        attribute:
            The attribute name being reconciled (used for tolerance lookup
            and in the returned schema).

        Returns
        -------
        ReconciledEvidence
            Populated with the reconciliation outcome.
        """
        logger.debug(
            "reconciling",
            attribute=attribute,
            n_entities=len(entities),
        )

        if not entities:
            return ReconciledEvidence(
                attribute=attribute,
                status=ReconciliationStatus.MISSING,
                best_value=None,
                sources=[],
                conflict_details=None,
            )

        sources = list(entities)  # copy so callers cannot mutate

        if len(entities) == 1:
            return ReconciledEvidence(
                attribute=attribute,
                status=ReconciliationStatus.SINGLE_SOURCE,
                best_value=entities[0].value,
                sources=sources,
                conflict_details=None,
            )

        # Two or more entities — pairwise comparison
        values = [e.value for e in entities]
        tolerance = self._tolerances.get(attribute, _DEFAULT_NUMERIC_TOLERANCE)

        conflict_details = self._find_conflict(values, tolerance)

        if conflict_details is not None:
            logger.info(
                "conflict detected",
                attribute=attribute,
                details=conflict_details,
            )
            return ReconciledEvidence(
                attribute=attribute,
                status=ReconciliationStatus.CONFLICTING,
                best_value=None,
                sources=sources,
                conflict_details=conflict_details,
            )

        best_value = self._compute_best_value(values)
        logger.debug("agreed", attribute=attribute, best_value=best_value)
        return ReconciledEvidence(
            attribute=attribute,
            status=ReconciliationStatus.AGREED,
            best_value=best_value,
            sources=sources,
            conflict_details=None,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_numeric(value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    def _find_conflict(self, values: list[Any], tolerance: float) -> str | None:
        """Return a description of the first conflicting pair, or None if all agree."""
        for i in range(len(values)):
            for j in range(i + 1, len(values)):
                a, b = values[i], values[j]
                if self._is_numeric(a) and self._is_numeric(b):
                    diff = abs(float(a) - float(b))
                    if diff > tolerance:
                        return (
                            f"Values {a} and {b} differ by {diff:.4g}, "
                            f"which exceeds the tolerance of {tolerance} "
                            f"(sources index {i} vs {j})"
                        )
                else:
                    # String / non-numeric: require exact equality
                    if a != b:
                        return (
                            f"Values {a!r} and {b!r} do not match "
                            f"(sources index {i} vs {j})"
                        )
        return None

    def _compute_best_value(self, values: list[Any]) -> Any:
        """Compute the agreed best value from a list of agreeing values."""
        if all(self._is_numeric(v) for v in values):
            return sum(float(v) for v in values) / len(values)
        # For strings (and other non-numeric types) all values are identical
        # (because _find_conflict passed), so any value is the best.
        return values[0]
