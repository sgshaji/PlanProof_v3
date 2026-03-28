"""PDF text extraction via pdfplumber.

Implements the ``OCRExtractor`` Protocol — extracts raw text from
text-layer PDFs, preserving page boundaries.
"""
from __future__ import annotations

from pathlib import Path

import pdfplumber

from planproof.infrastructure.logging import get_logger
from planproof.schemas.entities import RawTextResult

logger = get_logger(__name__)


class PdfPlumberExtractor:
    """Extract text from PDFs using pdfplumber.

    Implements the ``OCRExtractor`` Protocol.
    """

    def extract_text(self, document: Path) -> RawTextResult:
        if not document.exists():
            msg = f"Document not found: {document}"
            raise FileNotFoundError(msg)

        page_texts: list[str] = []
        page_numbers: list[int] = []

        with pdfplumber.open(document) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                page_texts.append(text)
                page_numbers.append(i)

        full_text = "\n\n".join(page_texts)

        logger.info(
            "text_extracted",
            document=str(document),
            pages=len(page_numbers),
            chars=len(full_text),
        )

        return RawTextResult(
            text=full_text,
            source_document=str(document),
            source_pages=page_numbers,
            extraction_method="PDFPLUMBER",
        )
