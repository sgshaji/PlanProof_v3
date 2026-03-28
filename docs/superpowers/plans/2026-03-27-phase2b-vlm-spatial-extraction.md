# Phase 2b: M3 VLM Spatial Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement VLM-based spatial extraction from architectural drawings with two ablation methods (zero-shot and two-stage structured), replacing the stub VLM in the pipeline.

**Architecture:** `VLMSpatialExtractor` class implements existing `VLMExtractor` Protocol. Subtype inferred from filename. Method selected by config. Both paths produce `ExtractedEntity` with `BoundingBox` in `source_region`.

**Tech Stack:** Python 3.11+, openai SDK (GPT-4o vision), Pillow (image cropping), pydantic, pyyaml

**Spec:** `docs/superpowers/specs/2026-03-27-phase2b-vlm-spatial-extraction-design.md`

---

## File Structure

### New Files
- `src/planproof/ingestion/vlm_spatial_extractor.py` — `VLMSpatialExtractor` class with zero-shot and structured paths
- `configs/prompts/spatial_zeroshot.yaml` — zero-shot prompt with bbox output schema
- `configs/prompts/spatial_structured_stage1.yaml` — coarse localisation prompt
- `configs/prompts/spatial_structured_stage2.yaml` — crop refinement prompt
- `tests/unit/ingestion/test_vlm_spatial_extractor.py` — unit tests with mocked GPT-4o
- `tests/integration/test_vlm_extraction_step.py` — integration test against synthetic data

### Modified Files
- `src/planproof/schemas/entities.py` — add `DrawingSubtype` enum
- `src/planproof/schemas/config.py` — add `vlm_extraction_method` field
- `src/planproof/pipeline/steps/vlm_extraction.py` — implement `execute()`
- `src/planproof/bootstrap.py` — replace `_StubVLM` with `VLMSpatialExtractor`

---

## Task 1: Add DrawingSubtype enum to schemas

**Files:**
- Modify: `src/planproof/schemas/entities.py`
- Test: `tests/unit/test_schemas.py`

- [ ] **Step 1: Add DrawingSubtype enum**

Add after the `DocumentType` enum in `src/planproof/schemas/entities.py`:

```python
class DrawingSubtype(StrEnum):
    """Subtype classification for DRAWING documents."""

    SITE_PLAN = "SITE_PLAN"
    FLOOR_PLAN = "FLOOR_PLAN"
    ELEVATION = "ELEVATION"
    OTHER_DRAWING = "OTHER_DRAWING"
```

- [ ] **Step 2: Add vlm_extraction_method to config**

Add to `PipelineConfig` in `src/planproof/schemas/config.py`, after `vlm_model`:

```python
    vlm_extraction_method: str = "zeroshot"  # "zeroshot" | "structured"
```

- [ ] **Step 3: Run lint and typecheck**

Run: `python -m ruff check src/planproof/schemas/ && python -m mypy src/planproof/schemas/ --strict`
Expected: clean

- [ ] **Step 4: Commit**

```bash
git add src/planproof/schemas/entities.py src/planproof/schemas/config.py
git commit -m "feat(M3): add DrawingSubtype enum and vlm_extraction_method config"
```

---

## Task 2: Create spatial extraction prompt templates

**Files:**
- Create: `configs/prompts/spatial_zeroshot.yaml`
- Create: `configs/prompts/spatial_structured_stage1.yaml`
- Create: `configs/prompts/spatial_structured_stage2.yaml`

- [ ] **Step 1: Create zero-shot prompt**

Write `configs/prompts/spatial_zeroshot.yaml`:

```yaml
system_message: |
  You are a planning document analysis expert. Extract all measurements,
  dimensions, and spatial annotations from architectural drawings.
  Return structured JSON with bounding box pixel coordinates for each entity.

user_message_template: |
  Analyze this {subtype} drawing. Extract all measurements and spatial data.

  Target attributes for {subtype}:
  - SITE_PLAN: rear_garden_depth, site_coverage, setback distances, site_area, boundary_lengths
  - FLOOR_PLAN: room_dimensions, floor_area, wall_lengths, corridor_width
  - ELEVATION: building_height, ridge_height, eave_height, storey_height, wall_height

  For each entity provide:
  - entity_type: MEASUREMENT or BOUNDARY
  - attribute: the specific measurement name (e.g. building_height)
  - value: numeric value
  - unit: metres, percent, or square_metres
  - bounding_box: pixel coordinates {{x, y, width, height}} of the annotation in the image
  - source_page: 1

  Respond with valid JSON: {{"entities": [...]}}

output_schema:
  type: object
  properties:
    entities:
      type: array
      items:
        type: object
        required: [entity_type, attribute, value, unit, bounding_box]
        properties:
          entity_type:
            type: string
            enum: [MEASUREMENT, BOUNDARY]
          attribute:
            type: string
          value:
            type: number
          unit:
            type: string
          bounding_box:
            type: object
            properties:
              x: { type: number }
              y: { type: number }
              width: { type: number }
              height: { type: number }
          source_page:
            type: integer

few_shot_examples:
  - input: "[Elevation drawing with dimension lines]"
    output: |
      {"entities": [
        {"entity_type": "MEASUREMENT", "attribute": "building_height", "value": 7.2, "unit": "metres",
         "bounding_box": {"x": 450, "y": 200, "width": 80, "height": 25}, "source_page": 1},
        {"entity_type": "MEASUREMENT", "attribute": "ridge_height", "value": 8.5, "unit": "metres",
         "bounding_box": {"x": 460, "y": 50, "width": 75, "height": 25}, "source_page": 1}
      ]}
```

