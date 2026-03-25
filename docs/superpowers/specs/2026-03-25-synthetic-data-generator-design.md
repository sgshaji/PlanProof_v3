# Synthetic Data Generator — Design Specification

> **Date**: 2026-03-25
> **Status**: Draft
> **Phase**: Phase 1 — Data Pipeline & Synthetic Generation
> **Location**: `src/planproof/datagen/`

---

## 1. Purpose

Build a synthetic planning application generator that produces full-fidelity documents closely mimicking real BCC (Birmingham City Council) householder planning applications. The synthetic data serves as the ground truth dataset for evaluating every layer of the PlanProof pipeline — from OCR extraction through to final compliance verdicts.

### Success Criteria

- Synthetic documents are structurally indistinguishable from real BCC data by the pipeline
- Every value in every document has pixel-level ground truth (bounding box + exact value)
- Adding new compliance rules requires only a YAML config file, not code changes
- Adding new document types requires only a new generator plugin
- Identical seed always produces identical output
- The generator covers compliant, non-compliant, and edge-case scenarios with controlled difficulty

---

## 2. Real Data Analysis

Based on analysis of 10 real BCC planning applications (39 files total):

### Document Composition

| Document Type | Format | Frequency | Pages |
|--------------|--------|-----------|-------|
| Planning Application Form | PDF (text-layer) | 1 per application (always) | 7-8 |
| Site Plan / Location Plan | PDF (vector) | 1-2 per application | 1 |
| Floor Plans | PDF (vector/raster) | 0-3 per application | 1 each |
| Elevations | PDF / PNG / JPG | 0-3 per application | 1 each |
| Correspondence | PDF / PNG | 0-1 per application (20%) | 1-2 |

### File Naming Convention

Pattern: `{docID}-{category}-{type}.{ext}`

Examples:
- `6125163-Forms-Planning Application Form.pdf`
- `6125167-Plans & Drawings-Application Plans.pdf`
- `6130708-Correspondence-Private Supporting Information.pdf`

### Application Complexity Tiers

| Tier | Files | Description |
|------|-------|-------------|
| Minimal | 2-3 | 1 form + 1-2 simple drawings |
| Standard | 3-4 | 1 form + 2-3 drawings |
| Complex | 5-7 | 1 form + 4-6 detailed drawings + optional correspondence |

---

## 3. Architecture

Three-layer pipeline with hybrid functional/OOP design:

```
Layer 1: SCENARIO GENERATION (pure FP)
  Rule configs (YAML) → Violation matrix → Ground truth values
  Pure functions, seed-deterministic, no side effects

Layer 2: DOCUMENT RENDERING (OOP plugins)
  Ground truth values → PDF forms + architectural drawings
  Plugin registry, Protocol-based, each generator records bounding boxes

Layer 3: DEGRADATION & OUTPUT (FP composition)
  Clean documents → Degraded documents + extraction-level JSON sidecars
  Composable transform chains, configurable noise profiles
```

### Data Flow

```
RuleConfig (YAML)
    ↓
ScenarioGenerator  →  Scenario (immutable dataclass)
    ↓
DocumentGenerators →  list[GeneratedDocument] (bytes + bounding box registry)
    ↓
DegradationPipeline → list[DegradedDocument] (noisy files + adjusted bboxes)
    ↓
SidecarWriter      →  ground_truth.json (extraction-level truth)
```

Each layer depends only on the output of the previous layer via immutable dataclasses. No layer reaches back. The entire pipeline is deterministic given a seed.

### Design Principles

- **FP core**: Value generation, degradation transforms, and ground truth assembly are pure functions — no side effects, fully testable, composable
- **OOP boundaries**: Plugin registry, document generators, and rendering use Protocol-based OOP — polymorphism and extensibility where it belongs
- **Immutable data**: All intermediate data structures are frozen dataclasses with `tuple` for collections (not `list`) to enforce true immutability
- **Config-driven**: Rules, profiles, and degradation presets are YAML — behaviour changes without code changes

---

## 4. Layer 1 — Scenario Generation

### Rule Configuration

