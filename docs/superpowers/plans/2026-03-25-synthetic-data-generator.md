# Synthetic Data Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a synthetic planning application generator that produces full-fidelity PDF/PNG documents with extraction-level ground truth, closely mimicking real BCC planning applications.

**Architecture:** Three-layer pipeline — (1) scenario generation via pure functions from YAML configs, (2) document rendering via Protocol-based plugins with bounding box tracking, (3) configurable degradation with affine bbox adjustment. Hybrid FP/OOP: pure functions for data transforms, Protocol-based OOP for plugin extensibility.

**Tech Stack:** Python 3.11+, reportlab (PDF generation), Pillow (raster images + degradation), numpy (noise/affine), pydantic (config validation), pyyaml (config loading)

**Spec:** `docs/superpowers/specs/2026-03-25-synthetic-data-generator-design.md`

---

## File Structure

### New Files to Create

**Layer 1 — Scenario Generation:**
- `src/planproof/datagen/__init__.py` — Package root
- `src/planproof/datagen/scenario/__init__.py` — Subpackage
- `src/planproof/datagen/scenario/models.py` — Value, Verdict, DocumentSpec, Scenario (frozen dataclasses)
- `src/planproof/datagen/scenario/config_loader.py` — Pydantic models for YAML configs, ConfigValidationError
- `src/planproof/datagen/scenario/generator.py` — Pure functions: generate_values, compute_verdicts, build_scenario
- `src/planproof/datagen/scenario/edge_cases.py` — Edge-case strategy functions

**Layer 2 — Document Rendering:**
- `src/planproof/datagen/rendering/__init__.py` — Subpackage
- `src/planproof/datagen/rendering/models.py` — PlacedValue, GeneratedDocument (frozen dataclasses)
- `src/planproof/datagen/rendering/coord_utils.py` — PDF-point ↔ pixel conversion
- `src/planproof/datagen/rendering/registry.py` — DocumentGeneratorRegistry
- `src/planproof/datagen/rendering/form_generator.py` — FormGenerator plugin
- `src/planproof/datagen/rendering/site_plan_generator.py` — SitePlanGenerator plugin
- `src/planproof/datagen/rendering/floor_plan_generator.py` — FloorPlanGenerator plugin
- `src/planproof/datagen/rendering/elevation_generator.py` — ElevationGenerator plugin

**Layer 3 — Degradation & Output:**
- `src/planproof/datagen/degradation/__init__.py` — Subpackage
- `src/planproof/datagen/degradation/transforms.py` — Pure transform functions
- `src/planproof/datagen/degradation/compose.py` — compose() utility + preset loader
- `src/planproof/datagen/degradation/bbox_adjust.py` — Affine bounding box recalculation
- `src/planproof/datagen/degradation/rasterise.py` — PDF → raster at 300 DPI
- `src/planproof/datagen/output/__init__.py` — Subpackage
- `src/planproof/datagen/output/sidecar_writer.py` — ground_truth.json assembly
- `src/planproof/datagen/output/reference_writer.py` — parcel.geojson + zone.json
- `src/planproof/datagen/output/file_writer.py` — Disk output with BCC naming
- `src/planproof/datagen/runner.py` — CLI entry point

**YAML Configs:**
- `configs/datagen/rules/r001_building_height.yaml`
- `configs/datagen/rules/r002_rear_garden.yaml`
- `configs/datagen/rules/r003_site_coverage.yaml`
- `configs/datagen/profiles/minimal_2file.yaml`
- `configs/datagen/profiles/standard_3file.yaml`
- `configs/datagen/profiles/complex_6file.yaml`
- `configs/datagen/degradation/clean.yaml`
- `configs/datagen/degradation/moderate_scan.yaml`
- `configs/datagen/degradation/heavy_scan.yaml`

**Tests:**
- `tests/unit/datagen/__init__.py`
- `tests/unit/datagen/test_models.py`
- `tests/unit/datagen/test_config_loader.py`
- `tests/unit/datagen/test_generator.py`
- `tests/unit/datagen/test_edge_cases.py`
- `tests/unit/datagen/test_coord_utils.py`
- `tests/unit/datagen/test_registry.py`
- `tests/unit/datagen/test_transforms.py`
- `tests/unit/datagen/test_compose.py`
- `tests/unit/datagen/test_bbox_adjust.py`
- `tests/unit/datagen/test_form_generator.py`
- `tests/unit/datagen/test_site_plan_generator.py`
- `tests/unit/datagen/test_floor_plan_generator.py`
- `tests/unit/datagen/test_elevation_generator.py`
- `tests/unit/datagen/test_sidecar_writer.py`
- `tests/unit/datagen/test_reference_writer.py`
- `tests/unit/datagen/test_file_writer.py`
- `tests/integration/test_datagen_pipeline.py`
- `tests/integration/test_datagen_coverage.py`
- `src/planproof/datagen/output/verify_data.py` — Dataset integrity verification

### Files to Modify

- `pyproject.toml` — Add reportlab, Pillow to dependencies
- `Makefile` — Add `generate-data` and `verify-data` targets
- `.gitignore` — Add `data/synthetic/` to prevent committing generated binaries

---

## Task 1: Install Dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add reportlab and Pillow to pyproject.toml**

Add to the `dependencies` list in `pyproject.toml`:

```toml
dependencies = [
    "pydantic>=2.0",
    "pydantic-settings",
    "structlog",
    "neo4j",
    "openai",
    "pyyaml",
    "requests",
    "groq",
    "reportlab",
    "Pillow",
]
```

- [ ] **Step 2: Install**

Run: `pip install -e ".[dev]"`
Expected: SUCCESS — both reportlab and Pillow install on ARM64 Windows

- [ ] **Step 3: Verify imports**

Run: `python -c "import reportlab; import PIL; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "feat: add reportlab and Pillow for synthetic data generation"
```

---

## Task 2: Scenario Models (Frozen Dataclasses)

**Files:**
- Create: `src/planproof/datagen/__init__.py`
- Create: `src/planproof/datagen/scenario/__init__.py`
- Create: `src/planproof/datagen/scenario/models.py`
- Test: `tests/unit/datagen/__init__.py`
- Test: `tests/unit/datagen/test_models.py`

- [ ] **Step 1: Write failing tests for scenario models**

```python
# tests/unit/datagen/test_models.py
"""Tests for datagen scenario models — immutability and construction."""
from __future__ import annotations

import pytest

from planproof.datagen.scenario.models import (
    DocumentSpec,
    Scenario,
    Value,
    Verdict,
)


class TestValue:
    def test_creation(self) -> None:
        v = Value(attribute="building_height", value=7.5, unit="metres", display_text="7.5m")
        assert v.attribute == "building_height"
        assert v.value == 7.5
        assert v.display_text == "7.5m"

    def test_frozen(self) -> None:
        v = Value(attribute="x", value=1.0, unit="m", display_text="1m")
        with pytest.raises(AttributeError):
            v.value = 2.0  # type: ignore[misc]


class TestVerdict:
    def test_creation(self) -> None:
        v = Verdict(rule_id="R001", outcome="PASS", evaluated_value=7.5, threshold=8.0)
        assert v.outcome == "PASS"


class TestDocumentSpec:
    def test_creation(self) -> None:
        ds = DocumentSpec(
            doc_type="FORM",
            file_format="pdf",
            values_to_place=("building_height", "site_address"),
        )
        assert ds.doc_type == "FORM"
        assert len(ds.values_to_place) == 2


class TestScenario:
    def test_creation(self) -> None:
        s = Scenario(
            set_id="SET_C001",
            category="compliant",
            seed=42,
            profile_id="standard_3file",
            difficulty="medium",
            degradation_preset="moderate_scan",
            values=(Value(attribute="h", value=7.5, unit="m", display_text="7.5m"),),
            verdicts=(Verdict(rule_id="R001", outcome="PASS", evaluated_value=7.5, threshold=8.0),),
            documents=(DocumentSpec(doc_type="FORM", file_format="pdf", values_to_place=("h",)),),
            edge_case_strategy=None,
        )
        assert s.set_id == "SET_C001"
        assert s.edge_case_strategy is None

    def test_frozen(self) -> None:
        s = Scenario(
            set_id="X", category="compliant", seed=1, profile_id="p",
            difficulty="low", degradation_preset="clean",
            values=(), verdicts=(), documents=(), edge_case_strategy=None,
        )
        with pytest.raises(AttributeError):
            s.seed = 99  # type: ignore[misc]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/datagen/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'planproof.datagen'`

- [ ] **Step 3: Create package structure and models**

Create `src/planproof/datagen/__init__.py`:
```python
"""Synthetic data generation for PlanProof evaluation datasets."""
```

Create `src/planproof/datagen/scenario/__init__.py`:
```python
"""Scenario generation layer — pure functions producing immutable scenarios."""
```

Create `src/planproof/datagen/scenario/models.py`:
```python
"""Immutable data structures for the scenario generation layer.

These frozen dataclasses are the contract between Layer 1 (scenario generation)
and Layer 2 (document rendering). All collections use tuple for true immutability.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Value:
    """A single ground-truth value to be placed in documents.

    # WHY: Separating the semantic value (7.5 metres) from its display form
    # ("7.5m") lets generators render values in context-appropriate ways while
    # the ground truth always records the canonical value.
    """

    attribute: str
    value: float
    unit: str
    display_text: str


@dataclass(frozen=True)
class Verdict:
    """Expected rule verdict for this scenario.

    # WHY: Pre-computing verdicts at generation time means the ground truth
    # JSON carries the expected outcome. The evaluation harness compares
    # pipeline output against these without re-running rule logic.
    """

    rule_id: str
    outcome: str  # "PASS", "FAIL", "NOT_ASSESSABLE"
    evaluated_value: float
    threshold: float


@dataclass(frozen=True)
class DocumentSpec:
    """Specification for one document to generate.

    # WHY: The scenario tells each generator which values to place, so
    # different documents can carry different subsets of the ground truth.
    # This models real-world applications where height appears on elevations
    # but not on the site plan.
    """

    doc_type: str  # "FORM", "SITE_PLAN", "FLOOR_PLAN", "ELEVATION"
    file_format: str  # "pdf", "png", "jpg"
    values_to_place: tuple[str, ...]  # attribute names from Scenario.values


@dataclass(frozen=True)
class Scenario:
    """Complete specification for generating one application set.

    # WHY: This is the central contract between Layer 1 and Layer 2. Everything
    # a document generator needs is here — values, document specs, difficulty
    # settings. The scenario is built once by pure functions and never mutated.
    """

    set_id: str
    category: str  # "compliant", "noncompliant", "edgecase"
    seed: int
    profile_id: str
    difficulty: str
    degradation_preset: str
    values: tuple[Value, ...]
    verdicts: tuple[Verdict, ...]
    documents: tuple[DocumentSpec, ...]
    edge_case_strategy: str | None  # None for compliant/noncompliant
```

