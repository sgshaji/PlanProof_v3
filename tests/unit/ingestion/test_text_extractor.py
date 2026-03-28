"""Tests for PdfPlumberExtractor."""
from __future__ import annotations

from pathlib import Path

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from planproof.ingestion.text_extractor import PdfPlumberExtractor


@pytest.fixture
def text_pdf(tmp_path: Path) -> Path:
    pdf_path = tmp_path / "test_form.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    c.drawString(100, 700, "Application for Planning Permission")
    c.drawString(100, 680, "Site Address: 123 Test Street, Bristol, BS1 1AA")
    c.showPage()
    c.drawString(100, 700, "Building Height: 7.5m")
    c.drawString(100, 680, "Rear Garden Depth: 12.0m")
    c.showPage()
    c.save()
    return pdf_path


@pytest.fixture
def extractor() -> PdfPlumberExtractor:
    return PdfPlumberExtractor()


class TestPdfPlumberExtractor:
    def test_extracts_text_from_pdf(self, extractor: PdfPlumberExtractor, text_pdf: Path) -> None:
        result = extractor.extract_text(text_pdf)
        assert "Planning Permission" in result.text
        assert "123 Test Street" in result.text

    def test_preserves_page_numbers(self, extractor: PdfPlumberExtractor, text_pdf: Path) -> None:
        result = extractor.extract_text(text_pdf)
        assert result.source_pages == [1, 2]

    def test_source_document_is_set(self, extractor: PdfPlumberExtractor, text_pdf: Path) -> None:
        result = extractor.extract_text(text_pdf)
        assert result.source_document == str(text_pdf)

    def test_extraction_method_is_pdfplumber(self, extractor: PdfPlumberExtractor, text_pdf: Path) -> None:
        result = extractor.extract_text(text_pdf)
        assert result.extraction_method == "PDFPLUMBER"

    def test_second_page_content(self, extractor: PdfPlumberExtractor, text_pdf: Path) -> None:
        result = extractor.extract_text(text_pdf)
        assert "7.5m" in result.text
        assert "12.0m" in result.text

    def test_nonexistent_file_raises(self, extractor: PdfPlumberExtractor) -> None:
        with pytest.raises(FileNotFoundError):
            extractor.extract_text(Path("/nonexistent/file.pdf"))

    def test_empty_pdf(self, extractor: PdfPlumberExtractor, tmp_path: Path) -> None:
        pdf_path = tmp_path / "empty.pdf"
        c = canvas.Canvas(str(pdf_path), pagesize=A4)
        c.showPage()
        c.save()
        result = extractor.extract_text(pdf_path)
        assert result.text.strip() == ""
        assert result.source_pages == [1]