Each compliance rule has two config files: the **production rule** in `configs/rules/` (used by the rule engine at runtime) and a **datagen extension** in `configs/datagen/rules/` that adds generation-specific fields. The datagen config references the production rule by `rule_id`:

```yaml
# configs/datagen/rules/r001_building_height.yaml
# Extension of configs/rules/r001_building_height.yaml
rule_id: R001
attribute: building_height
unit: metres
compliant_range: { min: 3.0, max: 8.0 }
violation_types:
  - name: exceeds_max
    range: { min: 8.1, max: 15.0 }
  - name: marginal_exceed
    range: { min: 8.01, max: 8.5 }
  - name: extreme_exceed
    range: { min: 12.0, max: 20.0 }
evidence_locations:
  - doc_type: FORM
    field: "proposed_height"
  - doc_type: DRAWING
    drawing_type: elevation
    annotation: dimension_line
```

The datagen loader validates these configs using Pydantic at load time. Invalid YAML (missing keys, out-of-range values, unknown doc_type references) raises `ConfigValidationError` at startup, before any generation begins.

### Scenario Profiles

Application-level characteristics defined in YAML:

```yaml
# configs/datagen/profiles/standard_3file.yaml
profile_id: standard_3file
document_composition:
  - type: FORM
    count: 1
  - type: DRAWING
    subtypes: [site_plan, floor_plan]
    count: 2
difficulty: medium
degradation_preset: moderate_scan
```

### Scenario Data Structure

The `Scenario` dataclass is the central contract between Layer 1 and Layer 2:

```python
@dataclass(frozen=True)
class Value:
    """A single ground-truth value to be placed in documents."""
    attribute: str
    value: float
    unit: str
    display_text: str         # e.g. "7.5m" — what gets rendered

@dataclass(frozen=True)
class Verdict:
    """Expected rule verdict for this scenario."""
    rule_id: str
    outcome: str              # "PASS", "FAIL", "NOT_ASSESSABLE"
    evaluated_value: float
    threshold: float

@dataclass(frozen=True)
class DocumentSpec:
    """Specification for one document to generate."""
    doc_type: str             # "FORM", "SITE_PLAN", "FLOOR_PLAN", "ELEVATION"
    file_format: str          # "pdf", "png", "jpg"
    values_to_place: tuple[str, ...]  # attribute names from values dict

@dataclass(frozen=True)
class Scenario:
    """Complete specification for generating one application set."""
    set_id: str
    category: str             # "compliant", "noncompliant", "edgecase"
    seed: int
    profile_id: str
    difficulty: str
    degradation_preset: str
    values: tuple[Value, ...]
    verdicts: tuple[Verdict, ...]
    documents: tuple[DocumentSpec, ...]
    edge_case_strategy: str | None  # None for compliant/noncompliant
```

### Pure Functions

- `generate_values(rule_configs, category, seed) -> tuple[Value, ...]` — produces compliant, noncompliant, or edge-case values from rule ranges using seeded RNG
- `compute_verdicts(values, rule_configs) -> tuple[Verdict, ...]` — deterministic verdict computation
- `build_scenario(profile, rule_configs, category, seed) -> Scenario` — assembles the full immutable scenario

### Seed Propagation

To avoid correlated randomness across generators, seeds are derived deterministically per document:

```python
document_seed = hash((scenario.seed, document_index, doc_type)) & 0xFFFFFFFF
```

This ensures: (a) same scenario seed always produces same documents, (b) each generator gets a unique seed, (c) adding/removing documents doesn't change other documents' seeds.

### Edge-Case Strategies

Named strategies, each a pure function `Scenario -> Scenario`:

| Strategy | What it does |
|----------|-------------|
| `missing_evidence` | Omit a measurement from one or more documents |
| `conflicting_values` | Same attribute, different values across documents |
| `low_confidence_scan` | Extreme degradation making extraction unreliable |
| `partial_documents` | Missing an entire document type (e.g. no elevation) |
| `ambiguous_units` | Value present but unit missing or unclear |

### Edge-Case Distribution

The 10 edge-case sets are allocated to ensure full strategy coverage:

| Sets | Strategy | Rules targeted |
|------|----------|---------------|
| 2 | `missing_evidence` | R001, R002 |
| 2 | `conflicting_values` | R001, R003 |
| 2 | `low_confidence_scan` | All rules |
| 2 | `partial_documents` | R001 (no elevation), R002 (no site plan) |
| 2 | `ambiguous_units` | R001, R003 |

---

## 5. Layer 2 — Document Rendering

### Plugin Protocol

Every document generator implements:

```python
class DocumentGenerator(Protocol):
    """Contract for all document type generators."""

    def generate(
        self, scenario: Scenario, doc_spec: DocumentSpec, seed: int
    ) -> GeneratedDocument: ...
```

### Coordinate System

All bounding boxes use a **unified coordinate system** regardless of document format:

- **Unit**: pixels at 300 DPI (the canonical rendering resolution)
- **Origin**: top-left of the page (image convention, not PDF convention)
- **For PDF documents**: generators internally use PDF points (origin bottom-left) during rendering, but convert all bounding boxes to the canonical pixel coordinate system before returning `PlacedValue` objects
- **For raster images**: coordinates are native pixels at the rendering resolution

This means all bounding boxes in `ground_truth.json` are in the same coordinate system, regardless of source document format. The degradation layer's affine transforms operate in this same space.

### Core Data Structures

```python
@dataclass(frozen=True)
class PlacedValue:
    """A single value placed in a document, with its exact location."""
    attribute: str
    value: Any
    text_rendered: str        # e.g. "7.5m"
    page: int
    bounding_box: BoundingBox  # reuses planproof.schemas.entities.BoundingBox
    entity_type: EntityType    # reuses planproof.schemas.entities.EntityType

@dataclass(frozen=True)
class GeneratedDocument:
    filename: str
    doc_type: DocumentType
    content_bytes: bytes
    file_format: str          # "pdf", "png", "jpg"
    placed_values: tuple[PlacedValue, ...]  # tuple for true immutability
```

Note: `BoundingBox` is imported from `planproof.schemas.entities` — the same type used throughout the pipeline. The datagen module does not define its own.

### Generator Plugins

| Plugin | Output | What it renders |
|--------|--------|-----------------|
| `FormGenerator` | PDF (7-8 pages) | Planning application form — site address, applicant, description of works, measurements, ownership certificate |
| `SitePlanGenerator` | PDF (vector) | Top-down site boundary with setback dimensions, north arrow, scale bar, property outline |
| `FloorPlanGenerator` | PDF (vector) | Room layouts with internal dimensions, wall thicknesses, door/window positions |
| `ElevationGenerator` | PNG (raster) | Front/side elevation with height annotations, roof pitch, ground level datum |

### Plugin Registry

```python
registry = DocumentGeneratorRegistry()
registry.register("FORM", FormGenerator())
registry.register("SITE_PLAN", SitePlanGenerator())
registry.register("FLOOR_PLAN", FloorPlanGenerator())
registry.register("ELEVATION", ElevationGenerator())
```

New document types are added by implementing the `DocumentGenerator` Protocol and registering with the factory. No existing code is modified.

### Bounding Box Tracking

Every value placed in any document is tracked with its exact coordinates. If "building_height: 7.5m" appears on page 3 of the form AND on the elevation drawing, both locations are recorded. This is what makes extraction-level ground truth possible.

---

## 6. Layer 3 — Degradation & Output

### Two Degradation Paths

PDF and raster documents require different degradation strategies:

**Raster documents (PNG/JPG — elevations, some drawings):**
Degradation transforms apply directly to the pixel array. Bounding boxes are adjusted via accumulated affine matrices.

**PDF documents (forms, vector drawings):**
PDFs cannot be degraded as raw files — noise and rotation don't apply to vector data. Instead:
1. The PDF is rendered to a raster image at 300 DPI (the canonical resolution)
2. Degradation transforms are applied to the rasterised image
3. The degraded image is saved as PDF (embedded raster) or PNG
4. The original text-layer PDF is **also preserved** alongside the degraded version

This means each PDF document produces two output files:
- `{docID}-Forms-Planning Application Form.pdf` — original text-layer (for OCR evaluation)
- `{docID}-Forms-Planning Application Form_scan.png` — degraded raster (for robustness evaluation)