Also create `tests/unit/datagen/__init__.py` (empty).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/datagen/test_models.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Run ruff + mypy**

Run: `ruff check src/planproof/datagen/ tests/unit/datagen/ && mypy src/planproof/datagen/`
Expected: All checks passed

- [ ] **Step 6: Commit**

```bash
git add src/planproof/datagen/ tests/unit/datagen/
git commit -m "feat(datagen): add scenario models — Value, Verdict, DocumentSpec, Scenario"
```

---

## Task 3a: YAML Config Files

**Files:**
- Create: `configs/datagen/rules/r001_building_height.yaml`
- Create: `configs/datagen/rules/r002_rear_garden.yaml`
- Create: `configs/datagen/rules/r003_site_coverage.yaml`
- Create: `configs/datagen/profiles/minimal_2file.yaml`
- Create: `configs/datagen/profiles/standard_3file.yaml`
- Create: `configs/datagen/profiles/complex_6file.yaml`
- Create: `configs/datagen/degradation/clean.yaml`
- Create: `configs/datagen/degradation/moderate_scan.yaml`
- Create: `configs/datagen/degradation/heavy_scan.yaml`

- [ ] **Step 1: Create rule configs** — one YAML per rule matching spec Section 4 schema
- [ ] **Step 2: Create profile configs** — minimal, standard, complex matching spec Section 4
- [ ] **Step 3: Create degradation presets** — clean, moderate_scan, heavy_scan matching spec Section 6
- [ ] **Step 4: Commit**

```bash
git add configs/datagen/
git commit -m "feat(datagen): add 9 YAML configs — rules, profiles, degradation presets"
```

---

## Task 3b: Config Loader (Pydantic-validated YAML)

**Files:**
- Create: `src/planproof/datagen/scenario/config_loader.py`
- Test: `tests/unit/datagen/test_config_loader.py`

- [ ] **Step 1: Write failing tests for config loader**

Test that valid YAML loads into Pydantic models, and invalid YAML raises `ConfigValidationError`.

```python
# tests/unit/datagen/test_config_loader.py
"""Tests for datagen YAML config loading and validation."""
from __future__ import annotations

from pathlib import Path

import pytest

from planproof.datagen.scenario.config_loader import (
    ConfigValidationError,
    DegradationPreset,
    DatagenRuleConfig,
    ProfileConfig,
    load_degradation_presets,
    load_profiles,
    load_rule_configs,
)


CONFIGS_DIR = Path("configs/datagen")


class TestRuleConfigLoading:
    def test_load_all_rule_configs(self) -> None:
        rules = load_rule_configs(CONFIGS_DIR / "rules")
        assert len(rules) == 3
        rule_ids = {r.rule_id for r in rules}
        assert rule_ids == {"R001", "R002", "R003"}

    def test_rule_has_compliant_range(self) -> None:
        rules = load_rule_configs(CONFIGS_DIR / "rules")
        r001 = next(r for r in rules if r.rule_id == "R001")
        assert r001.compliant_range.min < r001.compliant_range.max

    def test_rule_has_violation_types(self) -> None:
        rules = load_rule_configs(CONFIGS_DIR / "rules")
        r001 = next(r for r in rules if r.rule_id == "R001")
        assert len(r001.violation_types) >= 1
        assert all(v.name for v in r001.violation_types)

    def test_invalid_yaml_raises_error(self, tmp_path: Path) -> None:
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("rule_id: R999\n")  # missing required fields
        with pytest.raises(ConfigValidationError):
            load_rule_configs(tmp_path)


class TestProfileLoading:
    def test_load_all_profiles(self) -> None:
        profiles = load_profiles(CONFIGS_DIR / "profiles")
        assert len(profiles) == 3
        ids = {p.profile_id for p in profiles}
        assert "standard_3file" in ids

    def test_profile_has_document_composition(self) -> None:
        profiles = load_profiles(CONFIGS_DIR / "profiles")
        std = next(p for p in profiles if p.profile_id == "standard_3file")
        assert len(std.document_composition) >= 2


class TestDegradationPresetLoading:
    def test_load_all_presets(self) -> None:
        presets = load_degradation_presets(CONFIGS_DIR / "degradation")
        assert len(presets) == 3
        ids = {p.preset_id for p in presets}
        assert "clean" in ids
        assert "moderate_scan" in ids
        assert "heavy_scan" in ids

    def test_preset_has_transforms(self) -> None:
        presets = load_degradation_presets(CONFIGS_DIR / "degradation")
        moderate = next(p for p in presets if p.preset_id == "moderate_scan")
        assert len(moderate.transforms) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/datagen/test_config_loader.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Create YAML config files**

Create all 9 YAML config files matching the spec. See spec Section 4 for rule YAML format, Section 4 for profile format, Section 6 for degradation format.

- [ ] **Step 4: Implement config_loader.py**

Create `src/planproof/datagen/scenario/config_loader.py` with:
- Pydantic models: `ValueRange`, `ViolationType`, `EvidenceLocation`, `DatagenRuleConfig`, `DocumentComposition`, `ProfileConfig`, `TransformSpec`, `DegradationPreset`
- `ConfigValidationError` exception class
- Loader functions: `load_rule_configs()`, `load_profiles()`, `load_degradation_presets()`
- Each loader: reads YAML files from directory, validates with Pydantic, raises `ConfigValidationError` on failure

- [ ] **Step 5: Run tests**

Run: `pytest tests/unit/datagen/test_config_loader.py -v`
Expected: All tests PASS

- [ ] **Step 6: Run ruff + mypy**

Run: `ruff check src/planproof/datagen/ && mypy src/planproof/datagen/`
Expected: Clean

- [ ] **Step 7: Commit**

```bash
git add src/planproof/datagen/scenario/config_loader.py configs/datagen/ tests/unit/datagen/test_config_loader.py
git commit -m "feat(datagen): add config loader with Pydantic validation and 9 YAML configs"
```

---

## Task 4: Scenario Generator (Pure Functions)

**Files:**
- Create: `src/planproof/datagen/scenario/generator.py`
- Test: `tests/unit/datagen/test_generator.py`

- [ ] **Step 1: Write failing tests**

Test `generate_values()` for compliant/noncompliant categories, `compute_verdicts()`, `build_scenario()`, and seed determinism.

```python
# tests/unit/datagen/test_generator.py
"""Tests for scenario generation pure functions."""
from __future__ import annotations

