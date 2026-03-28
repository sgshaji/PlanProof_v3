"""Tests for VLMSpatialExtractor — zero-shot spatial attribute extraction."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from PIL import Image

from planproof.ingestion.vlm_spatial_extractor import VLMSpatialExtractor
from planproof.pipeline.steps.vlm_extraction import VLMExtractionStep
from planproof.schemas.entities import (
    ClassifiedDocument,
    DocumentType,
    DrawingSubtype,
    EntityType,
    ExtractedEntity,
    ExtractionMethod,
)


def _mock_zeroshot_response() -> str:
    return json.dumps({
        "entities": [{
            "entity_type": "MEASUREMENT",
            "attribute": "building_height",
            "value": 7.2,
            "unit": "metres",
            "bounding_box": {"x": 450, "y": 200, "width": 80, "height": 25},
            "source_page": 1,
        }]
    })


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def test_elevation(tmp_path: Path) -> Path:
    img = Image.new("RGB", (800, 600), color="white")
    path = tmp_path / "SET_COMPLIANT_100000-compliant-ELEVATION_3.png"
    img.save(path)
    return path


@pytest.fixture
def test_site_plan(tmp_path: Path) -> Path:
    img = Image.new("RGB", (800, 600), color="white")
    path = tmp_path / "SET_COMPLIANT_100000-compliant-SITE_PLAN_1_scan.png"
    img.save(path)
    return path


@pytest.fixture
def prompts_dir(tmp_path: Path) -> Path:
    pdir = tmp_path / "prompts"
    pdir.mkdir(parents=True, exist_ok=True)

    (pdir / "spatial_zeroshot.yaml").write_text(
        "system_message: 'Extract spatial attributes from architectural drawings.'\n"
        "user_message_template: 'Analyze this {subtype} drawing and extract measurements.'\n"
        "output_schema:\n  type: object\nfew_shot_examples: []\n"
    )
    (pdir / "spatial_structured_stage1.yaml").write_text(
        "system_message: 'Stage 1 region detection.'\n"
        "user_message_template: 'Detect regions in this {subtype} drawing.'\n"
        "output_schema:\n  type: object\nfew_shot_examples: []\n"
    )
    (pdir / "spatial_structured_stage2.yaml").write_text(
        "system_message: 'Stage 2 value extraction.'\n"
        "user_message_template: 'Extract values from detected regions.'\n"
        "output_schema:\n  type: object\nfew_shot_examples: []\n"
    )
    return pdir


@pytest.fixture
def mock_openai() -> MagicMock:
    client = MagicMock()
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = _mock_zeroshot_response()
    client.chat.completions.create.return_value = response
    return client


@pytest.fixture
def extractor(prompts_dir: Path, mock_openai: MagicMock) -> VLMSpatialExtractor:
    return VLMSpatialExtractor(
        openai_client=mock_openai,
        prompts_dir=prompts_dir,
        model="gpt-4o",
        method="zeroshot",
    )


# ---------------------------------------------------------------------------
# TestSubtypeInference
# ---------------------------------------------------------------------------


class TestSubtypeInference:
    def test_elevation(self, extractor: VLMSpatialExtractor) -> None:
        result = extractor._infer_subtype(Path("SET_100-ELEVATION_3.png"))
        assert result == DrawingSubtype.ELEVATION

    def test_site_plan(self, extractor: VLMSpatialExtractor) -> None:
        result = extractor._infer_subtype(Path("SET_100-SITE_PLAN_1.pdf"))
        assert result == DrawingSubtype.SITE_PLAN

    def test_floor_plan(self, extractor: VLMSpatialExtractor) -> None:
        result = extractor._infer_subtype(Path("SET_100-FLOOR_PLAN_2.pdf"))
        assert result == DrawingSubtype.FLOOR_PLAN

    def test_other_drawing(self, extractor: VLMSpatialExtractor) -> None:
        result = extractor._infer_subtype(Path("random_file.pdf"))
        assert result == DrawingSubtype.OTHER_DRAWING


# ---------------------------------------------------------------------------
# TestZeroshotExtraction
# ---------------------------------------------------------------------------


class TestZeroshotExtraction:
    def test_extracts_entities(
        self,
        extractor: VLMSpatialExtractor,
        test_elevation: Path,
    ) -> None:
        entities = extractor.extract_spatial_attributes(test_elevation)
        assert len(entities) == 1
        assert entities[0].entity_type == EntityType.MEASUREMENT

    def test_extraction_method_is_vlm_zeroshot(
        self,
        extractor: VLMSpatialExtractor,
        test_elevation: Path,
    ) -> None:
        entities = extractor.extract_spatial_attributes(test_elevation)
        assert entities[0].extraction_method == ExtractionMethod.VLM_ZEROSHOT

    def test_bounding_box_populated(
        self,
        extractor: VLMSpatialExtractor,
        test_elevation: Path,
    ) -> None:
        entities = extractor.extract_spatial_attributes(test_elevation)
        bbox = entities[0].source_region
        assert bbox is not None
        assert bbox.x == 450
        assert bbox.y == 200
        assert bbox.width == 80
        assert bbox.height == 25

    def test_source_document_set(
        self,
        extractor: VLMSpatialExtractor,
        test_elevation: Path,
    ) -> None:
        entities = extractor.extract_spatial_attributes(test_elevation)
        assert entities[0].source_document == str(test_elevation)

    def test_openai_called_with_image(
        self,
        extractor: VLMSpatialExtractor,
        test_elevation: Path,
        mock_openai: MagicMock,
    ) -> None:
        extractor.extract_spatial_attributes(test_elevation)
        mock_openai.chat.completions.create.assert_called_once()

    def test_nonexistent_image_raises(
        self,
        extractor: VLMSpatialExtractor,
    ) -> None:
        with pytest.raises(FileNotFoundError):
            extractor.extract_spatial_attributes(Path("/nonexistent_image.png"))

    def test_malformed_response_returns_empty(
        self,
        prompts_dir: Path,
        test_elevation: Path,
    ) -> None:
        bad_client = MagicMock()
        bad_response = MagicMock()
        bad_response.choices = [MagicMock()]
        bad_response.choices[0].message.content = "not json"
        bad_client.chat.completions.create.return_value = bad_response
        extractor = VLMSpatialExtractor(
            openai_client=bad_client,
            prompts_dir=prompts_dir,
            model="gpt-4o",
            method="zeroshot",
        )
        entities = extractor.extract_spatial_attributes(test_elevation)
        assert entities == []

    def test_subtype_passed_to_prompt(
        self,
        extractor: VLMSpatialExtractor,
        test_elevation: Path,
        mock_openai: MagicMock,
    ) -> None:
        extractor.extract_spatial_attributes(test_elevation)
        call_kwargs = mock_openai.chat.completions.create.call_args[1]
        messages = call_kwargs["messages"]
        # The user message should contain the subtype value
        all_text = " ".join(
            part["text"]
            for msg in messages
            for part in (
                msg["content"] if isinstance(msg["content"], list)
                else [{"type": "text", "text": msg["content"]}]
            )
            if isinstance(part, dict) and part.get("type") == "text"
        )
        assert DrawingSubtype.ELEVATION.value in all_text


# ---------------------------------------------------------------------------
# Helpers for structured path tests
# ---------------------------------------------------------------------------


def _mock_stage1_response() -> str:
    return json.dumps({
        "regions": [{
            "attribute": "building_height",
            "region": {"x": 400, "y": 180, "width": 200, "height": 100},
        }]
    })


def _mock_stage2_response() -> str:
    return json.dumps({
        "entity_type": "MEASUREMENT",
        "attribute": "building_height",
        "value": 7.2,
        "unit": "metres",
        "bounding_box": {"x": 20, "y": 10, "width": 80, "height": 25},
    })


# ---------------------------------------------------------------------------
# Fixtures for structured path
# ---------------------------------------------------------------------------


@pytest.fixture
def structured_extractor(prompts_dir: Path) -> VLMSpatialExtractor:
    client = MagicMock()
    responses = [
        MagicMock(choices=[MagicMock(message=MagicMock(content=_mock_stage1_response()))]),
        MagicMock(choices=[MagicMock(message=MagicMock(content=_mock_stage2_response()))]),
    ]
    client.chat.completions.create.side_effect = responses
    return VLMSpatialExtractor(
        openai_client=client, prompts_dir=prompts_dir, model="gpt-4o", method="structured"
    )


# ---------------------------------------------------------------------------
# TestStructuredExtraction
# ---------------------------------------------------------------------------


class TestStructuredExtraction:
    def test_two_stage_extracts_entities(
        self,
        structured_extractor: VLMSpatialExtractor,
        test_elevation: Path,
    ) -> None:
        entities = structured_extractor.extract_spatial_attributes(test_elevation)
        assert len(entities) == 1
        assert entities[0].value == 7.2

    def test_extraction_method_is_vlm_structured(
        self,
        structured_extractor: VLMSpatialExtractor,
        test_elevation: Path,
    ) -> None:
        entities = structured_extractor.extract_spatial_attributes(test_elevation)
        assert entities[0].extraction_method == ExtractionMethod.VLM_STRUCTURED

    def test_bbox_adjusted_to_global_coords(
        self,
        structured_extractor: VLMSpatialExtractor,
        test_elevation: Path,
    ) -> None:
        # stage1 region x=400,y=180 + stage2 local bbox x=20,y=10 → global x=420,y=190
        entities = structured_extractor.extract_spatial_attributes(test_elevation)
        bbox = entities[0].source_region
        assert bbox is not None
        assert bbox.x == 420
        assert bbox.y == 190

    def test_two_api_calls_made(
        self,
        structured_extractor: VLMSpatialExtractor,
        test_elevation: Path,
    ) -> None:
        structured_extractor.extract_spatial_attributes(test_elevation)
        assert structured_extractor._client.chat.completions.create.call_count == 2

    def test_empty_regions_returns_empty(
        self,
        prompts_dir: Path,
        test_elevation: Path,
    ) -> None:
        client = MagicMock()
        client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=json.dumps({"regions": []})))]
        )
        extractor = VLMSpatialExtractor(
            openai_client=client, prompts_dir=prompts_dir, model="gpt-4o", method="structured"
        )
        entities = extractor.extract_spatial_attributes(test_elevation)
        assert entities == []


# ---------------------------------------------------------------------------
# TestVLMExtractionStep
# ---------------------------------------------------------------------------


class TestVLMExtractionStep:
    def test_execute_extracts_from_drawings(
        self, extractor: VLMSpatialExtractor, test_elevation: Path
    ) -> None:
        step = VLMExtractionStep(vlm=extractor)
        context: dict[str, Any] = {
            "classified_documents": [
                ClassifiedDocument(
                    file_path=str(test_elevation),
                    doc_type=DocumentType.DRAWING,
                    confidence=0.9,
                    has_text_layer=False,
                )
            ],
            "entities": [],
        }
        result = step.execute(context)
        assert result["success"] is True
        assert len(context["entities"]) == 1

    def test_skips_non_drawing_documents(
        self, extractor: VLMSpatialExtractor, test_elevation: Path
    ) -> None:
        step = VLMExtractionStep(vlm=extractor)
        context: dict[str, Any] = {
            "classified_documents": [
                ClassifiedDocument(
                    file_path=str(test_elevation),
                    doc_type=DocumentType.FORM,
                    confidence=0.9,
                    has_text_layer=True,
                )
            ],
            "entities": [],
        }
        result = step.execute(context)
        assert result["success"] is True
        assert len(context["entities"]) == 0

    def test_skips_drawings_with_text_layer(
        self, extractor: VLMSpatialExtractor, test_elevation: Path
    ) -> None:
        step = VLMExtractionStep(vlm=extractor)
        context: dict[str, Any] = {
            "classified_documents": [
                ClassifiedDocument(
                    file_path=str(test_elevation),
                    doc_type=DocumentType.DRAWING,
                    confidence=0.9,
                    has_text_layer=True,
                )
            ],
            "entities": [],
        }
        result = step.execute(context)
        assert result["success"] is True
        assert len(context["entities"]) == 0

    def test_appends_to_existing_entities(
        self, extractor: VLMSpatialExtractor, test_elevation: Path
    ) -> None:
        step = VLMExtractionStep(vlm=extractor)
        existing = ExtractedEntity(
            entity_type=EntityType.ADDRESS,
            value="123 Test St",
            confidence=0.9,
            source_document="form.pdf",
            extraction_method=ExtractionMethod.OCR_LLM,
            timestamp=datetime.now(UTC),
        )
        context: dict[str, Any] = {
            "classified_documents": [
                ClassifiedDocument(
                    file_path=str(test_elevation),
                    doc_type=DocumentType.DRAWING,
                    confidence=0.9,
                    has_text_layer=False,
                )
            ],
            "entities": [existing],
        }
        step.execute(context)
        assert len(context["entities"]) == 2

    def test_empty_classified_docs(self, extractor: VLMSpatialExtractor) -> None:
        step = VLMExtractionStep(vlm=extractor)
        context: dict[str, Any] = {"classified_documents": [], "entities": []}
        result = step.execute(context)
        assert result["success"] is True