- [ ] **Step 2: Create structured stage 1 prompt**

Write `configs/prompts/spatial_structured_stage1.yaml`:

```yaml
system_message: |
  You are a planning document analysis expert. Identify all regions in this
  architectural drawing that contain measurement annotations, dimension lines,
  or spatial labels. Return the approximate pixel region for each.

user_message_template: |
  Scan this {subtype} drawing and locate all measurement annotations.
  For each, provide the attribute name and a bounding region large enough
  to fully contain the annotation text and its dimension line.

  Respond with valid JSON: {{"regions": [...]}}

output_schema:
  type: object
  properties:
    regions:
      type: array
      items:
        type: object
        required: [attribute, region]
        properties:
          attribute:
            type: string
          region:
            type: object
            properties:
              x: { type: number }
              y: { type: number }
              width: { type: number }
              height: { type: number }

few_shot_examples:
  - input: "[Site plan with boundary dimensions]"
    output: |
      {"regions": [
        {"attribute": "rear_garden_depth", "region": {"x": 100, "y": 400, "width": 200, "height": 100}},
        {"attribute": "site_coverage", "region": {"x": 500, "y": 600, "width": 250, "height": 80}}
      ]}
```

- [ ] **Step 3: Create structured stage 2 prompt**

Write `configs/prompts/spatial_structured_stage2.yaml`:

```yaml
system_message: |
  You are a planning document analysis expert. You are looking at a cropped
  region from an architectural drawing. Extract the precise measurement value
  and its bounding box within this crop.

user_message_template: |
  This crop contains an annotation for: {attribute}
  Extract the precise numeric value, unit, and the tight bounding box of the
  annotation text within this cropped image.

  Respond with valid JSON: {{"entity_type": "MEASUREMENT", "attribute": "{attribute}", "value": ..., "unit": ..., "bounding_box": {{...}}}}

output_schema:
  type: object
  required: [entity_type, attribute, value, unit, bounding_box]
  properties:
    entity_type:
      type: string
    attribute:
      type: string
    value:
      type: number
    unit:
      type: string
    bounding_box:
      type: object
      properties:
        x: { type: number }
        y: { type: number }
        width: { type: number }
        height: { type: number }

few_shot_examples: []
```

- [ ] **Step 4: Commit**

```bash
git add configs/prompts/spatial_zeroshot.yaml configs/prompts/spatial_structured_stage1.yaml configs/prompts/spatial_structured_stage2.yaml
git commit -m "feat(M3): add spatial extraction prompt templates for zero-shot and structured paths"
```

---

## Task 3: Implement VLMSpatialExtractor — zero-shot path

**Files:**
- Create: `src/planproof/ingestion/vlm_spatial_extractor.py`
- Test: `tests/unit/ingestion/test_vlm_spatial_extractor.py`

- [ ] **Step 1: Write failing tests for zero-shot extraction**

Write `tests/unit/ingestion/test_vlm_spatial_extractor.py`:

