"""Tests for VisionExtractor (GPT-4o image-based extraction)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from planproof.ingestion.vision_extractor import VisionExtractor
from planproof.schemas.entities import EntityType, ExtractionMethod


def _mock_vision_response() -> str:
    return json.dumps(
        {
            "entities": [
                {
                    "entity_type": "MEASUREMENT",
                    "attribute": "building_height",
                    "value": 7.5,
                    "unit": "metres",
                    "source_page": 1,
                }
            ]
        }
    )


@pytest.fixture
def test_image(tmp_path: Path) -> Path:
    img = Image.new("RGB", (800, 600), color="white")
    path = tmp_path / "elevation.png"
    img.save(path)
    return path


@pytest.fixture
def prompts_dir(tmp_path: Path) -> Path:
    template = tmp_path / "prompts" / "drawing_extraction.yaml"
    template.parent.mkdir(parents=True, exist_ok=True)
    template.write_text(
        "system_message: 'Extract measurements from architectural drawings.'\n"
        "user_message_template: 'Analyze this drawing and extract entities.'\n"
        "output_schema:\n  type: object\nfew_shot_examples: []\n"
    )
    return template.parent


@pytest.fixture
def mock_openai_client() -> MagicMock:
    client = MagicMock()
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = _mock_vision_response()
    client.chat.completions.create.return_value = response
    return client


@pytest.fixture
def extractor(prompts_dir: Path, mock_openai_client: MagicMock) -> VisionExtractor:
    return VisionExtractor(
        openai_client=mock_openai_client,
        prompts_dir=prompts_dir,
        model="gpt-4o",
    )


class TestVisionExtractor:
    def test_extracts_entities_from_image(
        self, extractor: VisionExtractor, test_image: Path
    ) -> None:
        entities = extractor.extract_from_image(test_image, doc_type="DRAWING")
        assert len(entities) == 1
        assert entities[0].entity_type == EntityType.MEASUREMENT

    def test_extraction_method_is_ocr_llm(
        self, extractor: VisionExtractor, test_image: Path
    ) -> None:
        entities = extractor.extract_from_image(test_image, doc_type="DRAWING")
        assert entities[0].extraction_method == ExtractionMethod.OCR_LLM

    def test_source_document_set(
        self, extractor: VisionExtractor, test_image: Path
    ) -> None:
        entities = extractor.extract_from_image(test_image, doc_type="DRAWING")
        assert entities[0].source_document == str(test_image)

    def test_openai_called_with_image(
        self,
        extractor: VisionExtractor,
        test_image: Path,
        mock_openai_client: MagicMock,
    ) -> None:
        extractor.extract_from_image(test_image, doc_type="DRAWING")
        mock_openai_client.chat.completions.create.assert_called_once()
        call_kwargs = mock_openai_client.chat.completions.create.call_args[1]
        messages = call_kwargs["messages"]
        user_msg = messages[-1]
        assert any(
            isinstance(c, dict) and c.get("type") == "image_url"
            for c in user_msg["content"]
        )

    def test_nonexistent_image_raises(self, extractor: VisionExtractor) -> None:
        with pytest.raises(FileNotFoundError):
            extractor.extract_from_image(
                Path("/nonexistent.png"), doc_type="DRAWING"
            )

    def test_malformed_response_returns_empty(self, prompts_dir: Path) -> None:
        bad_client = MagicMock()
        bad_response = MagicMock()
        bad_response.choices = [MagicMock()]
        bad_response.choices[0].message.content = "not json"
        bad_client.chat.completions.create.return_value = bad_response
        extractor = VisionExtractor(
            openai_client=bad_client, prompts_dir=prompts_dir, model="gpt-4o"
        )
        img_path = prompts_dir.parent / "test.png"
        Image.new("RGB", (100, 100)).save(img_path)
        entities = extractor.extract_from_image(img_path, doc_type="DRAWING")
        assert entities == []