The ground truth sidecar references both versions with their respective bounding boxes.

### Composable Transforms

Each transform returns both the transformed image and an optional affine matrix:

```python
@dataclass(frozen=True)
class TransformResult:
    image: ImageArray
    affine: AffineMatrix | None  # None if no geometric change

DegradeFn = Callable[[ImageArray], TransformResult]
```

Non-geometric transforms (noise, compression, contrast) return `affine=None`. Geometric transforms (rotation, resolution) return the affine matrix used. The pipeline accumulates non-None matrices and applies them to all bounding boxes at the end.

| Transform | Geometric? | What it does | Parameters |
|-----------|-----------|-------------|------------|
| `add_gaussian_noise` | No | Scanner sensor noise | `sigma: float` |
| `add_speckle_noise` | No | Dust/dirt on scanner | `density: float` |
| `apply_rotation` | Yes | Page skew from scanning | `degrees: float` |
| `apply_jpeg_compression` | No | Lossy compression artefacts | `quality: int (1-100)` |
| `vary_resolution` | Yes | Downsample then upsample | `target_dpi: int` |
| `dilate_erode` | No | Thicken/thin text strokes (morphological) | `kernel_size: int, iterations: int` |
| `add_partial_occlusion` | No | Dark patches/fold marks | `count: int, size: float` |
| `adjust_contrast` | No | Faded or over-exposed regions | `factor: float` |

### Composition via Pipeline Chains

```python
moderate_scan = compose(
    partial(add_gaussian_noise, sigma=0.02),
    partial(apply_rotation, degrees=1.5),
    partial(apply_jpeg_compression, quality=85),
)

heavy_scan = compose(
    partial(add_gaussian_noise, sigma=0.05),
    partial(add_speckle_noise, density=0.01),
    partial(apply_rotation, degrees=3.0),
    partial(apply_jpeg_compression, quality=60),
    partial(vary_resolution, target_dpi=150),
)
```

### Degradation Presets (YAML)

```yaml
# configs/datagen/degradation/moderate_scan.yaml
preset_id: moderate_scan
transforms:
  - name: add_gaussian_noise
    params: { sigma: 0.02 }
  - name: apply_rotation
    params: { degrees: 1.5 }
  - name: apply_jpeg_compression
    params: { quality: 85 }
```

### Difficulty Mapping

| Category | Preset | Rationale |
|----------|--------|-----------|
| Compliant | `clean` to `moderate_scan` | Tests rule logic, not OCR |
| Non-compliant | `moderate_scan` to `heavy_scan` | Realistic challenge |
| Edge-case | `heavy_scan` + edge-case strategies | Tests pipeline robustness |

---

## 7. Output Structure

### Directory Layout

```
data/synthetic/
├── compliant/
│   ├── SET_C001/
│   │   ├── 7000001-Forms-Planning Application Form.pdf
│   │   ├── 7000001-Forms-Planning Application Form_scan.png
│   │   ├── 7000002-Plans & Drawings-Application Plans.pdf
│   │   ├── 7000003-Plans & Drawings-Application Plans.pdf
│   │   ├── 7000004-Plans & Drawings-Application Plans.png
│   │   ├── reference/
│   │   │   ├── parcel.geojson
│   │   │   └── zone.json
│   │   └── ground_truth.json
│   └── ... (20 compliant sets)
├── noncompliant/
│   └── ... (20 noncompliant sets)
└── edgecase/
    └── ... (10 edge-case sets)
```

### File Formats

| Output | Format | Purpose |
|--------|--------|---------|
| Planning application forms | PDF (text-layer) + PNG (degraded scan) | OCR + LLM entity extraction |
| Site plans, floor plans | PDF (vector + text) + PNG (degraded scan) | VLM spatial extraction |
| Elevations, block plans | PNG/JPG (raster, degraded) | VLM extraction with noise |
| Parcel geometry | GeoJSON | SNKG reference data (Phase 3) |
| Zone assignment | JSON | Rule applicability lookup |
| Ground truth | JSON | Evaluation at every pipeline stage |

### Reference File Schemas