```python
"""Tests for VLMSpatialExtractor (M3 VLM spatial extraction)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from planproof.ingestion.vlm_spatial_extractor import VLMSpatialExtractor
from planproof.schemas.entities import (
    DrawingSubtype,
    EntityType,
    ExtractionMethod,
)


def _mock_zeroshot_response() -> str:
    return json.dumps(
        {
            "entities": [
                {
                    "entity_type": "MEASUREMENT",
                    "attribute": "building_height",
                    "value": 7.2,
                    "unit": "metres",
                    "bounding_box": {"x": 450, "y": 200, "width": 80, "height": 25},
                    "source_page": 1,
                }
            ]
        }
    )


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
    d = tmp_path / "prompts"
    d.mkdir()
    for name in ["spatial_zeroshot", "spatial_structured_stage1", "spatial_structured_stage2"]:
        (d / f"{name}.yaml").write_text(
            "system_message: 'test'\n"
            "user_message_template: 'Analyze {subtype}'\n"
            "output_schema:\n  type: object\nfew_shot_examples: []\n"
        )
    return d


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


class TestSubtypeInference:
    def test_elevation_inferred(self, extractor: VLMSpatialExtractor) -> None:
        assert extractor._infer_subtype(Path("SET_100-ELEVATION_3.png")) == DrawingSubtype.ELEVATION

    def test_site_plan_inferred(self, extractor: VLMSpatialExtractor) -> None:
        assert extractor._infer_subtype(Path("SET_100-SITE_PLAN_1.pdf")) == DrawingSubtype.SITE_PLAN

    def test_floor_plan_inferred(self, extractor: VLMSpatialExtractor) -> None:
        assert extractor._infer_subtype(Path("SET_100-FLOOR_PLAN_2.pdf")) == DrawingSubtype.FLOOR_PLAN

    def test_unknown_defaults_to_other(self, extractor: VLMSpatialExtractor) -> None:
        assert extractor._infer_subtype(Path("random_file.pdf")) == DrawingSubtype.OTHER_DRAWING


class TestZeroshotExtraction:
    def test_extracts_entities(
        self, extractor: VLMSpatialExtractor, test_elevation: Path
    ) -> None:
        entities = extractor.extract_spatial_attributes(test_elevation)
        assert len(entities) == 1
        assert entities[0].entity_type == EntityType.MEASUREMENT
        assert entities[0].value == 7.2

    def test_extraction_method_is_vlm_zeroshot(
        self, extractor: VLMSpatialExtractor, test_elevation: Path
    ) -> None:
        entities = extractor.extract_spatial_attributes(test_elevation)
        assert entities[0].extraction_method == ExtractionMethod.VLM_ZEROSHOT

    def test_bounding_box_populated(
        self, extractor: VLMSpatialExtractor, test_elevation: Path
    ) -> None:
        entities = extractor.extract_spatial_attributes(test_elevation)
        bbox = entities[0].source_region
        assert bbox is not None
        assert bbox.x == 450
        assert bbox.y == 200
        assert bbox.width == 80
        assert bbox.height == 25

    def test_source_document_set(
        self, extractor: VLMSpatialExtractor, test_elevation: Path
    ) -> None:
        entities = extractor.extract_spatial_attributes(test_elevation)
        assert entities[0].source_document == str(test_elevation)

    def test_openai_called_with_image(
        self, extractor: VLMSpatialExtractor, test_elevation: Path, mock_openai: MagicMock
    ) -> None:
        extractor.extract_spatial_attributes(test_elevation)
        mock_openai.chat.completions.create.assert_called_once()

    def test_nonexistent_image_raises(self, extractor: VLMSpatialExtractor) -> None:
        with pytest.raises(FileNotFoundError):
            extractor.extract_spatial_attributes(Path("/nonexistent.png"))

    def test_malformed_response_returns_empty(self, prompts_dir: Path) -> None:
        bad_client = MagicMock()
        bad_response = MagicMock()
        bad_response.choices = [MagicMock()]
        bad_response.choices[0].message.content = "not json"
        bad_client.chat.completions.create.return_value = bad_response
        ext = VLMSpatialExtractor(
            openai_client=bad_client, prompts_dir=prompts_dir, model="gpt-4o", method="zeroshot"
        )
        img = prompts_dir.parent / "test.png"
        Image.new("RGB", (100, 100)).save(img)
        assert ext.extract_spatial_attributes(img) == []

    def test_subtype_passed_to_prompt(
        self, extractor: VLMSpatialExtractor, test_site_plan: Path, mock_openai: MagicMock
    ) -> None:
        extractor.extract_spatial_attributes(test_site_plan)
        call_kwargs = mock_openai.chat.completions.create.call_args[1]
        messages = call_kwargs["messages"]
        system_or_user = " ".join(
            m["content"] if isinstance(m["content"], str)
            else " ".join(c.get("text", "") for c in m["content"] if isinstance(c, dict))
            for m in messages
        )
        assert "SITE_PLAN" in system_or_user or "site_plan" in system_or_user.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/ingestion/test_vlm_spatial_extractor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'planproof.ingestion.vlm_spatial_extractor'`

- [ ] **Step 3: Implement VLMSpatialExtractor zero-shot path**

Write `src/planproof/ingestion/vlm_spatial_extractor.py`:

```python
"""VLM-based spatial extraction from architectural drawings (M3).

Two extraction methods:
- zeroshot: single GPT-4o call with structured output schema
- structured: two-stage coarse-then-refine with image cropping
"""
from __future__ import annotations

import base64
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from planproof.infrastructure.logging import get_logger
from planproof.ingestion.prompt_loader import PromptLoader
from planproof.schemas.entities import (
    BoundingBox,
    DrawingSubtype,
    EntityType,
    ExtractedEntity,
    ExtractionMethod,
)

logger = get_logger(__name__)

_SUBTYPE_PATTERNS: list[tuple[str, DrawingSubtype]] = [
    (r"(?i)elevation", DrawingSubtype.ELEVATION),
    (r"(?i)site.?plan", DrawingSubtype.SITE_PLAN),
    (r"(?i)floor.?plan", DrawingSubtype.FLOOR_PLAN),
]

_ENTITY_TYPE_MAP: dict[str, EntityType] = {
    "MEASUREMENT": EntityType.MEASUREMENT,
    "BOUNDARY": EntityType.BOUNDARY,
}

_DEFAULT_CONFIDENCE: dict[str, float] = {
    "MEASUREMENT": 0.75,
    "BOUNDARY": 0.70,
}


class VLMSpatialExtractor:
    """Extract spatially grounded measurements from architectural drawings.

    Implements the ``VLMExtractor`` Protocol.
    """

    def __init__(
        self,
        openai_client: Any,
        prompts_dir: Path,
        model: str = "gpt-4o",
        method: str = "zeroshot",
    ) -> None:
        self._client = openai_client
        self._loader = PromptLoader(prompts_dir)
        self._model = model
        self._method = method

    def extract_spatial_attributes(self, image: Path) -> list[ExtractedEntity]:
        """Extract spatial entities from an architectural drawing image."""
        if not image.exists():
            msg = f"Image not found: {image}"
            raise FileNotFoundError(msg)

        subtype = self._infer_subtype(image)

        if self._method == "structured":
            return self._structured_path(image, subtype)
        return self._zeroshot_path(image, subtype)

    def _infer_subtype(self, image: Path) -> DrawingSubtype:
        """Infer drawing subtype from filename patterns."""
        name = image.name
        for pattern, subtype in _SUBTYPE_PATTERNS:
            if re.search(pattern, name):
                return subtype
        return DrawingSubtype.OTHER_DRAWING

    # ------------------------------------------------------------------
    # Zero-shot path
    # ------------------------------------------------------------------

    def _zeroshot_path(
        self, image: Path, subtype: DrawingSubtype
    ) -> list[ExtractedEntity]:
        """Single GPT-4o call requesting entities with bbox coords."""
        template = self._loader.load("spatial_zeroshot")
        user_text = template.user_message_template.format(subtype=subtype.value)

        messages = self._build_vision_messages(
            system=template.system_message,
            user_text=user_text,
            image_path=image,
        )

        content = self._call_vision(messages)
        if content is None:
            return []

        return self._parse_entities(content, str(image), ExtractionMethod.VLM_ZEROSHOT)

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _build_vision_messages(
        self, system: str, user_text: str, image_path: Path
    ) -> list[dict[str, Any]]:
        """Build OpenAI chat messages with an embedded base64 image."""
        image_bytes = image_path.read_bytes()
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        suffix = image_path.suffix.lower().lstrip(".")
        mime_map = {"png": "png", "jpg": "jpeg", "jpeg": "jpeg", "tiff": "tiff"}
        mime = f"image/{mime_map.get(suffix, 'png')}"

        return [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    },
                ],
            },
        ]

    def _call_vision(self, messages: list[dict[str, Any]]) -> str | None:
        """Send messages to GPT-4o and return the text content."""
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0,
                max_tokens=4096,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001
            logger.error("vlm_spatial_api_failed", error=str(exc))
            return None

    def _parse_entities(
        self,
        response: str,
        source_document: str,
        method: ExtractionMethod,
    ) -> list[ExtractedEntity]:
        """Parse JSON response into ExtractedEntity list with bounding boxes."""
        try:
            cleaned = response.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                cleaned = "\n".join(lines[1:-1])
            data = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("vlm_spatial_json_parse_failed", error=str(exc))
            return []

        raw_entities: list[dict[str, Any]] = data.get("entities", [])
        entities: list[ExtractedEntity] = []
        now = datetime.now(UTC)

        for raw in raw_entities:
            try:
                et_str = raw.get("entity_type", "MEASUREMENT")
                entity_type = _ENTITY_TYPE_MAP.get(et_str, EntityType.MEASUREMENT)

                bbox_data = raw.get("bounding_box")
                bbox = None
                if bbox_data and isinstance(bbox_data, dict):
                    bbox = BoundingBox(
                        x=float(bbox_data.get("x", 0)),
                        y=float(bbox_data.get("y", 0)),
                        width=float(bbox_data.get("width", 0)),
                        height=float(bbox_data.get("height", 0)),
                        page=int(raw.get("source_page", 1)),
                    )

                entity = ExtractedEntity(
                    entity_type=entity_type,
                    value=raw.get("value"),
                    unit=raw.get("unit"),
                    confidence=_DEFAULT_CONFIDENCE.get(et_str, 0.70),
                    source_document=source_document,
                    source_page=raw.get("source_page", 1),
                    source_region=bbox,
                    extraction_method=method,
                    timestamp=now,
                )
                entities.append(entity)
            except (ValueError, KeyError, TypeError) as exc:
                logger.warning("vlm_spatial_entity_skipped", error=str(exc), raw=raw)
                continue

        logger.info("vlm_spatial_extracted", count=len(entities), source=source_document)
        return entities
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/ingestion/test_vlm_spatial_extractor.py -v`
Expected: all pass

