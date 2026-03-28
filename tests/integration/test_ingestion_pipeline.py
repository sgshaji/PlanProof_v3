"""Integration tests for the ingestion pipeline (M1 + M2).

Tests the full flow: classify documents -> extract entities from a
synthetic application set, then compare against ground truth.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from planproof.ingestion.classifier import RuleBasedClassifier
from planproof.ingestion.entity_extractor import LLMEntityExtractor
from planproof.ingestion.text_extractor import PdfPlumberExtractor
from planproof.pipeline.steps.classification import ClassificationStep
from planproof.schemas.entities import DocumentType, EntityType

SYNTHETIC_SET = Path("data/synthetic/compliant/SET_COMPLIANT_42000")


@pytest.fixture
def classifier() -> RuleBasedClassifier:
    return RuleBasedClassifier(patterns_path=Path("configs/classifier_patterns.yaml"))


class TestClassificationIntegration:
    @pytest.mark.skipif(not SYNTHETIC_SET.exists(), reason="Synthetic data not generated")
    def test_classifies_all_files_in_set(self, classifier: RuleBasedClassifier) -> None:
        files = sorted(f for f in SYNTHETIC_SET.iterdir() if f.is_file() and f.suffix.lower() in {".pdf", ".png"})
        classified = [classifier.classify(f) for f in files]
        assert len(classified) > 0
        assert all(c.confidence > 0 for c in classified)

    @pytest.mark.skipif(not SYNTHETIC_SET.exists(), reason="Synthetic data not generated")
    def test_form_classified_correctly(self, classifier: RuleBasedClassifier) -> None:
        form_path = SYNTHETIC_SET / "SET_COMPLIANT_42000-compliant-FORM.pdf"
        if not form_path.exists():
            pytest.skip("Form file not found")
        result = classifier.classify(form_path)
        assert result.doc_type == DocumentType.FORM
        assert result.has_text_layer is True

    @pytest.mark.skipif(not SYNTHETIC_SET.exists(), reason="Synthetic data not generated")
    def test_elevation_classified_as_drawing(self, classifier: RuleBasedClassifier) -> None:
        elevations = list(SYNTHETIC_SET.glob("*ELEVATION*.png"))
        if not elevations:
            pytest.skip("No elevation files")
        result = classifier.classify(elevations[0])
        assert result.doc_type == DocumentType.DRAWING
        assert result.has_text_layer is False

    @pytest.mark.skipif(not SYNTHETIC_SET.exists(), reason="Synthetic data not generated")
    def test_scan_png_has_no_text_layer(self, classifier: RuleBasedClassifier) -> None:
        scans = list(SYNTHETIC_SET.glob("*_scan.png"))
        if not scans:
            pytest.skip("No scan files")
        for scan in scans:
            result = classifier.classify(scan)
            assert result.has_text_layer is False


class TestClassificationStepIntegration:
    @pytest.mark.skipif(not SYNTHETIC_SET.exists(), reason="Synthetic data not generated")
    def test_classification_step_populates_context(self, classifier: RuleBasedClassifier) -> None:
        step = ClassificationStep(classifier=classifier)
        context = {
            "entities": [],
            "verdicts": [],
            "assessability_results": [],
            "metadata": {"input_dir": str(SYNTHETIC_SET)},
        }
        result = step.execute(context)
        assert result.get("success") is True
        assert "classified_documents" in context
        assert len(context["classified_documents"]) > 0


class TestTextExtractionWithMockedLLM:
    @pytest.mark.skipif(not SYNTHETIC_SET.exists(), reason="Synthetic data not generated")
    def test_text_path_extracts_from_form(self) -> None:
        gt_path = SYNTHETIC_SET / "ground_truth.json"
        if not gt_path.exists():
            pytest.skip("No ground truth")
        with open(gt_path) as f:
            ground_truth = json.load(f)

        gt_entities: list[dict[str, object]] = []
        for doc in ground_truth["documents"]:
            if doc["doc_type"] == "FORM":
                for ext in doc["extractions"]:
                    gt_entities.append({
                        "entity_type": ext["entity_type"],
                        "attribute": ext["attribute"],
                        "value": ext["value"],
                        "unit": "metres" if ext["entity_type"] == "MEASUREMENT" else None,
                        "source_page": ext["page"],
                    })

        mock_llm = MagicMock()
        mock_llm.complete.return_value = json.dumps({"entities": gt_entities})

        extractor = PdfPlumberExtractor()
        entity_extractor = LLMEntityExtractor(llm=mock_llm, prompts_dir=Path("configs/prompts"), model="test")

        form_path = SYNTHETIC_SET / "SET_COMPLIANT_42000-compliant-FORM.pdf"
        if not form_path.exists():
            pytest.skip("Form PDF not found")

        raw = extractor.extract_text(form_path)
        entities = entity_extractor.extract_entities(raw)

        assert len(entities) > 0
        extracted_types = {e.entity_type.value for e in entities}
        gt_types = {e["entity_type"] for e in gt_entities}
        assert extracted_types == gt_types


class TestDeterminism:
    @pytest.mark.skipif(not SYNTHETIC_SET.exists(), reason="Synthetic data not generated")
    def test_same_input_same_output(self) -> None:
        form_path = SYNTHETIC_SET / "SET_COMPLIANT_42000-compliant-FORM.pdf"
        if not form_path.exists():
            pytest.skip("Form PDF not found")

        extractor = PdfPlumberExtractor()
        result1 = extractor.extract_text(form_path)
        result2 = extractor.extract_text(form_path)

        assert result1.text == result2.text
        assert result1.source_pages == result2.source_pages