**parcel.geojson** — GeoJSON FeatureCollection with a single polygon representing the property boundary:

```json
{
  "type": "FeatureCollection",
  "features": [{
    "type": "Feature",
    "properties": {
      "parcel_id": "SET_C001",
      "address": "14 Maple Street, Bishopsworth, BS13 7AA",
      "area_sqm": 450.0
    },
    "geometry": {
      "type": "Polygon",
      "coordinates": [[[0, 0], [15, 0], [15, 30], [0, 30], [0, 0]]]
    }
  }]
}
```

**zone.json** — Zone assignment for rule applicability:

```json
{
  "parcel_id": "SET_C001",
  "zone_code": "R1",
  "zone_name": "General Residential",
  "applicable_rules": ["R001", "R002", "R003"]
}
```

### Ground Truth Schema

```json
{
  "set_id": "SET_C001",
  "category": "compliant",
  "seed": 42,
  "difficulty": "medium",
  "values": {
    "building_height": { "value": 7.5, "unit": "metres" },
    "front_setback": { "value": 6.2, "unit": "metres" },
    "site_coverage": { "value": 45.0, "unit": "percent" }
  },
  "rule_verdicts": {
    "R001": { "outcome": "PASS", "evaluated_value": 7.5, "threshold": 8.0 },
    "R002": { "outcome": "PASS", "evaluated_value": 12.0, "threshold": 10.0 }
  },
  "documents": [
    {
      "filename": "7000001-Forms-Planning Application Form.pdf",
      "doc_type": "FORM",
      "has_degraded_version": true,
      "degraded_filename": "7000001-Forms-Planning Application Form_scan.png",
      "extractions": [
        {
          "entity_type": "ADDRESS",
          "value": "14 Maple Street, Bishopsworth, BS13 7AA",
          "attribute": "site_address",
          "page": 1,
          "bounding_box": { "x": 145, "y": 312, "width": 280, "height": 18 },
          "text_snippet": "14 Maple Street, Bishopsworth, BS13 7AA"
        },
        {
          "entity_type": "MEASUREMENT",
          "value": 7.5,
          "unit": "metres",
          "attribute": "building_height",
          "page": 3,
          "bounding_box": { "x": 220, "y": 445, "width": 40, "height": 14 },
          "text_snippet": "7.5m"
        }
      ],
      "degraded_extractions": [
        {
          "entity_type": "MEASUREMENT",
          "value": 7.5,
          "unit": "metres",
          "attribute": "building_height",
          "page": 3,
          "bounding_box": { "x": 223, "y": 449, "width": 41, "height": 15 },
          "text_snippet": "7.5m"
        }
      ]
    }
  ],
  "degradation": {
    "preset": "moderate_scan",
    "applied_transforms": [
      { "name": "add_gaussian_noise", "params": { "sigma": 0.02 } },
      { "name": "apply_rotation", "params": { "degrees": 1.2 } },
      { "name": "apply_jpeg_compression", "params": { "quality": 85 } }
    ]
  }
}
```

Bounding box coordinates are in **pixels at 300 DPI, origin top-left**. The `degraded_extractions` array contains bounding boxes adjusted by the accumulated affine transforms from the degradation pipeline.

---

## 8. Module Structure

