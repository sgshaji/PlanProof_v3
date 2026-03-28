"""Pipeline step: document classification."""
from __future__ import annotations

from pathlib import Path

from planproof.infrastructure.logging import get_logger
from planproof.interfaces.extraction import DocumentClassifier
from planproof.interfaces.pipeline import PipelineContext
from planproof.interfaces.pipeline import StepResult as StepResultDict
from planproof.schemas.entities import ClassifiedDocument

logger = get_logger(__name__)

SUPPORTED_EXTENSIONS = frozenset({
    ".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp",
})


class ClassificationStep:
    """Classify each input document into a known type (FORM, DRAWING, etc.)."""

    def __init__(self, classifier: DocumentClassifier) -> None:
        self._classifier = classifier

    @property
    def name(self) -> str:
        return "classification"

    def execute(self, context: PipelineContext) -> StepResultDict:
        input_dir_str = context.get("metadata", {}).get("input_dir", "")
        input_dir = Path(input_dir_str)

        if not input_dir.exists():
            logger.error("input_dir_not_found", path=input_dir_str)
            return {
                "success": False,
                "message": f"Input dir not found: {input_dir_str}",
            }

        files = sorted(
            f for f in input_dir.iterdir()
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
        )

        classified: list[ClassifiedDocument] = []
        for file_path in files:
            try:
                result = self._classifier.classify(file_path)
                classified.append(result)
            except Exception as e:
                logger.warning(
                    "classification_failed", file=str(file_path), error=str(e)
                )

        context["classified_documents"] = classified

        logger.info(
            "classification_complete",
            total_files=len(files),
            classified=len(classified),
        )

        return {
            "success": True,
            "message": f"Classified {len(classified)}/{len(files)} documents",
            "artifacts": {
                "classified_count": len(classified),
                "by_type": {
                    doc_type: sum(
                        1 for d in classified if d.doc_type.value == doc_type
                    )
                    for doc_type in {
                        "FORM", "DRAWING", "REPORT", "CERTIFICATE", "OTHER"
                    }
                },
            },
        }
