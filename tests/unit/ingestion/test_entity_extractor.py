"""Tests for LLMEntityExtractor."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from planproof.ingestion.entity_extractor import LLMEntityExtractor
from planproof.schemas.entities import EntityType, ExtractionMethod, RawTextResult


def _make_raw_text(text: str = "Height: 7.5m") -> RawTextResult:
    return RawTextResult(
        text=text, source_document="test.pdf", source_pages=[1], extraction_method="PDFPLUMBER",
    )


def _mock_llm_response() -> str:
    return json.dumps({
        "entities": [
            {"entity_type": "MEASUREMENT", "attribute": "building_height", "value": 7.5, "unit": "metres", "source_page": 1},
            {"entity_type": "ADDRESS", "attribute": "site_address", "value": "123 Test Street, Bristol, BS1 1AA", "unit": None, "source_page": 1},
        ]
    })


@pytest.fixture
def prompts_dir(tmp_path: Path) -> Path:
    form_template = tmp_path / "form_extraction.yaml"
    form_template.write_text(
        "system_message: 'Extract structured entities from planning documents.'\n"
        "user_message_template: 'Extract all entities from:\\n{text}'\n"
        "output_schema:\n  type: object\n  properties:\n    entities:\n      type: array\n"
        "few_shot_examples: []\n"
    )
    return tmp_path


@pytest.fixture
def mock_llm() -> MagicMock:
    llm = MagicMock()
    llm.complete.return_value = _mock_llm_response()
    return llm


@pytest.fixture
def extractor(prompts_dir: Path, mock_llm: MagicMock) -> LLMEntityExtractor:
    return LLMEntityExtractor(llm=mock_llm, prompts_dir=prompts_dir, model="llama-3.1-70b-versatile")


class TestLLMEntityExtractor:
    def test_extracts_entities_from_text(self, extractor: LLMEntityExtractor) -> None:
        raw = _make_raw_text("Height: 7.5m\nAddress: 123 Test Street")
        entities = extractor.extract_entities(raw)
        assert len(entities) == 2

    def test_entity_types_correct(self, extractor: LLMEntityExtractor) -> None:
        raw = _make_raw_text()
        entities = extractor.extract_entities(raw)
        types = {e.entity_type for e in entities}
        assert EntityType.MEASUREMENT in types
        assert EntityType.ADDRESS in types

    def test_extraction_method_is_ocr_llm(self, extractor: LLMEntityExtractor) -> None:
        raw = _make_raw_text()
        entities = extractor.extract_entities(raw)
        for entity in entities:
            assert entity.extraction_method == ExtractionMethod.OCR_LLM

    def test_source_document_propagated(self, extractor: LLMEntityExtractor) -> None:
        raw = _make_raw_text()
        entities = extractor.extract_entities(raw)
        for entity in entities:
            assert entity.source_document == "test.pdf"

    def test_confidence_assigned_from_defaults(self, extractor: LLMEntityExtractor) -> None:
        raw = _make_raw_text()
        entities = extractor.extract_entities(raw)
        for entity in entities:
            assert 0.0 < entity.confidence <= 1.0

    def test_llm_called_with_rendered_prompt(self, extractor: LLMEntityExtractor, mock_llm: MagicMock) -> None:
        raw = _make_raw_text("Height: 7.5m")
        extractor.extract_entities(raw)
        mock_llm.complete.assert_called_once()
        call_args = mock_llm.complete.call_args
        prompt = call_args[1].get("prompt", call_args[0][0] if call_args[0] else "")
        assert "7.5m" in prompt

    def test_malformed_json_returns_empty(self, prompts_dir: Path) -> None:
        bad_llm = MagicMock()
        bad_llm.complete.return_value = "not valid json {{"
        extractor = LLMEntityExtractor(llm=bad_llm, prompts_dir=prompts_dir, model="test")
        raw = _make_raw_text()
        entities = extractor.extract_entities(raw)
        assert entities == []

    def test_empty_entities_list_is_valid(self, prompts_dir: Path) -> None:
        empty_llm = MagicMock()
        empty_llm.complete.return_value = json.dumps({"entities": []})
        extractor = LLMEntityExtractor(llm=empty_llm, prompts_dir=prompts_dir, model="test")
        raw = _make_raw_text()
        entities = extractor.extract_entities(raw)
        assert entities == []