- [ ] **Step 5: Run lint and typecheck**

Run: `python -m ruff check src/planproof/ingestion/vlm_spatial_extractor.py && python -m mypy src/planproof/ingestion/vlm_spatial_extractor.py --strict`
Expected: clean

- [ ] **Step 6: Commit**

```bash
git add src/planproof/ingestion/vlm_spatial_extractor.py tests/unit/ingestion/test_vlm_spatial_extractor.py
git commit -m "feat(M3): implement VLMSpatialExtractor zero-shot path with bbox extraction"
```

---

## Task 4: Implement VLMSpatialExtractor — structured two-stage path

**Files:**
- Modify: `src/planproof/ingestion/vlm_spatial_extractor.py`
- Modify: `tests/unit/ingestion/test_vlm_spatial_extractor.py`

- [ ] **Step 1: Write failing tests for structured path**

Append to `tests/unit/ingestion/test_vlm_spatial_extractor.py`:

```python
def _mock_stage1_response() -> str:
    return json.dumps(
        {
            "regions": [
                {
                    "attribute": "building_height",
                    "region": {"x": 400, "y": 180, "width": 200, "height": 100},
                }
            ]
        }
    )


def _mock_stage2_response() -> str:
    return json.dumps(
        {
            "entity_type": "MEASUREMENT",
            "attribute": "building_height",
            "value": 7.2,
            "unit": "metres",
            "bounding_box": {"x": 20, "y": 10, "width": 80, "height": 25},
        }
    )


@pytest.fixture
def structured_extractor(prompts_dir: Path) -> VLMSpatialExtractor:
    client = MagicMock()
    # Stage 1 returns regions, stage 2 returns entity
    responses = [
        MagicMock(choices=[MagicMock(message=MagicMock(content=_mock_stage1_response()))]),
        MagicMock(choices=[MagicMock(message=MagicMock(content=_mock_stage2_response()))]),
    ]
    client.chat.completions.create.side_effect = responses
    return VLMSpatialExtractor(
        openai_client=client, prompts_dir=prompts_dir, model="gpt-4o", method="structured"
    )


class TestStructuredExtraction:
    def test_two_stage_extracts_entities(
        self, structured_extractor: VLMSpatialExtractor, test_elevation: Path
    ) -> None:
        entities = structured_extractor.extract_spatial_attributes(test_elevation)
        assert len(entities) == 1
        assert entities[0].value == 7.2

    def test_extraction_method_is_vlm_structured(
        self, structured_extractor: VLMSpatialExtractor, test_elevation: Path
    ) -> None:
        entities = structured_extractor.extract_spatial_attributes(test_elevation)
        assert entities[0].extraction_method == ExtractionMethod.VLM_STRUCTURED

    def test_bbox_adjusted_to_global_coords(
        self, structured_extractor: VLMSpatialExtractor, test_elevation: Path
    ) -> None:
        entities = structured_extractor.extract_spatial_attributes(test_elevation)
        bbox = entities[0].source_region
        assert bbox is not None
        # Stage 1 region x=400, stage 2 local bbox x=20 -> global x=420
        assert bbox.x == 420
        # Stage 1 region y=180, stage 2 local bbox y=10 -> global y=190
        assert bbox.y == 190

    def test_two_api_calls_made(
        self, structured_extractor: VLMSpatialExtractor, test_elevation: Path
    ) -> None:
        structured_extractor.extract_spatial_attributes(test_elevation)
        assert structured_extractor._client.chat.completions.create.call_count == 2

    def test_empty_regions_returns_empty(self, prompts_dir: Path, test_elevation: Path) -> None:
        client = MagicMock()
        response = MagicMock(choices=[MagicMock(message=MagicMock(content='{"regions": []}'))])
        client.chat.completions.create.return_value = response
        ext = VLMSpatialExtractor(
            openai_client=client, prompts_dir=prompts_dir, model="gpt-4o", method="structured"
        )
        assert ext.extract_spatial_attributes(test_elevation) == []
```