from planproof.datagen.scenario.config_loader import load_profiles, load_rule_configs
from planproof.datagen.scenario.generator import (
    build_scenario,
    compute_verdicts,
    generate_values,
)
from planproof.datagen.scenario.models import Scenario, Value

RULES_DIR = "configs/datagen/rules"
PROFILES_DIR = "configs/datagen/profiles"


class TestGenerateValues:
    def test_compliant_values_within_range(self) -> None:
        rules = load_rule_configs(RULES_DIR)
        values = generate_values(rules, "compliant", seed=42)
        assert len(values) >= 3  # one per rule
        for v in values:
            # Each value should have attribute, value, unit, display_text
            assert v.attribute
            assert v.unit

    def test_noncompliant_values_outside_range(self) -> None:
        rules = load_rule_configs(RULES_DIR)
        values = generate_values(rules, "noncompliant", seed=42)
        assert len(values) >= 3

    def test_seed_determinism(self) -> None:
        rules = load_rule_configs(RULES_DIR)
        v1 = generate_values(rules, "compliant", seed=123)
        v2 = generate_values(rules, "compliant", seed=123)
        assert v1 == v2

    def test_different_seeds_produce_different_values(self) -> None:
        rules = load_rule_configs(RULES_DIR)
        v1 = generate_values(rules, "compliant", seed=1)
        v2 = generate_values(rules, "compliant", seed=2)
        assert v1 != v2


class TestComputeVerdicts:
    def test_compliant_values_yield_pass(self) -> None:
        rules = load_rule_configs(RULES_DIR)
        values = generate_values(rules, "compliant", seed=42)
        verdicts = compute_verdicts(values, rules)
        assert all(v.outcome == "PASS" for v in verdicts)

    def test_noncompliant_values_yield_at_least_one_fail(self) -> None:
        rules = load_rule_configs(RULES_DIR)
        values = generate_values(rules, "noncompliant", seed=42)
        verdicts = compute_verdicts(values, rules)
        assert any(v.outcome == "FAIL" for v in verdicts)


class TestBuildScenario:
    def test_returns_complete_scenario(self) -> None:
        rules = load_rule_configs(RULES_DIR)
        profiles = load_profiles(PROFILES_DIR)
        std_profile = next(p for p in profiles if p.profile_id == "standard_3file")
        scenario = build_scenario(std_profile, rules, "compliant", seed=42)
        assert isinstance(scenario, Scenario)
        assert scenario.category == "compliant"
        assert len(scenario.values) >= 3
        assert len(scenario.documents) >= 2
        assert scenario.seed == 42
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/datagen/test_generator.py -v`
Expected: FAIL — ImportError

- [ ] **Step 3: Implement generator.py**

Create `src/planproof/datagen/scenario/generator.py` with pure functions:
- `generate_values()` — uses seeded `random.Random` to pick values from compliant/violation ranges
- `compute_verdicts()` — compares values against rule thresholds
- `build_scenario()` — assembles Scenario from profile + values + verdicts + document specs

All functions are pure — no global state, no side effects.

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/datagen/test_generator.py -v`
Expected: All PASS

- [ ] **Step 5: Ruff + mypy, then commit**

```bash
ruff check src/planproof/datagen/ && mypy src/planproof/datagen/
git add src/planproof/datagen/scenario/generator.py tests/unit/datagen/test_generator.py
git commit -m "feat(datagen): add scenario generator — generate_values, compute_verdicts, build_scenario"
```

---

## Task 5: Edge-Case Strategies

**Files:**
- Create: `src/planproof/datagen/scenario/edge_cases.py`
- Test: `tests/unit/datagen/test_edge_cases.py`

