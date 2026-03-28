"""Pipeline step: text extraction via OCR + LLM entity parsing."""
from __future__ import annotations

from pathlib import Path

from planproof.infrastructure.logging import get_logger
from planproof.interfaces.extraction import EntityExtractor, OCRExtractor
from planproof.interfaces.pipeline import PipelineContext
from planproof.interfaces.pipeline import StepResult as StepResultDict
from planproof.schemas.entities import ClassifiedDocument, ExtractedEntity

logger = get_logger(__name__)


class TextExtractionStep:
    """Extract structured entities from documents.

    Routes documents through text path (pdfplumber -> LLM) or vision path
    based on has_text_layer from the classification step.
    """

    def __init__(
        self,
        ocr: OCRExtractor,
        entity_extractor: EntityExtractor,
        vision_extractor: object | None = None,
    ) -> None:
        self._ocr = ocr
        self._entity_extractor = entity_extractor
        self._vision = vision_extractor

    @property
    def name(self) -> str:
        return "text_extraction"

    def execute(self, context: PipelineContext) -> StepResultDict:
        classified_docs: list[ClassifiedDocument] = context.get(
            "classified_documents", []
        )

        if not classified_docs:
            logger.warning("no_classified_documents")
            return {
                "success": True,
                "message": "No documents to extract from",
                "artifacts": {"entity_count": 0},
            }

        all_entities: list[ExtractedEntity] = []
        errors: list[str] = []

        for doc in classified_docs:
            try:
                entities = self._extract_from_document(doc)
                all_entities.extend(entities)
            except Exception as e:
                error_msg = f"{doc.file_path}: {type(e).__name__}: {e}"
                errors.append(error_msg)
                logger.warning("extraction_failed", file=doc.file_path, error=str(e))

        existing = context.get("entities", [])
        context["entities"] = existing + all_entities

        success = len(errors) == 0 or len(all_entities) > 0

        logger.info(
            "text_extraction_complete",
            entities=len(all_entities),
            errors=len(errors),
        )

        return {
            "success": success,
            "message": f"Extracted {len(all_entities)} entities, {len(errors)} errors",
            "artifacts": {
                "entity_count": len(all_entities),
                "error_count": len(errors),
                "errors": errors,
            },
        }

    def _extract_from_document(self, doc: ClassifiedDocument) -> list[ExtractedEntity]:
        if doc.has_text_layer:
            return self._text_path(doc)
        if self._vision is not None:
            return self._vision_path(doc)
        logger.info(
            "no_vision_extractor_skipping",
            file=doc.file_path,
            doc_type=doc.doc_type.value,
        )
        return []

    def _text_path(self, doc: ClassifiedDocument) -> list[ExtractedEntity]:
        raw_text = self._ocr.extract_text(Path(doc.file_path))
        return self._entity_extractor.extract_entities(raw_text)

    def _vision_path(self, doc: ClassifiedDocument) -> list[ExtractedEntity]:
        extractor = self._vision
        if hasattr(extractor, "extract_from_image"):
            extract_fn = getattr(extractor, "extract_from_image")
            result: list[ExtractedEntity] = extract_fn(
                Path(doc.file_path), doc_type=doc.doc_type.value
            )
            return result
        return []