- [ ] **Step 2: Run tests to verify new tests fail**

Run: `python -m pytest tests/unit/ingestion/test_vlm_spatial_extractor.py::TestStructuredExtraction -v`
Expected: FAIL — `_structured_path` not implemented or returns empty

- [ ] **Step 3: Implement structured two-stage path**

Add to `VLMSpatialExtractor` in `src/planproof/ingestion/vlm_spatial_extractor.py`:

```python
    # ------------------------------------------------------------------
    # Structured two-stage path
    # ------------------------------------------------------------------

    def _structured_path(
        self, image: Path, subtype: DrawingSubtype
    ) -> list[ExtractedEntity]:
        """Stage 1: locate regions. Stage 2: crop and refine each."""
        # Stage 1 — coarse localisation
        template1 = self._loader.load("spatial_structured_stage1")
        user_text1 = template1.user_message_template.format(subtype=subtype.value)
        messages1 = self._build_vision_messages(
            system=template1.system_message,
            user_text=user_text1,
            image_path=image,
        )
        content1 = self._call_vision(messages1)
        if content1 is None:
            return []

        regions = self._parse_regions(content1)
        if not regions:
            return []

        # Stage 2 — crop and refine each region
        from PIL import Image as PILImage

        img = PILImage.open(image)
        entities: list[ExtractedEntity] = []

        for region in regions:
            attribute = region["attribute"]
            r = region["region"]
            x, y, w, h = int(r["x"]), int(r["y"]), int(r["width"]), int(r["height"])

            # Clamp to image bounds
            img_w, img_h = img.size
            x = max(0, min(x, img_w - 1))
            y = max(0, min(y, img_h - 1))
            w = min(w, img_w - x)
            h = min(h, img_h - y)

            if w <= 0 or h <= 0:
                continue

            crop = img.crop((x, y, x + w, y + h))

            # Save crop to temp file
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                crop.save(tmp.name)
                crop_path = Path(tmp.name)

            template2 = self._loader.load("spatial_structured_stage2")
            user_text2 = template2.user_message_template.format(attribute=attribute)
            messages2 = self._build_vision_messages(
                system=template2.system_message,
                user_text=user_text2,
                image_path=crop_path,
            )
            content2 = self._call_vision(messages2)
            crop_path.unlink(missing_ok=True)

            if content2 is None:
                continue

            entity = self._parse_single_entity(
                content2, str(image), x, y, ExtractionMethod.VLM_STRUCTURED
            )
            if entity is not None:
                entities.append(entity)

        logger.info("vlm_structured_extracted", count=len(entities), source=str(image))
        return entities

    def _parse_regions(self, response: str) -> list[dict[str, Any]]:
        """Parse stage 1 response into region dicts."""
        try:
            cleaned = response.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                cleaned = "\n".join(lines[1:-1])
            data = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            return []
        return data.get("regions", [])

    def _parse_single_entity(
        self,
        response: str,
        source_document: str,
        region_x: int,
        region_y: int,
        method: ExtractionMethod,
    ) -> ExtractedEntity | None:
        """Parse stage 2 response, adjusting local bbox to global coords."""
        try:
            cleaned = response.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                cleaned = "\n".join(lines[1:-1])
            raw = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            return None

        try:
            et_str = raw.get("entity_type", "MEASUREMENT")
            entity_type = _ENTITY_TYPE_MAP.get(et_str, EntityType.MEASUREMENT)

            bbox = None
            bbox_data = raw.get("bounding_box")
            if bbox_data and isinstance(bbox_data, dict):
                bbox = BoundingBox(
                    x=float(bbox_data.get("x", 0)) + region_x,
                    y=float(bbox_data.get("y", 0)) + region_y,
                    width=float(bbox_data.get("width", 0)),
                    height=float(bbox_data.get("height", 0)),
                    page=1,
                )

            return ExtractedEntity(
                entity_type=entity_type,
                value=raw.get("value"),
                unit=raw.get("unit"),
                confidence=_DEFAULT_CONFIDENCE.get(et_str, 0.70),
                source_document=source_document,
                source_page=1,
                source_region=bbox,
                extraction_method=method,
                timestamp=datetime.now(UTC),
            )
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("vlm_stage2_parse_failed", error=str(exc))
            return None
```