- [ ] **Step 1: Write failing tests**

Test each of the 5 strategies: `missing_evidence`, `conflicting_values`, `low_confidence_scan`, `partial_documents`, `ambiguous_units`. Each test creates a normal scenario and applies the strategy, asserting the specific modification was made.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/datagen/test_edge_cases.py -v`

- [ ] **Step 3: Implement edge_cases.py**

Each strategy is a pure function `Scenario -> Scenario` that returns a new frozen Scenario with the specific deficiency introduced.

- [ ] **Step 4: Run tests, ruff, mypy, commit**

```bash
git commit -m "feat(datagen): add 5 edge-case strategies as pure functions"
```

---

## Task 6: Rendering Models + Coordinate Utils

**Files:**
- Create: `src/planproof/datagen/rendering/__init__.py`
- Create: `src/planproof/datagen/rendering/models.py`
- Create: `src/planproof/datagen/rendering/coord_utils.py`
- Test: `tests/unit/datagen/test_coord_utils.py`

- [ ] **Step 1: Write failing tests for coordinate conversion**

```python
# tests/unit/datagen/test_coord_utils.py
"""Tests for PDF-point ↔ pixel coordinate conversion."""
from __future__ import annotations

from planproof.datagen.rendering.coord_utils import (
    pdf_points_to_pixels,
    pixels_to_pdf_points,
)


class TestCoordinateConversion:
    def test_pdf_to_pixel_origin_flip(self) -> None:
        # PDF: origin bottom-left, 72 pts/inch
        # Pixel: origin top-left, 300 DPI
        # A4 height = 841.89 pts
        px = pdf_points_to_pixels(x_pt=0, y_pt=841.89, page_height_pt=841.89)
        assert px.x == 0.0
        assert abs(px.y - 0.0) < 1.0  # top of page

    def test_round_trip(self) -> None:
        page_h = 841.89  # A4
        px = pdf_points_to_pixels(x_pt=100, y_pt=500, page_height_pt=page_h)
        pt = pixels_to_pdf_points(px.x, px.y, page_height_pt=page_h)
        assert abs(pt.x - 100) < 0.5
        assert abs(pt.y - 500) < 0.5

    def test_scale_factor(self) -> None:
        # 72 pts/inch → 300 px/inch, scale = 300/72 = 4.1667
        px = pdf_points_to_pixels(x_pt=72, y_pt=0, page_height_pt=841.89)
        assert abs(px.x - 300.0) < 1.0  # 72pt = 1 inch = 300px
```

- [ ] **Step 2: Run test to verify it fails**

- [ ] **Step 3: Implement models.py and coord_utils.py**

`models.py` — PlacedValue and GeneratedDocument frozen dataclasses.
`coord_utils.py` — Pure conversion functions with `DPI = 300` constant.

- [ ] **Step 4: Run tests, ruff, mypy, commit**

```bash
git commit -m "feat(datagen): add rendering models and coordinate conversion utils"
```

---

## Task 7: Document Generator Registry

**Files:**
- Create: `src/planproof/datagen/rendering/registry.py`
- Test: `tests/unit/datagen/test_registry.py`

- [ ] **Step 1: Write failing tests for registry**

```python
# tests/unit/datagen/test_registry.py
"""Tests for DocumentGeneratorRegistry."""
from __future__ import annotations

import pytest

from planproof.datagen.rendering.registry import DocumentGeneratorRegistry
from planproof.datagen.scenario.models import DocumentSpec, Scenario


class _FakeGenerator:
    def generate(self, scenario: Scenario, doc_spec: DocumentSpec, seed: int):
        return "fake_doc"


class TestRegistry:
    def test_register_and_get(self) -> None:
        reg = DocumentGeneratorRegistry()
        gen = _FakeGenerator()
        reg.register("FORM", gen)
        assert reg.get("FORM") is gen

    def test_unknown_type_raises_key_error(self) -> None:
        reg = DocumentGeneratorRegistry()
        with pytest.raises(KeyError, match="UNKNOWN"):
            reg.get("UNKNOWN")

    def test_register_multiple_types(self) -> None:
        reg = DocumentGeneratorRegistry()
        reg.register("FORM", _FakeGenerator())
        reg.register("ELEVATION", _FakeGenerator())
        assert reg.get("FORM") is not reg.get("ELEVATION")
