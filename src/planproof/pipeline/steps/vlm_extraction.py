"""Pipeline step: VLM-based extraction from architectural drawings."""
from __future__ import annotations

from planproof.interfaces.extraction import VLMExtractor
from planproof.interfaces.pipeline import PipelineContext, StepResult


class VLMExtractionStep:
    """Extract spatial attributes from architectural drawings using a VLM.

    Uses the ``VLMExtractor`` Protocol to analyse building plans, site plans,
    and elevation drawings, producing ``ExtractedEntity`` instances with
    spatial grounding information.
    """

    def __init__(self, vlm: VLMExtractor) -> None:
        self._vlm = vlm

    @property
    def name(self) -> str:
        return "vlm_extraction"

    def execute(self, context: PipelineContext) -> StepResult:
        raise NotImplementedError("Implemented in Phase 2")
