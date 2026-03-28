"""Pipeline step: filter low-confidence extractions."""
from __future__ import annotations

from planproof.infrastructure.logging import get_logger
from planproof.interfaces.pipeline import PipelineContext, StepResult
from planproof.interfaces.reasoning import ConfidenceGate

logger = get_logger(__name__)


class ConfidenceGatingStep:
    """Remove entities whose confidence falls below method-specific thresholds.

    Uses the ``ConfidenceGate`` Protocol so that gating logic is
    testable independently of the concrete threshold configuration.
    """

    def __init__(self, gate: ConfidenceGate) -> None:
        self._gate = gate

    @property
    def name(self) -> str:
        return "confidence_gating"

    def execute(self, context: PipelineContext) -> StepResult:
        entities = context.get("entities", [])
        original_count = len(entities)

        filtered = self._gate.filter_trusted(entities)
        context["entities"] = filtered

        removed_count = original_count - len(filtered)
        logger.info(
            "confidence_gating_complete",
            original=original_count,
            retained=len(filtered),
            removed=removed_count,
        )

        return {
            "success": True,
            "message": (
                f"Retained {len(filtered)}/{original_count} entities "
                f"({removed_count} removed by confidence gate)"
            ),
            "artifacts": {
                "original_count": original_count,
                "retained_count": len(filtered),
                "removed_count": removed_count,
            },
        }