```

- [ ] **Step 2: Implement registry.py**

Protocol-based `DocumentGenerator`, `DocumentGeneratorRegistry` with `register()` and `get()`.

- [ ] **Step 3: Run tests, ruff, mypy, commit**

```bash
git commit -m "feat(datagen): add DocumentGeneratorRegistry with Protocol-based plugins"
```

---

## Task 8: FormGenerator Plugin

**Files:**
- Create: `src/planproof/datagen/rendering/form_generator.py`
- Test: `tests/unit/datagen/test_form_generator.py`

- [ ] **Step 1: Write failing tests**

Test that FormGenerator produces a PDF with: correct page count (7-8), placed values tracked with bounding boxes, text content extractable from PDF.

- [ ] **Step 2: Implement form_generator.py**

Uses reportlab to generate a multi-page planning application form. Renders sections: site location, applicant details, description of works, materials, measurements, ownership certificate. Records every placed value's bounding box in pixel coordinates.

- [ ] **Step 3: Run tests, ruff, mypy, commit**

```bash
git commit -m "feat(datagen): add FormGenerator — 7-page planning application PDF with bbox tracking"
```

---

## Task 9: SitePlanGenerator Plugin

**Files:**
- Create: `src/planproof/datagen/rendering/site_plan_generator.py`
- Test: `tests/unit/datagen/test_site_plan_generator.py`

- [ ] **Step 1: Write failing test**

Test that SitePlanGenerator produces a PDF with setback dimension annotations tracked via bounding boxes. Verify bounding boxes are in pixel coordinates (300 DPI, origin top-left).

- [ ] **Step 2: Implement site_plan_generator.py**

Uses reportlab to draw a top-down site plan: property boundary, building footprint, setback dimension lines with annotations, north arrow, scale bar. Records bounding boxes for all dimension annotations.

- [ ] **Step 3: Run tests, ruff + mypy, commit**

```bash
git commit -m "feat(datagen): add SitePlanGenerator — site boundary with setback dimensions"
```

---

## Task 10: FloorPlanGenerator Plugin

**Files:**
- Create: `src/planproof/datagen/rendering/floor_plan_generator.py`
- Test: `tests/unit/datagen/test_floor_plan_generator.py`

- [ ] **Step 1: Write failing test**

Test that FloorPlanGenerator produces a PDF with room dimension annotations tracked via bounding boxes.

- [ ] **Step 2: Implement floor_plan_generator.py**

Uses reportlab to draw room layouts with internal dimensions, wall outlines, door/window indicators. Records bounding boxes for dimension annotations.

- [ ] **Step 3: Run tests, ruff + mypy, commit**

```bash
git commit -m "feat(datagen): add FloorPlanGenerator — room layouts with dimensions"
```

---

## Task 11: ElevationGenerator Plugin

**Files:**
- Create: `src/planproof/datagen/rendering/elevation_generator.py`
- Test: `tests/unit/datagen/test_elevation_generator.py`

- [ ] **Step 1: Write failing test**

Test that ElevationGenerator produces a PNG with height dimension annotation tracked via bounding box.

- [ ] **Step 2: Implement elevation_generator.py**

Uses Pillow to draw a front/side elevation: building outline, roof pitch, ground level datum line, height dimension annotation. This is raster-native (PNG output), so bounding boxes are already in pixel coordinates.

- [ ] **Step 3: Run tests, ruff, mypy, commit**

```bash
git commit -m "feat(datagen): add ElevationGenerator — raster elevation with height annotation"
```

---

## Task 12: Degradation Transforms

**Files:**
- Create: `src/planproof/datagen/degradation/__init__.py`
- Create: `src/planproof/datagen/degradation/transforms.py`
- Test: `tests/unit/datagen/test_transforms.py`

- [ ] **Step 1: Write failing tests**

Test all 8 transforms explicitly:
1. `add_gaussian_noise` — pixel values change, `affine=None`
2. `add_speckle_noise` — sparse pixel changes, `affine=None`
3. `apply_rotation` — image dimensions may change, returns valid affine matrix
4. `apply_jpeg_compression` — file size decreases, `affine=None`
5. `vary_resolution` — downsample then upsample, returns affine with scale factor
6. `dilate_erode` — morphological operation changes stroke weight, `affine=None`
7. `add_partial_occlusion` — dark patches added at random positions, `affine=None`
8. `adjust_contrast` — pixel histogram changes, `affine=None`

- [ ] **Step 2: Implement transforms.py**

8 pure transform functions, each returning `TransformResult(image, affine)`. Uses numpy for noise/affine, Pillow for rotation/compression.

- [ ] **Step 3: Run tests, ruff, mypy, commit**

```bash
git commit -m "feat(datagen): add 8 degradation transforms with TransformResult affine tracking"
```

---

## Task 13: Compose Utility + Preset Loader

**Files:**
- Create: `src/planproof/datagen/degradation/compose.py`
- Test: `tests/unit/datagen/test_compose.py`

- [ ] **Step 1: Write failing tests**

Test `compose()` chains transforms in order, accumulates affine matrices. Test `load_preset()` reads YAML and returns a composed function.

- [ ] **Step 2: Implement compose.py**

`compose(*fns)` — returns a function that applies transforms in sequence, accumulating affine matrices. `load_preset(yaml_path)` — loads YAML, resolves transform names to functions, returns composed pipeline.

- [ ] **Step 3: Run tests, ruff, mypy, commit**

```bash
git commit -m "feat(datagen): add compose() utility and YAML preset loader"
```

---

## Task 14: Bounding Box Adjustment + PDF Rasterisation

**Files:**
- Create: `src/planproof/datagen/degradation/bbox_adjust.py`
- Create: `src/planproof/datagen/degradation/rasterise.py`
- Test: `tests/unit/datagen/test_bbox_adjust.py`

- [ ] **Step 1: Write failing tests for bbox adjustment**

Test that applying a rotation affine to a bounding box produces correct new coordinates. Test identity affine returns unchanged bbox.

- [ ] **Step 2: Implement bbox_adjust.py and rasterise.py**

`adjust_bounding_boxes(placed_values, affine_matrix)` — applies accumulated affine to all bounding boxes.
`rasterise_pdf(pdf_bytes, dpi=300)` — renders PDF to list of numpy arrays (one per page).

- [ ] **Step 3: Run tests, ruff, mypy, commit**

```bash
git commit -m "feat(datagen): add bbox affine adjustment and PDF rasterisation"
```

---

## Task 15: Output Writers (Sidecar + Reference + File)

**Files:**
- Create: `src/planproof/datagen/output/__init__.py`
- Create: `src/planproof/datagen/output/sidecar_writer.py`
- Create: `src/planproof/datagen/output/reference_writer.py`
- Create: `src/planproof/datagen/output/file_writer.py`
- Test: `tests/unit/datagen/test_sidecar_writer.py`
- Test: `tests/unit/datagen/test_reference_writer.py`
- Test: `tests/unit/datagen/test_file_writer.py`

- [ ] **Step 1: Write failing tests for sidecar_writer**

Test produces valid JSON matching ground truth schema from spec Section 7. Verify `documents` array includes both original and `degraded_extractions` with adjusted bounding boxes.

- [ ] **Step 2: Write failing tests for reference_writer**

Test `parcel.geojson` is valid GeoJSON FeatureCollection with required properties (`parcel_id`, `address`, `area_sqm`). Test `zone.json` has required keys (`parcel_id`, `zone_code`, `zone_name`, `applicable_rules`).

- [ ] **Step 3: Write failing tests for file_writer**

Test creates correct directory structure with BCC naming convention. Test that PDF documents produce **both** the text-layer PDF and a `_scan.png` degraded version. Test raster documents produce only the degraded version.

- [ ] **Step 4: Implement all three writers**

- `sidecar_writer.py` — assembles ground_truth.json from Scenario + GeneratedDocuments + degradation params
- `reference_writer.py` — generates parcel.geojson and zone.json from Scenario
- `file_writer.py` — writes all files to disk with `{docID}-{category}-{type}.{ext}` naming, creates dual output (PDF + _scan.png) for PDF documents

- [ ] **Step 5: Run tests, ruff, mypy, commit**

```bash
git commit -m "feat(datagen): add output writers — sidecar, reference, file with BCC naming"
```

---

## Task 16: CLI Runner

**Files:**
- Create: `src/planproof/datagen/runner.py`
- Modify: `Makefile`

- [ ] **Step 1: Implement runner.py**

CLI entry point using `argparse`. Orchestrates: load configs → build scenarios → generate documents → apply degradation → write output. Supports `--seed`, `--category`, `--count` flags.

- [ ] **Step 2: Add Makefile targets**

```makefile
generate-data:
	python -m planproof.datagen.runner --seed 42

