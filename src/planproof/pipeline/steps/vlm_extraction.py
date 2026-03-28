"""Pipeline step: VLM-based extraction from architectural drawings."""
from __future__ import annotations

from pathlib import Path

from planproof.infrastructure.logging import get_logger
from planproof.interfaces.extraction import VLMExtractor
from planproof.interfaces.pipeline import PipelineContext, StepResult
from planproof.schemas.entities import ClassifiedDocument, DocumentType

logger = get_logger(__name__)


class VLMExtractionStep:
    """Extract spatial attributes from architectural drawings using a VLM.

    Filters for DRAWING documents without text layers (those are handled
    by TextExtractionStep). Delegates extraction to the VLMExtractor Protocol.
    """

    def __init__(self, vlm: VLMExtractor) -> None:
        self._vlm = vlm

    @property
    def name(self) -> str:
        return "vlm_extraction"

    def execute(self, context: PipelineContext) -> StepResult:
        classified_docs: list[ClassifiedDocument] = context.get(
            "classified_documents", []
        )

        drawings = [
            doc
            for doc in classified_docs
            if doc.doc_type == DocumentType.DRAWING and not doc.has_text_layer
        ]

        if not drawings:
            logger.info("vlm_no_drawings_to_process")
            return {
                "success": True,
                "message": "No drawings for VLM extraction",
                "artifacts": {"entity_count": 0},
            }

        all_entities = []
        errors: list[str] = []

        for doc in drawings:
            try:
                entities = self._vlm.extract_spatial_attributes(Path(doc.file_path))
                all_entities.extend(entities)
            except Exception as e:  # noqa: BLE001
                error_msg = f"{doc.file_path}: {type(e).__name__}: {e}"
                errors.append(error_msg)
                logger.warning(
                    "vlm_extraction_failed", file=doc.file_path, error=str(e)
                )

        existing = context.get("entities", [])
        context["entities"] = existing + all_entities

        success = len(errors) == 0 or len(all_entities) > 0

        logger.info(
            "vlm_extraction_complete",
            entities=len(all_entities),
            drawings=len(drawings),
            errors=len(errors),
        )

        return {
            "success": success,
            "message": (
                f"VLM extracted {len(all_entities)} entities "
                f"from {len(drawings)} drawings"
            ),
            "artifacts": {
                "entity_count": len(all_entities),
                "drawing_count": len(drawings),
                "error_count": len(errors),
            },
        }