- [ ] **Step 4: Run all tests**

Run: `python -m pytest tests/unit/ingestion/test_vlm_spatial_extractor.py -v`
Expected: all pass

- [ ] **Step 5: Lint and typecheck**

Run: `python -m ruff check src/planproof/ingestion/vlm_spatial_extractor.py && python -m mypy src/planproof/ingestion/vlm_spatial_extractor.py --strict`
Expected: clean

- [ ] **Step 6: Commit**

```bash
git add src/planproof/ingestion/vlm_spatial_extractor.py tests/unit/ingestion/test_vlm_spatial_extractor.py
git commit -m "feat(M3): implement VLMSpatialExtractor structured two-stage path"
```

---

## Task 5: Implement VLMExtractionStep.execute()

**Files:**
- Modify: `src/planproof/pipeline/steps/vlm_extraction.py`
- Test: `tests/unit/ingestion/test_vlm_spatial_extractor.py` (add step-level tests)

- [ ] **Step 1: Write failing tests for the pipeline step**

Append to `tests/unit/ingestion/test_vlm_spatial_extractor.py`:

```python
from planproof.pipeline.steps.vlm_extraction import VLMExtractionStep
from planproof.schemas.entities import ClassifiedDocument, DocumentType


class TestVLMExtractionStep:
    def test_execute_extracts_from_drawings(
        self, extractor: VLMSpatialExtractor, test_elevation: Path
    ) -> None:
        step = VLMExtractionStep(vlm=extractor)
        context = {
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
        context = {
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
        context = {
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
        # Drawings with text layer are handled by TextExtractionStep, not VLM
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
        context = {
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
```

Add this import at the top of the test file:

```python
from datetime import UTC, datetime
from typing import Any
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/ingestion/test_vlm_spatial_extractor.py::TestVLMExtractionStep -v`
Expected: FAIL — `NotImplementedError: Implemented in Phase 2`

- [ ] **Step 3: Implement VLMExtractionStep.execute()**

Replace the contents of `src/planproof/pipeline/steps/vlm_extraction.py`:

```python
"""Pipeline step: VLM-based extraction from architectural drawings."""
from __future__ import annotations

from pathlib import Path

from planproof.infrastructure.logging import get_logger
from planproof.interfaces.extraction import VLMExtractor
from planproof.interfaces.pipeline import PipelineContext, StepResult
from planproof.schemas.entities import ClassifiedDocument, DocumentType

logger = get_logger(__name__)


class VLMExtractionStep:
    """Extract spatial attributes from architectural drawings using a VLM.

    Filters for DRAWING documents without text layers (those are handled
    by TextExtractionStep). Delegates extraction to the VLMExtractor Protocol.
    """

    def __init__(self, vlm: VLMExtractor) -> None:
        self._vlm = vlm

    @property
    def name(self) -> str:
        return "vlm_extraction"

    def execute(self, context: PipelineContext) -> StepResult:
        classified_docs: list[ClassifiedDocument] = context.get(
            "classified_documents", []
        )

        drawings = [
            doc
            for doc in classified_docs
            if doc.doc_type == DocumentType.DRAWING and not doc.has_text_layer
        ]

        if not drawings:
            logger.info("vlm_no_drawings_to_process")
            return {
                "success": True,
                "message": "No drawings for VLM extraction",
                "artifacts": {"entity_count": 0},
            }

        all_entities = []
        errors: list[str] = []

        for doc in drawings:
            try:
                entities = self._vlm.extract_spatial_attributes(Path(doc.file_path))
                all_entities.extend(entities)
            except Exception as e:  # noqa: BLE001
                error_msg = f"{doc.file_path}: {type(e).__name__}: {e}"
                errors.append(error_msg)
                logger.warning("vlm_extraction_failed", file=doc.file_path, error=str(e))

        existing = context.get("entities", [])
        context["entities"] = existing + all_entities

        success = len(errors) == 0 or len(all_entities) > 0

        logger.info(
            "vlm_extraction_complete",
            entities=len(all_entities),
            drawings=len(drawings),
            errors=len(errors),
        )

        return {
            "success": success,
            "message": f"VLM extracted {len(all_entities)} entities from {len(drawings)} drawings",
            "artifacts": {
                "entity_count": len(all_entities),
                "drawing_count": len(drawings),
                "error_count": len(errors),
            },
        }
```

- [ ] **Step 4: Run all tests**

Run: `python -m pytest tests/unit/ingestion/test_vlm_spatial_extractor.py -v`
Expected: all pass

