"""Tests for RuleBasedClassifier."""
from __future__ import annotations

from pathlib import Path

import pytest

from planproof.ingestion.classifier import RuleBasedClassifier
from planproof.schemas.entities import DocumentType


@pytest.fixture
def classifier() -> RuleBasedClassifier:
    """Classifier using the project's default patterns."""
    patterns_path = Path("configs/classifier_patterns.yaml")
    return RuleBasedClassifier(patterns_path=patterns_path)


class TestFilenamePatterns:
    def test_form_filename(self, classifier: RuleBasedClassifier) -> None:
        result = classifier.classify(Path("test_data/FORM.pdf"))
        assert result.doc_type == DocumentType.FORM
        assert result.confidence >= 0.85

    def test_application_filename(self, classifier: RuleBasedClassifier) -> None:
        result = classifier.classify(Path("test_data/planning_application.pdf"))
        assert result.doc_type == DocumentType.FORM

    def test_elevation_filename(self, classifier: RuleBasedClassifier) -> None:
        result = classifier.classify(Path("test_data/elevation_drawing.png"))
        assert result.doc_type == DocumentType.DRAWING

    def test_site_plan_filename(self, classifier: RuleBasedClassifier) -> None:
        result = classifier.classify(Path("test_data/site_plan.pdf"))
        assert result.doc_type == DocumentType.DRAWING

    def test_floor_plan_filename(self, classifier: RuleBasedClassifier) -> None:
        result = classifier.classify(Path("test_data/floor_plan_2.pdf"))
        assert result.doc_type == DocumentType.DRAWING

    def test_certificate_filename(self, classifier: RuleBasedClassifier) -> None:
        result = classifier.classify(Path("test_data/certificate_a.pdf"))
        assert result.doc_type == DocumentType.CERTIFICATE

    def test_report_filename(self, classifier: RuleBasedClassifier) -> None:
        result = classifier.classify(Path("test_data/design_statement.pdf"))
        assert result.doc_type == DocumentType.REPORT

    def test_unknown_filename(self, classifier: RuleBasedClassifier) -> None:
        result = classifier.classify(Path("test_data/random_file.pdf"))
        assert result.doc_type == DocumentType.OTHER
        assert result.confidence <= 0.60


class TestTextLayerDetection:
    def test_image_file_has_no_text_layer(self, classifier: RuleBasedClassifier) -> None:
        result = classifier.classify(Path("test_data/elevation.png"))
        assert result.has_text_layer is False

    def test_pdf_with_text_layer(
        self, classifier: RuleBasedClassifier, tmp_path: Path
    ) -> None:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        pdf_path = tmp_path / "text_form.pdf"
        c = canvas.Canvas(str(pdf_path), pagesize=A4)
        c.drawString(100, 700, "Application for Planning Permission")
        c.drawString(100, 680, "Site Address: 123 Test Street, Bristol, BS1 1AA")
        c.drawString(100, 660, "Building Height: 7.5m")
        c.save()

        result = classifier.classify(pdf_path)
        assert result.has_text_layer is True


class TestSyntheticDataClassification:
    def test_synthetic_form(self, classifier: RuleBasedClassifier) -> None:
        result = classifier.classify(
            Path("data/synthetic/compliant/SET_COMPLIANT_42000/SET_COMPLIANT_42000-compliant-FORM.pdf")
        )
        assert result.doc_type == DocumentType.FORM

    def test_synthetic_site_plan(self, classifier: RuleBasedClassifier) -> None:
        result = classifier.classify(
            Path("data/synthetic/compliant/SET_COMPLIANT_42000/SET_COMPLIANT_42000-compliant-SITE_PLAN_1.pdf")
        )
        assert result.doc_type == DocumentType.DRAWING

    def test_synthetic_elevation(self, classifier: RuleBasedClassifier) -> None:
        result = classifier.classify(
            Path("data/synthetic/compliant/SET_COMPLIANT_42000/SET_COMPLIANT_42000-compliant-ELEVATION_3.png")
        )
        assert result.doc_type == DocumentType.DRAWING

    def test_synthetic_floor_plan(self, classifier: RuleBasedClassifier) -> None:
        result = classifier.classify(
            Path("data/synthetic/compliant/SET_COMPLIANT_42000/SET_COMPLIANT_42000-compliant-FLOOR_PLAN_2.pdf")
        )
        assert result.doc_type == DocumentType.DRAWING

    def test_synthetic_scan_is_no_text_layer(self, classifier: RuleBasedClassifier) -> None:
        result = classifier.classify(
            Path("data/synthetic/compliant/SET_COMPLIANT_42000/SET_COMPLIANT_42000-compliant-FORM_scan.png")
        )
        assert result.has_text_layer is False


class TestConfidenceBoosting:
    def test_filename_match_gives_high_confidence(
        self, classifier: RuleBasedClassifier
    ) -> None:
        result = classifier.classify(Path("test_data/FORM.pdf"))
        assert result.confidence >= 0.85

    def test_no_match_gives_low_confidence(
        self, classifier: RuleBasedClassifier
    ) -> None:
        result = classifier.classify(Path("test_data/mystery.xyz"))
        assert result.confidence <= 0.60