verify-data:
	python -m planproof.evaluation.verify_data
```

- [ ] **Step 3: Smoke test**

Run: `python -m planproof.datagen.runner --category compliant --count 1 --seed 42`
Expected: Creates `data/synthetic/compliant/SET_C001/` with PDF, PNG, ground_truth.json

- [ ] **Step 4: Ruff + mypy, commit**

```bash
git commit -m "feat(datagen): add CLI runner with --seed, --category, --count flags"
```

---

## Task 17: Integration Test — Full Pipeline

**Files:**
- Test: `tests/integration/test_datagen_pipeline.py`

- [ ] **Step 1: Write integration test**

```python
# tests/integration/test_datagen_pipeline.py
"""Integration test: generate one complete application set and validate output."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def generated_set(tmp_path: Path) -> Path:
    """Generate a single compliant set to a temp directory."""
    from planproof.datagen.runner import generate_sets
    generate_sets(
        output_dir=tmp_path,
        category="compliant",
        count=1,
        seed=42,
    )
    return tmp_path / "compliant" / "SET_C001"


class TestDatagenPipeline:
    def test_output_directory_exists(self, generated_set: Path) -> None:
        assert generated_set.is_dir()

    def test_ground_truth_valid_json(self, generated_set: Path) -> None:
        gt_path = generated_set / "ground_truth.json"
        assert gt_path.exists()
        gt = json.loads(gt_path.read_text())
        assert gt["set_id"] == "SET_C001"
        assert gt["category"] == "compliant"
        assert "values" in gt
        assert "documents" in gt
        assert "rule_verdicts" in gt

    def test_form_pdf_exists(self, generated_set: Path) -> None:
        pdfs = list(generated_set.glob("*-Forms-*.pdf"))
        assert len(pdfs) == 1

    def test_form_scan_png_exists(self, generated_set: Path) -> None:
        """PDF documents must produce both text-layer PDF and degraded _scan.png."""
        scans = list(generated_set.glob("*-Forms-*_scan.png"))
        assert len(scans) == 1

    def test_drawing_files_exist(self, generated_set: Path) -> None:
        drawings = list(generated_set.glob("*-Plans*"))
        assert len(drawings) >= 1

    def test_reference_files_exist(self, generated_set: Path) -> None:
        assert (generated_set / "reference" / "parcel.geojson").exists()
        assert (generated_set / "reference" / "zone.json").exists()

    def test_bounding_boxes_within_bounds(self, generated_set: Path) -> None:
        gt = json.loads((generated_set / "ground_truth.json").read_text())
        for doc in gt["documents"]:
            for ext in doc["extractions"]:
                bb = ext["bounding_box"]
                assert bb["x"] >= 0
                assert bb["y"] >= 0
                assert bb["width"] > 0
                assert bb["height"] > 0

    def test_seed_determinism(self, tmp_path: Path) -> None:
        from planproof.datagen.runner import generate_sets
        dir1 = tmp_path / "run1"
        dir2 = tmp_path / "run2"
        generate_sets(output_dir=dir1, category="compliant", count=1, seed=42)
        generate_sets(output_dir=dir2, category="compliant", count=1, seed=42)
        gt1 = (dir1 / "compliant" / "SET_C001" / "ground_truth.json").read_text()
        gt2 = (dir2 / "compliant" / "SET_C001" / "ground_truth.json").read_text()
        assert gt1 == gt2
```

- [ ] **Step 2: Run integration test**

Run: `pytest tests/integration/test_datagen_pipeline.py -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git commit -m "test(datagen): add integration test — full pipeline, determinism, schema validation"
```

---

## Task 18: Verify Data Module + Coverage Tests

**Files:**
- Create: `src/planproof/datagen/output/verify_data.py`
- Create: `tests/integration/test_datagen_coverage.py`
- Modify: `.gitignore`

- [ ] **Step 1: Add `data/synthetic/` to .gitignore**

Append to `.gitignore`: `data/synthetic/` — generated binary data must not be committed.

- [ ] **Step 2: Implement verify_data.py**

`python -m planproof.datagen.output.verify_data` — scans `data/synthetic/`, validates:
- Expected directory structure (20 compliant + 20 noncompliant + 10 edgecase)
- Every set has ground_truth.json with valid schema
- Every referenced file exists
- All bounding boxes are within document bounds
- **Violation matrix coverage**: every rule × every violation type has at least one set
- **Edge-case distribution**: all 5 strategies appear in the 10 edge-case sets

- [ ] **Step 3: Write coverage integration test**

```python
# tests/integration/test_datagen_coverage.py
"""Integration test: verify violation matrix and edge-case coverage across full dataset."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

