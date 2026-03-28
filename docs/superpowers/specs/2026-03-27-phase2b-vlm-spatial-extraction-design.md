# Phase 2b: M3 VLM Spatial Extraction — Design Spec

**Date:** 2026-03-27
**Status:** Approved
**Depends on:** Phase 2a (M1 classifier, M2 text extraction)

---

## Goal

Extract spatially grounded measurements from DRAWING-classified documents (site plans, floor plans, elevations) using GPT-4o vision. Produce `ExtractedEntity` instances with attribute labels, numeric values, units, and bounding box coordinates.

## Two Extraction Methods (Ablation Dimension)

| Method | `ExtractionMethod` | Description |
|--------|-------------------|-------------|
| Zero-shot | `VLM_ZEROSHOT` | Single GPT-4o call with structured output schema requesting entities + bbox pixel coords |
| Two-stage | `VLM_STRUCTURED` | Stage 1: GPT-4o identifies entities + coarse regions. Stage 2: crop each region, re-query for precise value + refined bbox |

Selected via `config.vlm_extraction_method` (`"zeroshot"` | `"structured"`). Default: `"zeroshot"`.

## Data Flow

```
ClassifiedDocument (DRAWING, has_text_layer=False)
  → VLMExtractionStep.execute()
    → filter context["classified_documents"] to DRAWINGs without text layer
    → for each drawing:
        → determine DrawingSubtype from filename patterns
        → VLMSpatialExtractor.extract_spatial_attributes(image_path)
          → [zeroshot]: single GPT-4o call → parse JSON → ExtractedEntity[]
          → [structured]: GPT-4o coarse → crop regions → GPT-4o refine → ExtractedEntity[]
    → append to context["entities"]
```

## New Files

| File | Purpose |
|------|---------|
| `src/planproof/ingestion/vlm_spatial_extractor.py` | `VLMSpatialExtractor` implementing `VLMExtractor` Protocol |
| `configs/prompts/spatial_zeroshot.yaml` | Zero-shot prompt with bbox output schema |
| `configs/prompts/spatial_structured_stage1.yaml` | Coarse localisation prompt |
| `configs/prompts/spatial_structured_stage2.yaml` | Crop refinement prompt |
| `tests/unit/ingestion/test_vlm_spatial_extractor.py` | Unit tests with mocked GPT-4o |
| `tests/integration/test_vlm_extraction_step.py` | Integration test against synthetic data |

## Modified Files

| File | Change |
|------|--------|
| `schemas/entities.py` | Add `DrawingSubtype` enum (SITE_PLAN, FLOOR_PLAN, ELEVATION) |
| `schemas/config.py` | Add `vlm_extraction_method: str = "zeroshot"` to `PipelineConfig` |
| `pipeline/steps/vlm_extraction.py` | Implement `execute()` — filter drawings, call extractor, merge entities |
| `bootstrap.py` | Replace `_StubVLM` with `VLMSpatialExtractor`, wire config |

## Key Interfaces

`VLMSpatialExtractor` satisfies the existing `VLMExtractor` Protocol. The Protocol signature stays unchanged (`extract_spatial_attributes(image: Path) -> list[ExtractedEntity]`). Drawing subtype is inferred internally from the filename, not passed as a parameter — this keeps the Protocol clean.

```python
class VLMSpatialExtractor:
    def __init__(self, openai_client, prompts_dir, model, method): ...
    def extract_spatial_attributes(self, image: Path) -> list[ExtractedEntity]: ...
    def _infer_subtype(self, image: Path) -> DrawingSubtype: ...
```

## Prompt Design

**Zero-shot prompt** requests structured JSON with bbox:
```json
{"entities": [
  {"entity_type": "MEASUREMENT", "attribute": "building_height", "value": 7.2, "unit": "metres",
   "bounding_box": {"x": 150, "y": 300, "width": 80, "height": 25}, "source_page": 1}
]}
```

**Structured stage 1** returns coarse regions:
```json
{"regions": [
  {"attribute": "building_height", "region": {"x": 120, "y": 270, "width": 150, "height": 80}}
]}
```

**Structured stage 2** receives a cropped image and returns a single precise extraction.

## Subtype-Aware Prompting

Drawing subtype (SITE_PLAN, FLOOR_PLAN, ELEVATION) drives which attributes to prioritise:
- **SITE_PLAN**: rear_garden_depth, site_coverage, setback distances, site area
- **FLOOR_PLAN**: room dimensions, floor area, wall lengths
- **ELEVATION**: building_height, ridge height, eave height, storey heights

Subtype determined from filename patterns (same regex patterns used by M1 classifier).

## Evaluation

- **Primary metric:** value-match accuracy against ground truth (`ground_truth.json` per synthetic set)
- **Secondary (logged):** bounding box pixel coordinates stored in `ExtractedEntity.source_region`
- Bbox accuracy metrics (IoU, centre-point distance) deferred for future optimisation

## Deferred

- `VLM_FINETUNED` extraction method — fine-tuned VLM for domain-specific spatial extraction (may be needed later)
- IoU / centre-point bbox accuracy evaluation
- Multi-page drawing support (current synthetic data is single-page per drawing)
