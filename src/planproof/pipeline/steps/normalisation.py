"""Pipeline step: entity normalisation and unit conversion."""
from __future__ import annotations

from planproof.interfaces.pipeline import PipelineContext, StepResult


class NormalisationStep:
    """Normalise extracted entities to canonical units and formats.

    Converts measurements to SI units, standardises address formats,
    and resolves abbreviations so that downstream comparison logic
    operates on uniform representations.
    """

    def __init__(self) -> None:
        pass

    @property
    def name(self) -> str:
        return "normalisation"

    def execute(self, context: PipelineContext) -> StepResult:
        raise NotImplementedError("Implemented in Phase 3")