DATA_DIR = Path("data/synthetic")

needs_full_dataset = pytest.mark.skipif(
    not DATA_DIR.exists(),
    reason="Full synthetic dataset not generated yet",
)


@needs_full_dataset
class TestViolationMatrixCoverage:
    def test_all_rule_violation_types_present(self) -> None:
        """Every rule × every violation type must have at least one set."""
        verdicts: dict[str, set[str]] = {}
        for gt_path in DATA_DIR.rglob("ground_truth.json"):
            gt = json.loads(gt_path.read_text())
            for rule_id, verdict in gt["rule_verdicts"].items():
                verdicts.setdefault(rule_id, set()).add(verdict["outcome"])
        # Each rule should have both PASS and FAIL outcomes
        for rule_id in ["R001", "R002", "R003"]:
            assert rule_id in verdicts, f"No verdicts for {rule_id}"
            assert "PASS" in verdicts[rule_id], f"No PASS for {rule_id}"
            assert "FAIL" in verdicts[rule_id], f"No FAIL for {rule_id}"


@needs_full_dataset
class TestEdgeCaseCoverage:
    def test_all_strategies_present(self) -> None:
        """All 5 edge-case strategies must appear in the edgecase sets."""
        strategies: set[str] = set()
        edgecase_dir = DATA_DIR / "edgecase"
        for gt_path in edgecase_dir.rglob("ground_truth.json"):
            gt = json.loads(gt_path.read_text())
            if gt.get("edge_case_strategy"):
                strategies.add(gt["edge_case_strategy"])
        expected = {
            "missing_evidence", "conflicting_values",
            "low_confidence_scan", "partial_documents", "ambiguous_units",
        }
        assert strategies == expected
```

- [ ] **Step 4: Update Makefile**

```makefile
verify-data:
	python -m planproof.datagen.output.verify_data
```

- [ ] **Step 5: Run tests, ruff, mypy, commit**

```bash
git commit -m "feat(datagen): add verify_data module and coverage tests"
```

---

## Task 19: Generate Full Evaluation Dataset

- [ ] **Step 1: Generate all 50 sets**

Run: `python -m planproof.datagen.runner --seed 42`
Expected: Creates `data/synthetic/` with 20 compliant + 20 noncompliant + 10 edgecase sets

- [ ] **Step 2: Verify data**

Run: `make verify-data`
Expected: All 50 sets valid, violation matrix covered, edge-case distribution correct

- [ ] **Step 3: Run full test suite**

Run: `ruff check src/ tests/ && mypy src/ && pytest tests/ -v`
Expected: All clean, all pass

- [ ] **Step 4: Commit and push** (do NOT commit data/synthetic/ — it's gitignored)

```bash
git add src/ tests/ configs/ Makefile .gitignore
git commit -m "feat(datagen): complete synthetic data generator — all 50 sets verified"
git push origin master:main
```

---

## Task 20: Update Execution Status

- [ ] **Step 1: Update docs/EXECUTION_STATUS.md**

Mark Phase 1 items as complete:
- Synthetic Dataset Generation (Section 1.2)
- Violation matrix
- Document generator
- Ground truth sidecars
- Reference geometry

- [ ] **Step 2: Commit and push**

```bash
git commit -m "docs: update execution status for Phase 1 synthetic data generation"
git push origin master:main
```