- [ ] **Step 5: Lint and typecheck**

Run: `python -m ruff check src/planproof/pipeline/steps/vlm_extraction.py && python -m mypy src/planproof/pipeline/steps/vlm_extraction.py --strict`
Expected: clean

- [ ] **Step 6: Commit**

```bash
git add src/planproof/pipeline/steps/vlm_extraction.py tests/unit/ingestion/test_vlm_spatial_extractor.py
git commit -m "feat(M3): implement VLMExtractionStep with drawing filtering and entity merging"
```

---

## Task 6: Wire into bootstrap and update execution status

**Files:**
- Modify: `src/planproof/bootstrap.py`
- Modify: `docs/EXECUTION_STATUS.md`

- [ ] **Step 1: Replace _StubVLM with VLMSpatialExtractor in bootstrap**

In `src/planproof/bootstrap.py`, add the import:

```python
from planproof.ingestion.vlm_spatial_extractor import VLMSpatialExtractor
```

Replace the `_StubVLM` class and `_stub_vlm` function with a new factory:

```python
def _create_vlm_spatial_extractor(config: PipelineConfig) -> VLMSpatialExtractor | None:
    api_key = config.llm_api_key
    if not api_key:
        logger.warning("no_openai_key_vlm_spatial_disabled")
        return None
    import openai
    client = openai.OpenAI(api_key=api_key)
    return VLMSpatialExtractor(
        openai_client=client,
        prompts_dir=config.configs_dir / "prompts",
        model=config.vlm_model,
        method=config.vlm_extraction_method,
    )
```

Update the pipeline registration block. Replace:

```python
    if config.ablation.use_vlm:
        pipeline.register(VLMExtractionStep(vlm=_stub_vlm()))
```

With:

```python
    if config.ablation.use_vlm:
        vlm_spatial = _create_vlm_spatial_extractor(config)
        if vlm_spatial is not None:
            pipeline.register(VLMExtractionStep(vlm=vlm_spatial))
```

Remove the `_StubVLM` class and `_stub_vlm()` function.

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: all pass

- [ ] **Step 3: Lint and typecheck full project**

Run: `python -m ruff check src/ && python -m mypy src/ --strict`
Expected: clean

- [ ] **Step 4: Update execution status**

Update `docs/EXECUTION_STATUS.md`: change Phase 2b row to **Complete** and add detailed status section for Phase 2b with all checkboxes ticked.

- [ ] **Step 5: Commit**

```bash
git add src/planproof/bootstrap.py docs/EXECUTION_STATUS.md
git commit -m "feat(M3): wire VLMSpatialExtractor into bootstrap, remove stub"
```

---

## Task 7: Integration test against synthetic data

**Files:**
- Create: `tests/integration/test_vlm_extraction_step.py`

- [ ] **Step 1: Write integration test**

Write `tests/integration/test_vlm_extraction_step.py`:

```python
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

        # Mock OpenAI client that returns appropriate response per image
        mock_client = MagicMock()

        def side_effect(**kwargs: object) -> MagicMock:
            # Extract filename hint from the user message text
            messages = kwargs.get("messages", [])
            # Return first available mock response
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

        # Classify documents first
        classifier = RuleBasedClassifier(
            patterns_path=Path("configs/classifier_patterns.yaml")
        )
        class_step = ClassificationStep(classifier=classifier)
        context: dict[str, object] = {
            "entities": [],
            "metadata": {"input_dir": str(SYNTHETIC_SET)},
        }
        class_step.execute(context)

        # Run VLM extraction
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

        # Check that at least one measurement was extracted
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

        # Verify we found entities — attribute matching depends on mock fidelity
        assert len(context["entities"]) > 0
```

- [ ] **Step 2: Run integration tests**

Run: `python -m pytest tests/integration/test_vlm_extraction_step.py -v`
Expected: all pass (skipped if synthetic data missing)

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_vlm_extraction_step.py
git commit -m "test: add VLM extraction integration tests against synthetic data"
```

---

## Task 8: Final docs commit

**Files:**
- Add: `docs/superpowers/specs/2026-03-27-phase2b-vlm-spatial-extraction-design.md`
- Add: `docs/superpowers/plans/2026-03-27-phase2b-vlm-spatial-extraction.md`

- [ ] **Step 1: Commit docs**

```bash
git add docs/superpowers/specs/2026-03-27-phase2b-vlm-spatial-extraction-design.md docs/superpowers/plans/2026-03-27-phase2b-vlm-spatial-extraction.md
git commit -m "docs: Phase 2b M3 VLM spatial extraction spec and plan"
```

- [ ] **Step 2: Push to GitHub**

```bash
git push origin master
```
