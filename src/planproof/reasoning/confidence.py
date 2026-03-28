"""Confidence gating for extracted entities.

Implements the ConfidenceGate Protocol from planproof.interfaces.reasoning.
Entities below per-method, per-type thresholds are excluded from the
evidence pool before reconciliation runs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from planproof.infrastructure.logging import get_logger
from planproof.schemas.entities import ExtractedEntity

_log = get_logger(__name__)


class ThresholdConfidenceGate:
    """Filter entities by per-method, per-type confidence thresholds.

    Parameters
    ----------
    thresholds:
        Nested dict keyed by extraction_method value then entity_type value,
        mapping to a float threshold in [0, 1].
        Example::

            {
                "OCR_LLM": {"MEASUREMENT": 0.80, "ADDRESS": 0.85},
                "VLM_ZEROSHOT": {"MEASUREMENT": 0.70},
            }

        If the method or entity_type is absent the entity is treated as
        trustworthy (fail-open, not fail-closed).
    """

    def __init__(self, thresholds: dict[str, dict[str, float]]) -> None:
        self._thresholds = thresholds

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    def is_trustworthy(self, entity: ExtractedEntity) -> bool:
        """Return True when *entity* meets or exceeds its configured threshold.

        Defaults to True when the method or entity_type is not in the config.
        """
        method_key = entity.extraction_method.value
        type_key = entity.entity_type.value

        method_thresholds = self._thresholds.get(method_key)
        if method_thresholds is None:
            _log.debug(
                "confidence_gate.method_not_configured",
                method=method_key,
                entity_type=type_key,
                action="default_trustworthy",
            )
            return True

        threshold = method_thresholds.get(type_key)
        if threshold is None:
            _log.debug(
                "confidence_gate.type_not_configured",
                method=method_key,
                entity_type=type_key,
                action="default_trustworthy",
            )
            return True

        trusted = entity.confidence >= threshold
        if not trusted:
            _log.debug(
                "confidence_gate.entity_rejected",
                method=method_key,
                entity_type=type_key,
                confidence=entity.confidence,
                threshold=threshold,
            )
        return trusted

    def filter_trusted(
        self, entities: list[ExtractedEntity]
    ) -> list[ExtractedEntity]:
        """Return only entities that pass is_trustworthy."""
        return [e for e in entities if self.is_trustworthy(e)]

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_yaml(cls, path: Path) -> ThresholdConfidenceGate:
        """Load thresholds from a YAML file and return a configured gate.

        The YAML file must have a top-level ``thresholds`` key whose value is
        a nested mapping of extraction_method -> entity_type -> float.

        Parameters
        ----------
        path:
            Absolute or relative path to the YAML config file.
        """
        raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
        thresholds: dict[str, dict[str, float]] = raw["thresholds"]
        _log.info("confidence_gate.loaded_from_yaml", path=str(path))
        return cls(thresholds=thresholds)
