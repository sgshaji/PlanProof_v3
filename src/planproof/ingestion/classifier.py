"""Content-first document classifier (M1).

Classification priority: content analysis → page geometry → filename patterns.
No LLM involvement — uses text keywords, page dimensions, and text density.

# WHY content-first: Real BCC applications name all drawings
# "Plans & Drawings-Application Plans.pdf" which matches filename pattern
# for FORM (contains "Application"). Content analysis correctly distinguishes
# forms (structured questions, applicant details) from drawings (dimension
# annotations, scale references, architectural keywords).
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

# Keywords that strongly indicate a planning application FORM
_FORM_KEYWORDS: tuple[str, ...] = (
    "householder application",
    "planning permission",
    "town and country planning act",
    "certificate of ownership",
    "certificate a",
    "certificate b",
    "applicant details",
    "agent details",
    "description of proposed works",
    "pre-application advice",
    "biodiversity net gain",
    "foul sewage",
    "planning portal reference",
)

# Keywords that strongly indicate a DRAWING (site plan, floor plan, elevation)
_DRAWING_KEYWORDS: tuple[str, ...] = (
    "site plan",
    "floor plan",
    "ground floor",
    "first floor",
    "elevation",
    "section",
    "scale 1:",
    "scale:",
    "location plan",
    "block plan",
    "proposed plan",
    "existing plan",
    "north",
    "ordnance survey",
    "crown copyright",
    "os 100",
    "site boundary",
    "existing wall",
    "proposed wall",
    "dimension",
)

# Keywords for CERTIFICATE documents
_CERTIFICATE_KEYWORDS: tuple[str, ...] = (
    "lawful development",
    "certificate of lawful",
)

# Keywords for REPORT documents
_REPORT_KEYWORDS: tuple[str, ...] = (
    "design and access statement",
    "heritage statement",
    "flood risk assessment",
    "planning statement",
    "structural report",
)


class RuleBasedClassifier:
    """Classify documents using content analysis, page geometry, and filename patterns.

    Priority order:
    1. PDF content analysis (keyword matching on extracted text)
    2. Page geometry (landscape A3/A1 → DRAWING, portrait A4 with dense text → FORM)
    3. Filename patterns (fallback only)
    4. Image heuristics (aspect ratio for image files)
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
        """Classify a document by file path, prioritising content over filename."""
        filename = file_path.name
        suffix = file_path.suffix.lower()
        is_image = suffix in IMAGE_EXTENSIONS

        # --- Signal 1: Content analysis (PDFs only) ---
        has_text_layer = False
        content_type: DocumentType | None = None
        content_confidence: float = 0.0
        page_geometry_type: DocumentType | None = None

        if not is_image and suffix == ".pdf" and file_path.exists():
            has_text_layer, content_type, content_confidence, page_geometry_type = (
                self._analyse_pdf_content(file_path)
            )

        # --- Signal 2: Filename patterns (fallback) ---
        pattern_match = self._match_filename(filename)

        # --- Signal 3: Image heuristics ---
        image_type: DocumentType | None = None
        if is_image and file_path.exists():
            image_type = self._check_image_heuristics(file_path)

        # --- Combine: content wins over filename ---
        doc_type, confidence = self._combine_signals(
            content_type=content_type,
            content_confidence=content_confidence,
            page_geometry_type=page_geometry_type,
            pattern_match=pattern_match,
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

    def _analyse_pdf_content(
        self, pdf_path: Path
    ) -> tuple[bool, DocumentType | None, float, DocumentType | None]:
        """Analyse PDF text content and page geometry to determine document type.

        Returns (has_text_layer, content_type, confidence, page_geometry_type).
        """
        try:
            import pdfplumber

            with pdfplumber.open(pdf_path) as pdf:
                if not pdf.pages:
                    return False, None, 0.0, None

                full_text = ""
                total_chars = 0
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    full_text += text + "\n"
                    total_chars += len(text)

                avg_chars = total_chars / len(pdf.pages)
                has_text = avg_chars > 0

                # Page geometry: check if landscape and large (A3/A1)
                first_page = pdf.pages[0]
                pw, ph = first_page.width, first_page.height
                is_landscape = pw > ph * 1.1
                is_large = pw > 800 or ph > 800  # larger than A4

                page_geo_type: DocumentType | None = None
                if is_landscape and is_large:
                    page_geo_type = DocumentType.DRAWING
                elif not is_landscape and avg_chars >= self._high_threshold:
                    page_geo_type = DocumentType.FORM

            if not has_text:
                return False, None, 0.0, page_geo_type

            # Keyword-based content classification
            text_lower = full_text.lower()

            form_score = sum(1 for kw in _FORM_KEYWORDS if kw in text_lower)
            drawing_score = sum(1 for kw in _DRAWING_KEYWORDS if kw in text_lower)
            cert_score = sum(1 for kw in _CERTIFICATE_KEYWORDS if kw in text_lower)
            report_score = sum(1 for kw in _REPORT_KEYWORDS if kw in text_lower)

            scores = {
                DocumentType.FORM: form_score,
                DocumentType.DRAWING: drawing_score,
                DocumentType.CERTIFICATE: cert_score,
                DocumentType.REPORT: report_score,
            }

            best_type = max(scores, key=scores.get)  # type: ignore[arg-type]
            best_score = scores[best_type]

            if best_score == 0:
                # No keywords matched — fall back to text density
                if avg_chars >= self._high_threshold:
                    return True, DocumentType.FORM, 0.60, page_geo_type
                if avg_chars < self._low_threshold:
                    return True, DocumentType.DRAWING, 0.55, page_geo_type
                return True, None, 0.0, page_geo_type

            # Confidence scales with keyword match count and margin over runner-up
            runner_up = sorted(scores.values(), reverse=True)[1]
            margin = best_score - runner_up
            confidence = min(0.70 + margin * 0.05 + best_score * 0.02, 0.95)

            return True, best_type, confidence, page_geo_type

        except Exception:
            logger.warning("pdf_content_analysis_failed", path=str(pdf_path))
            return False, None, 0.0, None

    def _match_filename(self, filename: str) -> tuple[DocumentType, float] | None:
        """Match filename against configured regex patterns (first-match wins)."""
        for entry in self._patterns:
            if re.search(entry["pattern"], filename):
                return DocumentType(entry["doc_type"]), float(entry["confidence"])
        return None

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
        content_type: DocumentType | None,
        content_confidence: float,
        page_geometry_type: DocumentType | None,
        pattern_match: tuple[DocumentType, float] | None,
        image_type: DocumentType | None,
        has_text_layer: bool,
    ) -> tuple[DocumentType, float]:
        """Merge classification signals. Content wins over filename."""

        # 1. Content analysis is the strongest signal
        if content_type is not None and content_confidence >= 0.65:
            # Boost if page geometry agrees
            if page_geometry_type == content_type:
                return content_type, min(content_confidence + 0.05, 0.98)
            return content_type, content_confidence

        # 2. Page geometry (landscape A3+ → DRAWING)
        if page_geometry_type is not None and content_type is None:
            return page_geometry_type, 0.70

        # 3. Content analysis with lower confidence, boosted by filename agreement
        if content_type is not None:
            if pattern_match is not None and pattern_match[0] == content_type:
                return content_type, min(content_confidence + 0.10, 0.95)
            return content_type, content_confidence

        # 4. Filename patterns (fallback for no-content PDFs and edge cases)
        if pattern_match is not None:
            return pattern_match

        # 5. Image heuristics
        if image_type is not None:
            return image_type, 0.65

        return DocumentType.OTHER, 0.50