```
src/planproof/datagen/
├── __init__.py
├── runner.py                  # CLI entry point: generate all sets
├── scenario/
│   ├── __init__.py
│   ├── models.py              # Scenario, Value, Verdict, DocumentSpec (frozen dataclasses)
│   ├── generator.py           # Pure functions: generate_values, compute_verdicts, build_scenario
│   ├── edge_cases.py          # Edge-case strategy functions
│   └── config_loader.py       # Pydantic-validated YAML loading, raises ConfigValidationError
├── rendering/
│   ├── __init__.py
│   ├── registry.py            # DocumentGeneratorRegistry
│   ├── models.py              # GeneratedDocument, PlacedValue (frozen dataclasses)
│   ├── coord_utils.py         # PDF-point ↔ pixel conversion, coordinate system helpers
│   ├── form_generator.py      # FormGenerator plugin
│   ├── site_plan_generator.py # SitePlanGenerator plugin
│   ├── floor_plan_generator.py# FloorPlanGenerator plugin
│   └── elevation_generator.py # ElevationGenerator plugin
├── degradation/
│   ├── __init__.py
│   ├── transforms.py          # Pure transform functions returning TransformResult
│   ├── compose.py             # compose() utility + preset loader
│   ├── bbox_adjust.py         # Affine bounding box recalculation
│   └── rasterise.py           # PDF → raster at canonical 300 DPI
└── output/
    ├── __init__.py
    ├── sidecar_writer.py      # Assemble + write ground_truth.json
    ├── reference_writer.py    # Write parcel.geojson + zone.json
    └── file_writer.py         # Write documents to disk with BCC naming convention

configs/datagen/
├── rules/
│   ├── r001_building_height.yaml
│   ├── r002_rear_garden.yaml
│   └── r003_site_coverage.yaml
├── profiles/
│   ├── minimal_2file.yaml
│   ├── standard_3file.yaml
│   └── complex_6file.yaml
└── degradation/
    ├── clean.yaml
    ├── moderate_scan.yaml
    └── heavy_scan.yaml
```

---

## 9. Dependencies

| Package | Purpose | Already installed? |
|---------|---------|-------------------|
| `reportlab` | PDF generation (forms, vector drawings) | No — add to core deps |
| `Pillow` | Raster image generation + degradation transforms | No — add to core deps |
| `numpy` | Noise generation, affine transforms | Already installed |
| `pydantic` | Data models for configs and ground truth | Already installed |
| `pyyaml` | Config loading | Already installed |

---

## 10. Testing Strategy

| Test Type | What it validates |
|-----------|------------------|
| Unit: scenario generation | Pure functions produce correct values/verdicts for each category and seed |
| Unit: verdict computation | Every rule config + value combination yields the expected verdict |
| Unit: edge-case strategies | Each strategy introduces exactly the expected deficiency |
| Unit: degradation transforms | Each transform produces expected visual changes; geometric transforms return correct affine matrices; bounding box adjustments are geometrically correct |
| Unit: coordinate conversion | PDF-point ↔ pixel conversions are accurate and round-trip correctly |
| Unit: config validation | Invalid YAML configs raise `ConfigValidationError` with clear messages |
| Integration: full pipeline | Seed → documents + sidecar. Verify files exist, sidecar schema valid, bounding boxes within document bounds |
| Integration: PDF rasterisation | PDF → raster → degradation → bbox adjustment produces correct coordinates |
| Determinism: seed stability | Same seed produces byte-identical output across runs |
| Coverage: violation matrix | Every rule × every violation type has at least one set in the output |
| Coverage: edge-case strategies | All 5 strategies appear in the 10 edge-case sets per the distribution table |

---

## 11. Future Extensibility

| Extension | How to add it |
|-----------|--------------|
| New compliance rule | Add YAML to `configs/rules/` (production) and `configs/datagen/rules/` (generation ranges). Optionally add violation strategy to `edge_cases.py` |
| New document type | Implement `DocumentGenerator` Protocol, register in `rendering/registry.py` |
| New degradation transform | Add pure function returning `TransformResult` to `degradation/transforms.py`, reference in preset YAML |
| LLM-generated text content | Add an `LLMContentPlugin` that generates realistic descriptions of works, material choices, etc. via Groq. Inject into `FormGenerator` as an optional content provider. Architecture unchanged. |
| New edge-case strategy | Add pure function to `scenario/edge_cases.py` |

---

## 12. Execution

```bash
# Generate all 50 sets (20 compliant + 20 noncompliant + 10 edgecase)
python -m planproof.datagen.runner

# Generate specific category (for development/testing — does not produce evaluation dataset)
python -m planproof.datagen.runner --category compliant --count 5

# Generate with specific seed (reproducible)
python -m planproof.datagen.runner --seed 42

# Verify generated data
make verify-data
```

The default invocation (`python -m planproof.datagen.runner`) always produces the full evaluation dataset: 20 compliant, 20 noncompliant, 10 edgecase. The `--count` flag is for development iteration only and is incompatible with `make verify-data` (which expects the full 50 sets).
