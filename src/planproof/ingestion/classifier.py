"""Rule-based document classifier (M1).

Three-signal cascade: filename patterns -> text density -> image heuristics.
No LLM involvement -- intentionally simple.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from PIL import Image

from planproof.infrastructure.logging import get_logger
from planproof.schemas.entities import ClassifiedDocument, DocumentType

logger = get_logger(__name__)

IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"})


class RuleBasedClassifier:
    """Classify documents using filename patterns, text density, and image heuristics.

    Implements the ``DocumentClassifier`` Protocol.
    """

    def __init__(self, patterns_path: Path) -> None:
        with open(patterns_path, encoding="utf-8") as f:
            config: dict[str, Any] = yaml.safe_load(f)

        self._patterns: list[dict[str, Any]] = config.get("patterns", [])
        td = config.get("text_density", {})
        self._high_threshold: int = td.get("high_threshold", 200)
        self._low_threshold: int = td.get("low_threshold", 50)
        ih = config.get("image_heuristics", {})
        self._landscape_ratio: float = ih.get("landscape_ratio", 1.2)

    def classify(self, file_path: Path) -> ClassifiedDocument:
        """Classify a document by file path.

        Parameters
        ----------
        file_path:
            Path to the document file.

        Returns
        -------
        ClassifiedDocument
            Classification result with type, confidence, and text layer flag.
        """
        filename = file_path.name
        suffix = file_path.suffix.lower()
        is_image = suffix in IMAGE_EXTENSIONS

        pattern_match = self._match_filename(filename)

        has_text_layer = False
        text_density_type: DocumentType | None = None
        if not is_image and suffix == ".pdf" and file_path.exists():
            has_text_layer, text_density_type = self._check_text_density(file_path)

        image_type: DocumentType | None = None
        if is_image and pattern_match is None and file_path.exists():
            image_type = self._check_image_heuristics(file_path)

        doc_type, confidence = self._combine_signals(
            pattern_match=pattern_match,
            text_density_type=text_density_type,
            image_type=image_type,
            has_text_layer=has_text_layer,
        )

        logger.info(
            "document_classified",
            file=filename,
            doc_type=doc_type.value,
            confidence=round(confidence, 2),
            has_text_layer=has_text_layer,
        )

        return ClassifiedDocument(
            file_path=str(file_path),
            doc_type=doc_type,
            confidence=confidence,
            has_text_layer=has_text_layer,
        )

    def _match_filename(self, filename: str) -> tuple[DocumentType, float] | None:
        """Match filename against configured regex patterns (first-match wins)."""
        for entry in self._patterns:
            if re.search(entry["pattern"], filename):
                return DocumentType(entry["doc_type"]), float(entry["confidence"])
        return None

    def _check_text_density(self, pdf_path: Path) -> tuple[bool, DocumentType | None]:
        """Extract text from a PDF and infer type from character density."""
        try:
            import pdfplumber

            with pdfplumber.open(pdf_path) as pdf:
                total_chars = 0
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    total_chars += len(text)
                if not pdf.pages:
                    return False, None
                avg_chars = total_chars / len(pdf.pages)
            if avg_chars == 0:
                return False, None
            if avg_chars >= self._high_threshold:
                return True, DocumentType.FORM
            if avg_chars < self._low_threshold:
                return True, DocumentType.DRAWING
            return True, None
        except Exception:
            logger.warning("pdfplumber_failed", path=str(pdf_path))
            return False, None

    def _check_image_heuristics(self, image_path: Path) -> DocumentType | None:
        """Use aspect ratio to guess whether an image is a drawing."""
        try:
            with Image.open(image_path) as img:
                width, height = img.size
                ratio = width / height if height > 0 else 1.0
            if ratio > self._landscape_ratio:
                return DocumentType.DRAWING
            return None
        except Exception:
            logger.warning("image_heuristic_failed", path=str(image_path))
            return None

    def _combine_signals(
        self,
        pattern_match: tuple[DocumentType, float] | None,
        text_density_type: DocumentType | None,
        image_type: DocumentType | None,
        has_text_layer: bool,
    ) -> tuple[DocumentType, float]:
        """Merge the three classification signals into a final verdict."""
        if pattern_match is not None:
            doc_type, base_conf = pattern_match
            if text_density_type is not None and text_density_type == doc_type:
                return doc_type, min(base_conf + 0.05, 1.0)
            return doc_type, base_conf
        if text_density_type is not None:
            return text_density_type, 0.75
        if image_type is not None:
            return image_type, 0.65
        return DocumentType.OTHER, 0.50
