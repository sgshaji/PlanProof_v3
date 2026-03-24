"""Pipeline step: text extraction via OCR + LLM entity parsing."""
from __future__ import annotations

from planproof.interfaces.extraction import EntityExtractor, OCRExtractor
from planproof.interfaces.pipeline import PipelineContext, StepResult


class TextExtractionStep:
    """Extract structured entities from text-based documents (PDFs, forms).

    Chains ``OCRExtractor`` (raw text) with ``EntityExtractor`` (LLM-based
    entity parsing) to produce ``ExtractedEntity`` instances.
    """

    def __init__(
        self,
        ocr: OCRExtractor,
        entity_extractor: EntityExtractor,
    ) -> None:
        self._ocr = ocr
        self._entity_extractor = entity_extractor

    @property
    def name(self) -> str:
        return "text_extraction"

    def execute(self, context: PipelineContext) -> StepResult:
        raise NotImplementedError("Implemented in Phase 2")
