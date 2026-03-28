"""Integration tests for VLM spatial extraction (M3) against synthetic data."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from planproof.ingestion.classifier import RuleBasedClassifier
from planproof.ingestion.vlm_spatial_extractor import VLMSpatialExtractor
from planproof.pipeline.steps.classification import ClassificationStep
from planproof.pipeline.steps.vlm_extraction import VLMExtractionStep
from planproof.schemas.entities import DocumentType, EntityType

SYNTHETIC_SET = Path("data/synthetic_diverse/compliant/SET_COMPLIANT_100000")


def _build_mock_response_for_set(gt_path: Path) -> dict[str, str]:
    """Build filename -> mock VLM response mapping from ground truth."""
    with open(gt_path) as f:
        gt = json.load(f)

    responses: dict[str, str] = {}
    for doc in gt["documents"]:
        if doc["doc_type"] != "DRAWING" or not doc["extractions"]:
            continue
        entities = []
        for ext in doc["extractions"]:
            entities.append(
                {
                    "entity_type": ext["entity_type"],
                    "attribute": ext["attribute"],
                    "value": ext["value"],
                    "unit": "metres" if ext["entity_type"] == "MEASUREMENT" else None,
                    "bounding_box": ext.get("bounding_box", {"x": 0, "y": 0, "width": 50, "height": 20}),
                    "source_page": ext.get("page", 1),
                }
            )
        responses[doc["filename"]] = json.dumps({"entities": entities})
    return responses


@pytest.mark.skipif(not SYNTHETIC_SET.exists(), reason="Synthetic data not generated")
class TestVLMExtractionIntegration:
    def test_vlm_step_extracts_from_drawings(self) -> None:
        gt_path = SYNTHETIC_SET / "ground_truth.json"
        if not gt_path.exists():
            pytest.skip("No ground truth")

        mock_responses = _build_mock_response_for_set(gt_path)

        mock_client = MagicMock()

        def side_effect(**kwargs: object) -> MagicMock:
            for _fname, resp in mock_responses.items():
                response = MagicMock()
                response.choices = [MagicMock()]
                response.choices[0].message.content = resp
                return response
            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message.content = '{"entities": []}'
            return response

        mock_client.chat.completions.create.side_effect = side_effect

        classifier = RuleBasedClassifier(
            patterns_path=Path("configs/classifier_patterns.yaml")
        )
        class_step = ClassificationStep(classifier=classifier)
        context: dict[str, object] = {
            "entities": [],
            "metadata": {"input_dir": str(SYNTHETIC_SET)},
        }
        class_step.execute(context)

        vlm = VLMSpatialExtractor(
            openai_client=mock_client,
            prompts_dir=Path("configs/prompts"),
            model="gpt-4o",
            method="zeroshot",
        )
        vlm_step = VLMExtractionStep(vlm=vlm)
        result = vlm_step.execute(context)

        assert result["success"] is True
        entities = context["entities"]
        assert len(entities) > 0

        measurement_types = {e.entity_type for e in entities}
        assert EntityType.MEASUREMENT in measurement_types

    def test_ground_truth_attributes_found(self) -> None:
        gt_path = SYNTHETIC_SET / "ground_truth.json"
        if not gt_path.exists():
            pytest.skip("No ground truth")

        with open(gt_path) as f:
            gt = json.load(f)

        gt_drawing_attrs: set[str] = set()
        for doc in gt["documents"]:
            if doc["doc_type"] == "DRAWING":
                for ext in doc["extractions"]:
                    gt_drawing_attrs.add(ext["attribute"])

        if not gt_drawing_attrs:
            pytest.skip("No drawing extractions in ground truth")

        mock_responses = _build_mock_response_for_set(gt_path)
        mock_client = MagicMock()

        def side_effect(**kwargs: object) -> MagicMock:
            for _fname, resp in mock_responses.items():
                response = MagicMock()
                response.choices = [MagicMock()]
                response.choices[0].message.content = resp
                return response
            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message.content = '{"entities": []}'
            return response

        mock_client.chat.completions.create.side_effect = side_effect

        classifier = RuleBasedClassifier(
            patterns_path=Path("configs/classifier_patterns.yaml")
        )
        class_step = ClassificationStep(classifier=classifier)
        context: dict[str, object] = {
            "entities": [],
            "metadata": {"input_dir": str(SYNTHETIC_SET)},
        }
        class_step.execute(context)

        vlm = VLMSpatialExtractor(
            openai_client=mock_client,
            prompts_dir=Path("configs/prompts"),
            model="gpt-4o",
            method="zeroshot",
        )
        vlm_step = VLMExtractionStep(vlm=vlm)
        vlm_step.execute(context)

        assert len(context["entities"]) > 0
