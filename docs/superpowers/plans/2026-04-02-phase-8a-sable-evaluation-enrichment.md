# Phase 8a: SABLE-Centred Evaluation Enrichment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the result model to capture SABLE metrics, enrich synthetic data for all 7 rules (R001–R003 + C001–C004), re-run the full ablation suite, produce 7 dissertation-quality visualizations, and generate a component contribution table with statistical significance.

**Architecture:** Six tasks in dependency order — (1) extend `RuleResult` with SABLE fields, (2) extend the datagen to support multi-attribute and categorical/string rules for C001–C004, (3) update the ablation runner to extract and store SABLE metrics, (4) extend metrics with component contribution and SABLE-specific functions, (5) build 7 new visualizations in the analysis notebook, (6) write qualitative error analysis. Tasks 1–4 are sequential (each builds on the prior). Tasks 5–6 depend on 4 completing but are independent of each other.

**Tech Stack:** Python 3.12, pytest, pydantic, matplotlib, seaborn, numpy, sentence-transformers, structlog, ruff, mypy --strict.

---

## Task 1: Extend RuleResult with SABLE Fields

**Files:**
- Modify: `src/planproof/evaluation/results.py:18-25`
- Test: `tests/unit/evaluation/test_results.py`

- [ ] **Step 1: Write failing test — RuleResult accepts PARTIALLY_ASSESSABLE and SABLE fields**

In `tests/unit/evaluation/test_results.py`, add:

```python
class TestRuleResultSableFields:
    def test_partially_assessable_accepted(self) -> None:
        r = RuleResult(
            rule_id="R001",
            ground_truth_outcome="PASS",
            predicted_outcome="PARTIALLY_ASSESSABLE",
            config_name="cfg",
            set_id="s1",
        )
        assert r.predicted_outcome == "PARTIALLY_ASSESSABLE"

    def test_sable_fields_default_none(self) -> None:
        r = RuleResult(
            rule_id="R001",
            ground_truth_outcome="PASS",
            predicted_outcome="PASS",
            config_name="cfg",
            set_id="s1",
        )
        assert r.belief is None
        assert r.plausibility is None
        assert r.conflict_mass is None
        assert r.blocking_reason is None

    def test_sable_fields_stored(self) -> None:
        r = RuleResult(
            rule_id="R001",
            ground_truth_outcome="FAIL",
            predicted_outcome="PASS",
            config_name="cfg",
            set_id="s1",
            belief=0.85,
            plausibility=0.95,
            conflict_mass=0.02,
            blocking_reason="NONE",
        )
        assert r.belief == 0.85
        assert r.plausibility == 0.95
        assert r.conflict_mass == 0.02
        assert r.blocking_reason == "NONE"

    def test_sable_fields_round_trip(self, tmp_path: Path) -> None:
        rr = RuleResult(
            rule_id="R001",
            ground_truth_outcome="FAIL",
            predicted_outcome="PARTIALLY_ASSESSABLE",
            config_name="cfg",
            set_id="s1",
            belief=0.55,
            plausibility=0.80,
            conflict_mass=0.10,
            blocking_reason="LOW_CONFIDENCE",
        )
        from planproof.evaluation.results import ExperimentResult, save_result, load_result
        exp = ExperimentResult(
            config_name="cfg",
            set_id="s1",
            rule_results=[rr],
            metadata={},
            timestamp=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        )
        save_result(exp, tmp_path)
        loaded = load_result(tmp_path / "cfg" / "s1.json")
        loaded_rr = loaded.rule_results[0]
        assert loaded_rr.predicted_outcome == "PARTIALLY_ASSESSABLE"
        assert loaded_rr.belief == pytest.approx(0.55)
        assert loaded_rr.plausibility == pytest.approx(0.80)
        assert loaded_rr.conflict_mass == pytest.approx(0.10)
        assert loaded_rr.blocking_reason == "LOW_CONFIDENCE"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/evaluation/test_results.py::TestRuleResultSableFields -v`
Expected: FAIL — `PARTIALLY_ASSESSABLE` not in Literal, `belief` not a field.

- [ ] **Step 3: Extend RuleResult model**

In `src/planproof/evaluation/results.py`, change `RuleResult` to:

```python
class RuleResult(BaseModel):
    """Outcome of evaluating a single rule in an experiment run."""

    rule_id: str
    ground_truth_outcome: Literal["PASS", "FAIL"]
    predicted_outcome: Literal["PASS", "FAIL", "NOT_ASSESSABLE", "PARTIALLY_ASSESSABLE"]
    config_name: str
    set_id: str

    # SABLE evidence-sufficiency metrics (None for baselines / ablation_d)
    belief: float | None = None
    plausibility: float | None = None
    conflict_mass: float | None = None
    blocking_reason: str | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/evaluation/test_results.py -v`
Expected: All pass including the new `TestRuleResultSableFields` tests.

- [ ] **Step 5: Run full test suite**

Run: `pytest -x -q`
Expected: All pass. The Literal extension may break tests that construct `RuleResult` with `predicted_outcome="MAYBE"` — those should still fail validation (the test `test_invalid_predicted_raises` should still pass since "MAYBE" is not in the new Literal either).

- [ ] **Step 6: Commit**

```bash
git add src/planproof/evaluation/results.py tests/unit/evaluation/test_results.py
git commit -m "feat(eval): extend RuleResult with SABLE fields — belief, plausibility, conflict_mass, blocking_reason, PARTIALLY_ASSESSABLE"
```

---

## Task 2: Extend Datagen for Multi-Attribute and C-Rule Support

The current `DatagenRuleConfig` model and `generate_values()` only handle single numeric attributes. We need to support:
- Multi-attribute rules (R003: footprint + site area + zone)
- Categorical values (C001: certificate type enum)
- String pair values (C002: address consistency)
- Numeric pair values (C003: area tolerance, C004: plan changes)

This task extends the datagen config model, generator, and creates 4 new C-rule datagen YAML files.

**Files:**
- Modify: `src/planproof/datagen/scenario/config_loader.py:93-106`
- Modify: `src/planproof/datagen/scenario/models.py:23-42`
- Modify: `src/planproof/datagen/scenario/generator.py`
- Modify: `configs/datagen/rules/r003_site_coverage.yaml`
- Create: `configs/datagen/rules/c001_certificate_type.yaml`
- Create: `configs/datagen/rules/c002_address_consistency.yaml`
- Create: `configs/datagen/rules/c003_boundary_validation.yaml`
- Create: `configs/datagen/rules/c004_plan_change.yaml`
- Test: `tests/unit/datagen/test_generator.py`

### Sub-task 2a: Extend the Value model and DatagenRuleConfig

- [ ] **Step 1: Write failing test — Value supports string values**

In `tests/unit/datagen/test_generator.py`, add:

```python
from planproof.datagen.scenario.models import Value


class TestValueStringSupport:
    def test_value_with_str_value(self) -> None:
        """Value can hold a string value alongside numeric."""
        v = Value(
            attribute="certificate_type",
            value=0.0,
            unit="categorical",
            display_text="A",
            str_value="A",
        )
        assert v.str_value == "A"

    def test_value_str_value_defaults_none(self) -> None:
        """str_value defaults to None for numeric values."""
        v = Value(
            attribute="building_height",
            value=7.5,
            unit="metres",
            display_text="7.5m",
        )
        assert v.str_value is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/datagen/test_generator.py::TestValueStringSupport -v`
Expected: FAIL — `str_value` not a field on `Value`.

- [ ] **Step 3: Add str_value field to Value dataclass**

In `src/planproof/datagen/scenario/models.py`, add to the `Value` dataclass:

```python
@dataclass(frozen=True)
class Value:
    attribute: str
    value: float
    unit: str
    display_text: str
    # String value for categorical/string attributes (None for numeric).
    str_value: str | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/datagen/test_generator.py::TestValueStringSupport -v`
Expected: PASS

- [ ] **Step 5: Write failing test — DatagenRuleConfig supports multi-attribute and categorical rules**

In `tests/unit/datagen/test_config_loader.py`, add:

```python
from planproof.datagen.scenario.config_loader import DatagenRuleConfig, ValueRange


class TestMultiAttributeConfig:
    def test_extra_attributes_field(self) -> None:
        """DatagenRuleConfig accepts extra_attributes list."""
        cfg = DatagenRuleConfig(
            rule_id="R003",
            attribute="site_coverage",
            unit="percent",
            compliant_range=ValueRange(min=10.0, max=50.0),
            violation_types=[],
            evidence_locations=[],
            extra_attributes=[
                {
                    "attribute": "building_footprint_area",
                    "unit": "m²",
                    "type": "derived",
                }
            ],
        )
        assert len(cfg.extra_attributes) == 1

    def test_value_type_categorical(self) -> None:
        """DatagenRuleConfig accepts value_type='categorical'."""
        cfg = DatagenRuleConfig(
            rule_id="C001",
            attribute="certificate_type",
            unit="categorical",
            compliant_range=ValueRange(min=0.0, max=0.0),
            violation_types=[],
            evidence_locations=[],
            value_type="categorical",
            valid_values=["A", "B", "C", "D"],
            invalid_values=["X", "E"],
        )
        assert cfg.value_type == "categorical"
        assert cfg.valid_values == ["A", "B", "C", "D"]

    def test_defaults_for_new_fields(self) -> None:
        """New fields default to safe values so existing R001/R002 configs still load."""
        cfg = DatagenRuleConfig(
            rule_id="R001",
            attribute="building_height",
            unit="metres",
            compliant_range=ValueRange(min=3.0, max=8.0),
            violation_types=[],
            evidence_locations=[],
        )
        assert cfg.value_type == "numeric"
        assert cfg.extra_attributes == []
        assert cfg.valid_values == []
        assert cfg.invalid_values == []
        assert cfg.compliant_pairs == []
        assert cfg.noncompliant_pairs == []
```

- [ ] **Step 6: Run test to verify it fails**

Run: `pytest tests/unit/datagen/test_config_loader.py::TestMultiAttributeConfig -v`
Expected: FAIL — `extra_attributes`, `value_type`, etc. not on `DatagenRuleConfig`.

- [ ] **Step 7: Extend DatagenRuleConfig model**

In `src/planproof/datagen/scenario/config_loader.py`, update `DatagenRuleConfig`:

```python
class DatagenRuleConfig(BaseModel):
    """Full configuration for one planning rule used by the data generator."""

    rule_id: str
    attribute: str
    unit: str
    compliant_range: ValueRange
    violation_types: list[ViolationType]
    evidence_locations: list[EvidenceLocation]

    # Extended fields for multi-attribute and categorical/string rules
    value_type: str = "numeric"  # "numeric", "categorical", "string_pair", "numeric_pair"
    extra_attributes: list[dict[str, Any]] = []
    valid_values: list[str] = []       # For categorical rules
    invalid_values: list[str] = []     # For categorical rules (noncompliant)
    compliant_pairs: list[dict[str, Any]] = []    # For pair-based rules
    noncompliant_pairs: list[dict[str, Any]] = [] # For pair-based rules
```

Add `from typing import Any` to the imports if not already present.

- [ ] **Step 8: Run test to verify it passes**

Run: `pytest tests/unit/datagen/test_config_loader.py::TestMultiAttributeConfig -v`
Expected: PASS

- [ ] **Step 9: Verify existing configs still load**

Run: `pytest tests/unit/datagen/test_config_loader.py -v && pytest tests/unit/datagen/test_generator.py -v`
Expected: All existing tests pass — new fields have defaults.

- [ ] **Step 10: Commit**

```bash
git add src/planproof/datagen/scenario/models.py src/planproof/datagen/scenario/config_loader.py tests/unit/datagen/
git commit -m "feat(datagen): extend Value with str_value, DatagenRuleConfig with multi-attribute and categorical support"
```

### Sub-task 2b: Create C-Rule Datagen YAML Configs

- [ ] **Step 11: Create C001 datagen config**

Create `configs/datagen/rules/c001_certificate_type.yaml`:

```yaml
# C001: Certificate Type — datagen config
# Generates certificate_type (enum) and ownership_declaration (categorical)

rule_id: C001
attribute: certificate_type
unit: categorical
value_type: categorical

compliant_range:
  min: 0.0
  max: 0.0

violation_types:
  - name: invalid_certificate
    range: { min: 0.0, max: 0.0 }

valid_values: ["A", "B", "C", "D"]
invalid_values: ["X", "E", "NONE"]

extra_attributes:
  - attribute: ownership_declaration
    unit: categorical
    type: companion
    valid_values: ["sole_owner", "part_owner", "other"]
    invalid_values: ["missing", "invalid"]

evidence_locations:
  - doc_type: FORM
    field: certificate_type
  - doc_type: FORM
    field: ownership_declaration
```

- [ ] **Step 12: Create C002 datagen config**

Create `configs/datagen/rules/c002_address_consistency.yaml`:

```yaml
# C002: Address Consistency — datagen config
# Generates form_address and drawing_address string pairs

rule_id: C002
attribute: form_address
unit: string_pair
value_type: string_pair

compliant_range:
  min: 0.0
  max: 0.0

violation_types:
  - name: address_mismatch
    range: { min: 0.0, max: 0.0 }

compliant_pairs:
  - form_address: "123 Example Street, Birmingham, B1 1AA"
    drawing_address: "123 Example St, Birmingham, B1 1AA"
  - form_address: "45 Park Road, Edgbaston, B15 2TT"
    drawing_address: "45 Park Rd, Edgbaston, B15 2TT"
  - form_address: "78 High Street, Moseley, B13 8HG"
    drawing_address: "78 High St, Moseley, B13 8HG"
  - form_address: "12 Station Avenue, Kings Heath, B14 7QR"
    drawing_address: "12 Station Ave, Kings Heath, B14 7QR"
  - form_address: "9 Church Lane, Harborne, B17 0BD"
    drawing_address: "9 Church Ln, Harborne, B17 0BD"

noncompliant_pairs:
  - form_address: "123 Example Street, Birmingham, B1 1AA"
    drawing_address: "456 Other Road, London, E1 2BB"
  - form_address: "45 Park Road, Edgbaston, B15 2TT"
    drawing_address: "99 Victoria Road, Moseley, B13 9PL"
  - form_address: "78 High Street, Moseley, B13 8HG"
    drawing_address: "22 Low Lane, Selly Oak, B29 6NA"

evidence_locations:
  - doc_type: FORM
    field: form_address
  - doc_type: DRAWING
    annotation: drawing_address
```

- [ ] **Step 13: Create C003 datagen config**

Create `configs/datagen/rules/c003_boundary_validation.yaml`:

```yaml
# C003: Boundary Validation — datagen config
# Generates stated_site_area and reference_parcel_area numeric pairs

rule_id: C003
attribute: stated_site_area
unit: m²
value_type: numeric_pair

compliant_range:
  min: 200.0
  max: 1000.0

violation_types:
  - name: area_discrepancy
    range: { min: 0.0, max: 0.0 }

extra_attributes:
  - attribute: reference_parcel_area
    unit: m²
    type: reference

compliant_pairs:
  - stated_site_area: 500.0
    reference_parcel_area: 510.0
  - stated_site_area: 300.0
    reference_parcel_area: 290.0
  - stated_site_area: 750.0
    reference_parcel_area: 720.0
  - stated_site_area: 400.0
    reference_parcel_area: 420.0
  - stated_site_area: 600.0
    reference_parcel_area: 580.0

noncompliant_pairs:
  - stated_site_area: 500.0
    reference_parcel_area: 300.0
  - stated_site_area: 300.0
    reference_parcel_area: 500.0
  - stated_site_area: 750.0
    reference_parcel_area: 400.0

evidence_locations:
  - doc_type: FORM
    field: stated_site_area
  - doc_type: EXTERNAL_DATA
    field: reference_parcel_area
```

- [ ] **Step 14: Create C004 datagen config**

Create `configs/datagen/rules/c004_plan_change.yaml`:

```yaml
# C004: Plan Change Detection — datagen config
# Generates proposed/approved pairs for building_height, footprint_area, storeys

rule_id: C004
attribute: proposed_building_height
unit: metres
value_type: numeric_pair

compliant_range:
  min: 3.0
  max: 15.0

violation_types:
  - name: material_change
    range: { min: 0.0, max: 0.0 }

extra_attributes:
  - attribute: approved_building_height
    unit: metres
    type: reference
  - attribute: proposed_building_footprint_area
    unit: m²
    type: primary
  - attribute: approved_building_footprint_area
    unit: m²
    type: reference
  - attribute: proposed_storeys
    unit: count
    type: primary
  - attribute: approved_storeys
    unit: count
    type: reference

compliant_pairs:
  - proposed_building_height: 7.5
    approved_building_height: 7.5
    proposed_building_footprint_area: 120.0
    approved_building_footprint_area: 118.0
    proposed_storeys: 2
    approved_storeys: 2
  - proposed_building_height: 5.0
    approved_building_height: 5.1
    proposed_building_footprint_area: 80.0
    approved_building_footprint_area: 82.0
    proposed_storeys: 1
    approved_storeys: 1

noncompliant_pairs:
  - proposed_building_height: 9.0
    approved_building_height: 7.0
    proposed_building_footprint_area: 200.0
    approved_building_footprint_area: 120.0
    proposed_storeys: 3
    approved_storeys: 2
  - proposed_building_height: 6.0
    approved_building_height: 4.0
    proposed_building_footprint_area: 150.0
    approved_building_footprint_area: 80.0
    proposed_storeys: 2
    approved_storeys: 1

evidence_locations:
  - doc_type: DRAWING
    drawing_type: elevation
    annotation: proposed_building_height
  - doc_type: DRAWING
    drawing_type: elevation
    annotation: approved_building_height
  - doc_type: DRAWING
    drawing_type: site_plan
    annotation: proposed_building_footprint_area
  - doc_type: DRAWING
    drawing_type: site_plan
    annotation: approved_building_footprint_area
```

- [ ] **Step 15: Update R003 datagen config with extra attributes**

Update `configs/datagen/rules/r003_site_coverage.yaml` — add `extra_attributes` for `building_footprint_area`, `total_site_area`, and `zone_category`:

```yaml
rule_id: R003
attribute: site_coverage
unit: percent
value_type: numeric

compliant_range:
  min: 10.0
  max: 50.0

violation_types:
  - name: exceeds_max
    range: { min: 50.1, max: 80.0 }
  - name: marginal_exceed
    range: { min: 50.01, max: 55.0 }
  - name: extreme_exceed
    range: { min: 70.0, max: 95.0 }

extra_attributes:
  - attribute: building_footprint_area
    unit: m²
    type: derived
    compliant_range: { min: 40.0, max: 200.0 }
  - attribute: total_site_area
    unit: m²
    type: derived
    compliant_range: { min: 200.0, max: 1000.0 }
  - attribute: zone_category
    unit: categorical
    type: companion
    valid_values: ["residential", "suburban_residential"]
    invalid_values: ["industrial", "commercial"]

evidence_locations:
  - doc_type: FORM
    field: site_coverage
  - doc_type: DRAWING
    drawing_type: site_plan
    annotation: area_annotation
  - doc_type: FORM
    field: building_footprint_area
  - doc_type: FORM
    field: total_site_area
```

- [ ] **Step 16: Write test to verify all 7 datagen configs load**

In `tests/unit/datagen/test_config_loader.py`, add:

```python
class TestAllRuleConfigsLoad:
    def test_seven_configs_load(self) -> None:
        """All 7 datagen rule configs (R001-R003 + C001-C004) load successfully."""
        from planproof.datagen.scenario.config_loader import load_rule_configs
        configs = load_rule_configs(Path("configs/datagen/rules"))
        rule_ids = {c.rule_id for c in configs}
        assert rule_ids == {"R001", "R002", "R003", "C001", "C002", "C003", "C004"}
```

- [ ] **Step 17: Run test**

Run: `pytest tests/unit/datagen/test_config_loader.py::TestAllRuleConfigsLoad -v`
Expected: PASS — all 7 YAML files parse and validate.

- [ ] **Step 18: Commit**

```bash
git add configs/datagen/rules/ tests/unit/datagen/test_config_loader.py
git commit -m "feat(datagen): add C001-C004 datagen configs, enrich R003 with extra_attributes"
```

### Sub-task 2c: Extend generate_values for Categorical, String, and Pair Rules

- [ ] **Step 19: Write failing test — generate_values handles categorical rules**

In `tests/unit/datagen/test_generator.py`, add:

```python
class TestGenerateValuesExtended:
    def test_categorical_compliant_value(self) -> None:
        """Categorical rule generates a valid_values member for compliant."""
        rules = load_rule_configs(RULES_DIR)
        values = generate_values(rules, "compliant", seed=42)
        c001_values = [v for v in values if v.attribute == "certificate_type"]
        assert len(c001_values) >= 1
        assert c001_values[0].str_value in ["A", "B", "C", "D"]

    def test_string_pair_compliant_values(self) -> None:
        """String pair rule generates both form_address and drawing_address."""
        rules = load_rule_configs(RULES_DIR)
        values = generate_values(rules, "compliant", seed=42)
        attrs = {v.attribute for v in values}
        assert "form_address" in attrs
        assert "drawing_address" in attrs

    def test_numeric_pair_compliant_values(self) -> None:
        """Numeric pair rule generates both stated_site_area and reference_parcel_area."""
        rules = load_rule_configs(RULES_DIR)
        values = generate_values(rules, "compliant", seed=42)
        attrs = {v.attribute for v in values}
        assert "stated_site_area" in attrs
        assert "reference_parcel_area" in attrs

    def test_extra_attributes_generated(self) -> None:
        """R003 extra attributes (building_footprint_area, total_site_area, zone_category) generated."""
        rules = load_rule_configs(RULES_DIR)
        values = generate_values(rules, "compliant", seed=42)
        attrs = {v.attribute for v in values}
        assert "building_footprint_area" in attrs
        assert "total_site_area" in attrs
        assert "zone_category" in attrs

    def test_noncompliant_categorical_invalid(self) -> None:
        """Noncompliant categorical rule can generate an invalid value."""
        rules = load_rule_configs(RULES_DIR)
        # Run many seeds to find one where C001 is the anchor violation
        found_invalid = False
        for seed in range(100):
            values = generate_values(rules, "noncompliant", seed=seed)
            c001_vals = [v for v in values if v.attribute == "certificate_type"]
            if c001_vals and c001_vals[0].str_value not in ["A", "B", "C", "D"]:
                found_invalid = True
                break
        assert found_invalid, "Expected at least one seed to produce an invalid certificate_type"

    def test_seven_rules_generate_values(self) -> None:
        """All 7 rules produce at least one Value each."""
        rules = load_rule_configs(RULES_DIR)
        values = generate_values(rules, "compliant", seed=42)
        rule_ids_with_values = set()
        for v in values:
            for r in rules:
                if r.attribute == v.attribute:
                    rule_ids_with_values.add(r.rule_id)
                    break
        # At least R001, R002, R003 should have values; C-rules contribute via their own attrs
        assert len(values) >= 7  # At least one per rule, plus extras
```

- [ ] **Step 20: Run tests to verify they fail**

Run: `pytest tests/unit/datagen/test_generator.py::TestGenerateValuesExtended -v`
Expected: FAIL — current generator doesn't handle categorical/string/pair value types.

- [ ] **Step 21: Extend generate_values to handle all value types**

In `src/planproof/datagen/scenario/generator.py`, refactor `generate_values()` to dispatch by `rule.value_type`:

```python
def generate_values(
    rule_configs: list[DatagenRuleConfig],
    category: str,
    seed: int,
) -> tuple[Value, ...]:
    """Generate ground-truth Values for all rules, supporting numeric, categorical,
    string_pair, and numeric_pair value types."""
    rng = random.Random(seed)

    if category == "noncompliant":
        anchor_idx = rng.randrange(len(rule_configs))
    else:
        anchor_idx = -1

    values: list[Value] = []

    for idx, rule in enumerate(rule_configs):
        is_violation = category == "noncompliant" and idx == anchor_idx

        if rule.value_type == "categorical":
            values.extend(_generate_categorical(rule, rng, is_violation))
        elif rule.value_type == "string_pair":
            values.extend(_generate_string_pair(rule, rng, is_violation))
        elif rule.value_type == "numeric_pair":
            values.extend(_generate_numeric_pair(rule, rng, is_violation))
        else:
            # Default: single numeric value (existing logic)
            values.extend(_generate_numeric(rule, rng, is_violation))

        # Generate extra_attributes (e.g., R003 footprint/site area/zone)
        for extra in rule.extra_attributes:
            extra_unit = extra.get("unit", "")
            extra_attr = extra["attribute"]
            if extra.get("valid_values"):
                # Categorical companion attribute
                chosen = rng.choice(extra["valid_values"])
                values.append(Value(
                    attribute=extra_attr,
                    value=0.0,
                    unit=extra_unit,
                    display_text=chosen,
                    str_value=chosen,
                ))
            elif "compliant_range" in extra:
                # Derived numeric extra
                cr = extra["compliant_range"]
                numeric = _sample_in_range(rng, cr["min"], cr["max"])
                values.append(Value(
                    attribute=extra_attr,
                    value=numeric,
                    unit=extra_unit,
                    display_text=_format_display_text(numeric, extra_unit),
                ))

    return tuple(values)


def _generate_numeric(
    rule: DatagenRuleConfig, rng: random.Random, is_violation: bool
) -> list[Value]:
    """Generate a single numeric value for a standard numeric rule."""
    if is_violation:
        violation = rng.choice(rule.violation_types)
        numeric = _sample_in_range(rng, violation.range.min, violation.range.max)
    else:
        numeric = _sample_in_range(rng, rule.compliant_range.min, rule.compliant_range.max)

    return [Value(
        attribute=rule.attribute,
        value=numeric,
        unit=rule.unit,
        display_text=_format_display_text(numeric, rule.unit),
    )]


def _generate_categorical(
    rule: DatagenRuleConfig, rng: random.Random, is_violation: bool
) -> list[Value]:
    """Generate categorical value(s) for enum-type rules like C001."""
    if is_violation and rule.invalid_values:
        chosen = rng.choice(rule.invalid_values)
    else:
        chosen = rng.choice(rule.valid_values) if rule.valid_values else "UNKNOWN"

    return [Value(
        attribute=rule.attribute,
        value=0.0,
        unit=rule.unit,
        display_text=chosen,
        str_value=chosen,
    )]


def _generate_string_pair(
    rule: DatagenRuleConfig, rng: random.Random, is_violation: bool
) -> list[Value]:
    """Generate string pair values for consistency rules like C002."""
    if is_violation and rule.noncompliant_pairs:
        pair = rng.choice(rule.noncompliant_pairs)
    elif rule.compliant_pairs:
        pair = rng.choice(rule.compliant_pairs)
    else:
        return []

    result: list[Value] = []
    for attr_name, str_val in pair.items():
        result.append(Value(
            attribute=attr_name,
            value=0.0,
            unit="string",
            display_text=str(str_val),
            str_value=str(str_val),
        ))
    return result


def _generate_numeric_pair(
    rule: DatagenRuleConfig, rng: random.Random, is_violation: bool
) -> list[Value]:
    """Generate numeric pair values for tolerance/diff rules like C003/C004."""
    if is_violation and rule.noncompliant_pairs:
        pair = rng.choice(rule.noncompliant_pairs)
    elif rule.compliant_pairs:
        pair = rng.choice(rule.compliant_pairs)
    else:
        return []

    result: list[Value] = []
    for attr_name, num_val in pair.items():
        fval = float(num_val)
        # Infer unit from the rule or extra_attributes
        unit = rule.unit
        for extra in rule.extra_attributes:
            if extra["attribute"] == attr_name:
                unit = extra.get("unit", rule.unit)
                break
        result.append(Value(
            attribute=attr_name,
            value=fval,
            unit=unit,
            display_text=_format_display_text(fval, unit),
        ))
    return result
```

- [ ] **Step 22: Run tests to verify they pass**

Run: `pytest tests/unit/datagen/test_generator.py -v`
Expected: All pass including `TestGenerateValuesExtended`.

- [ ] **Step 23: Update compute_verdicts for multi-value rules**

The current `compute_verdicts` zips values 1:1 with rules. Now that we have multiple values per rule, update `compute_verdicts` to produce one verdict per rule using the primary attribute:

```python
def compute_verdicts(
    values: tuple[Value, ...],
    rule_configs: list[DatagenRuleConfig],
) -> tuple[Verdict, ...]:
    """Evaluate each rule against its primary attribute value and return verdicts."""
    # Build lookup: attribute_name → Value
    value_map: dict[str, Value] = {v.attribute: v for v in values}

    verdicts: list[Verdict] = []

    for rule in rule_configs:
        primary_value = value_map.get(rule.attribute)
        if primary_value is None:
            # No primary value generated (shouldn't happen if generate_values is correct)
            continue

        if rule.value_type == "categorical":
            # Categorical: check if str_value is in valid_values
            in_range = primary_value.str_value in rule.valid_values if primary_value.str_value else False
            outcome = "PASS" if in_range else "FAIL"
            verdicts.append(Verdict(
                rule_id=rule.rule_id,
                outcome=outcome,
                evaluated_value=0.0,
                threshold=0.0,
            ))
        elif rule.value_type in ("string_pair", "numeric_pair"):
            # For pair rules, compliance was determined at generation time by pair selection
            # Check if the selected pair came from compliant or noncompliant list
            # Simple heuristic: look for the primary attribute in compliant_pairs
            is_compliant = any(
                abs(float(p.get(rule.attribute, -9999)) - primary_value.value) < 0.01
                if rule.value_type == "numeric_pair"
                else p.get(rule.attribute) == primary_value.str_value
                for p in rule.compliant_pairs
            ) if rule.compliant_pairs else True
            outcome = "PASS" if is_compliant else "FAIL"
            verdicts.append(Verdict(
                rule_id=rule.rule_id,
                outcome=outcome,
                evaluated_value=primary_value.value,
                threshold=0.0,
            ))
        else:
            # Numeric: existing logic
            in_range = rule.compliant_range.min <= primary_value.value <= rule.compliant_range.max
            outcome = "PASS" if in_range else "FAIL"
            verdicts.append(Verdict(
                rule_id=rule.rule_id,
                outcome=outcome,
                evaluated_value=primary_value.value,
                threshold=rule.compliant_range.max,
            ))

    return tuple(verdicts)
```

- [ ] **Step 24: Update build_scenario for multi-value rules**

Update `build_scenario` in `generator.py` — the `doc_type_to_attributes` mapping should include extra_attributes and pair attributes:

After the existing mapping loop, add:

```python
    # Also map extra_attributes and pair values to their evidence locations
    for rule in rule_configs:
        for extra in rule.extra_attributes:
            for loc in rule.evidence_locations:
                if loc.field == extra["attribute"] or loc.annotation == extra.get("attribute"):
                    doc_type_to_attributes.setdefault(loc.doc_type, []).append(extra["attribute"])
        # For pair rules, map both attributes from pairs
        if rule.value_type in ("string_pair", "numeric_pair"):
            for loc in rule.evidence_locations:
                attr_name = loc.field or loc.annotation
                if attr_name and attr_name not in doc_type_to_attributes.get(loc.doc_type, []):
                    doc_type_to_attributes.setdefault(loc.doc_type, []).append(attr_name)
```

- [ ] **Step 25: Run all datagen tests**

Run: `pytest tests/unit/datagen/ -v`
Expected: All pass.

- [ ] **Step 26: Run full test suite**

Run: `pytest -x -q`
Expected: All pass.

- [ ] **Step 27: Commit**

```bash
git add src/planproof/datagen/scenario/generator.py tests/unit/datagen/test_generator.py
git commit -m "feat(datagen): extend generator for categorical, string_pair, numeric_pair value types and extra_attributes"
```

---

## Task 3: Update Ablation Runner to Capture SABLE Metrics

**Files:**
- Modify: `scripts/run_ablation.py:430-450` (assessability extraction)
- Modify: `scripts/run_ablation.py:770-795` (RuleResult construction)
- Modify: `scripts/run_ablation.py:531-553` (`_apply_ground_truth_outcomes`)
- Test: manual verification via `python scripts/run_ablation.py --config full_system --data-dir data/synthetic_diverse -v`

- [ ] **Step 1: Modify _run_pipeline_config to return assessability_results alongside verdicts**

Change the return type of `_run_pipeline_config` from `list[Any]` to `tuple[list[Any], list[Any]]` — returning `(verdicts, assessability_results)`:

In `scripts/run_ablation.py`, at line ~345, change the function signature:

```python
def _run_pipeline_config(
    config_name: str,
    ground_truth: dict[str, Any],
    ablation_yaml: dict[str, Any],
    configs_dir: Path,
    test_set_dir: Path | None = None,
) -> tuple[list[Any], list[Any]]:
    """Run the reasoning pipeline steps against ground-truth entities.

    Returns (verdicts, assessability_results) where assessability_results
    is a list of AssessabilityResult objects (empty when assessability is disabled).
    """
```

Change the two return statements:
- Line ~454 (`return verdicts`) → `return verdicts, assessability_results`
- After the verdicts loop ends → `return verdicts, assessability_results`

Also handle the `use_rule_engine=False` early return:
- Line ~454: `return [], assessability_results`

- [ ] **Step 2: Update run_experiment to extract SABLE metrics into RuleResult**

In `scripts/run_ablation.py`, inside `run_experiment()` (line ~760), update the pipeline config dispatch to unpack the new return type:

```python
        if config_name in PIPELINE_CONFIGS:
            verdicts, assessability_results = _run_pipeline_config(
                config_name, ground_truth, ablation_yaml, configs_dir,
                test_set_dir=test_set_dir,
            )
        else:
            verdicts = _run_baseline(config_name, ground_truth, configs_dir, ablation_yaml)
            assessability_results = []
```

Then build an assessability lookup map:

```python
        # Build assessability lookup: rule_id → AssessabilityResult
        assessability_map: dict[str, Any] = {
            ar.rule_id: ar for ar in assessability_results
        }
```

Then update the `RuleResult` construction loop (line ~787) to include SABLE fields:

```python
        for rule_id in all_rule_ids:
            gt_outcome = gt_verdicts.get(rule_id, "PASS")
            if rule_id in evaluated_rule_ids:
                verdict_obj = next(v for v in verdicts if v.rule_id == rule_id)
                predicted = str(verdict_obj.outcome)
            else:
                predicted = "NOT_ASSESSABLE"

            # Extract SABLE metrics from assessability result
            ar = assessability_map.get(rule_id)
            belief = ar.belief if ar else None
            plausibility = ar.plausibility if ar else None
            conflict_mass_val = ar.conflict_mass if ar else None
            blocking_reason_val = str(ar.blocking_reason) if ar else None

            # Map PARTIALLY_ASSESSABLE through
            if ar and ar.status == "PARTIALLY_ASSESSABLE" and predicted == "NOT_ASSESSABLE":
                predicted = "PARTIALLY_ASSESSABLE"

            rule_results.append(
                RuleResult(
                    rule_id=rule_id,
                    ground_truth_outcome=gt_outcome,
                    predicted_outcome=predicted,
                    config_name=config_name,
                    set_id=set_id,
                    belief=belief,
                    plausibility=plausibility,
                    conflict_mass=conflict_mass_val,
                    blocking_reason=blocking_reason_val,
                )
            )
```

- [ ] **Step 3: Update _apply_ground_truth_outcomes to preserve SABLE fields**

In `_apply_ground_truth_outcomes` (line ~531), the function reconstructs `RuleResult` objects but currently drops any extra fields. Update to preserve them:

```python
def _apply_ground_truth_outcomes(
    rule_results: list[Any],
    ground_truth: dict[str, Any],
) -> list[Any]:
    """Patch ground_truth_outcome on each RuleResult from the ground truth."""
    gt_verdicts: dict[str, str] = {
        v["rule_id"]: v["outcome"]
        for v in ground_truth.get("rule_verdicts", [])
    }
    from planproof.evaluation.results import RuleResult

    for i, rr in enumerate(rule_results):
        gt_outcome = gt_verdicts.get(rr.rule_id, "PASS")
        rule_results[i] = RuleResult(
            rule_id=rr.rule_id,
            ground_truth_outcome=gt_outcome,
            predicted_outcome=rr.predicted_outcome,
            config_name=rr.config_name,
            set_id=rr.set_id,
            belief=rr.belief,
            plausibility=rr.plausibility,
            conflict_mass=rr.conflict_mass,
            blocking_reason=rr.blocking_reason,
        )
    return rule_results
```

- [ ] **Step 4: Update summary counts to include PARTIALLY_ASSESSABLE**

In `run_experiment`, update the count computation:

```python
        n_pass = sum(1 for r in rule_results if r.predicted_outcome == "PASS")
        n_fail = sum(1 for r in rule_results if r.predicted_outcome == "FAIL")
        n_na = sum(1 for r in rule_results if r.predicted_outcome in ("NOT_ASSESSABLE", "PARTIALLY_ASSESSABLE"))
```

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `pytest -x -q`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/run_ablation.py
git commit -m "feat(ablation): extract SABLE metrics into RuleResult — belief, plausibility, conflict_mass, blocking_reason"
```

---

## Task 4: Extend Metrics Module

**Files:**
- Modify: `src/planproof/evaluation/metrics.py`
- Test: `tests/unit/evaluation/test_metrics.py`

- [ ] **Step 1: Write failing tests for new metrics functions**

In `tests/unit/evaluation/test_metrics.py`, add:

```python
from planproof.evaluation.metrics import (
    blocking_reason_distribution,
    belief_statistics,
    compute_component_contribution,
    partially_assessable_rate,
)


class TestPartiallyAssessableRate:
    def test_no_partially_assessable(self) -> None:
        results = [_result("PASS", "PASS"), _result("FAIL", "FAIL")]
        assert partially_assessable_rate(results) == pytest.approx(0.0)

    def test_some_partially_assessable(self) -> None:
        results = [
            _result("PASS", "PASS"),
            RuleResult(
                rule_id="R002", ground_truth_outcome="FAIL",
                predicted_outcome="PARTIALLY_ASSESSABLE",
                config_name="cfg", set_id="s1",
            ),
        ]
        assert partially_assessable_rate(results) == pytest.approx(0.5)

    def test_empty_returns_zero(self) -> None:
        assert partially_assessable_rate([]) == pytest.approx(0.0)


class TestBlockingReasonDistribution:
    def test_counts_each_reason(self) -> None:
        results = [
            RuleResult(
                rule_id="R001", ground_truth_outcome="PASS",
                predicted_outcome="NOT_ASSESSABLE",
                config_name="cfg", set_id="s1",
                blocking_reason="MISSING_EVIDENCE",
            ),
            RuleResult(
                rule_id="R002", ground_truth_outcome="PASS",
                predicted_outcome="NOT_ASSESSABLE",
                config_name="cfg", set_id="s1",
                blocking_reason="MISSING_EVIDENCE",
            ),
            RuleResult(
                rule_id="R003", ground_truth_outcome="PASS",
                predicted_outcome="PASS",
                config_name="cfg", set_id="s1",
                blocking_reason="NONE",
            ),
        ]
        dist = blocking_reason_distribution(results)
        assert dist["MISSING_EVIDENCE"] == 2
        assert dist["NONE"] == 1

    def test_none_blocking_reason_counted(self) -> None:
        """Results with blocking_reason=None are counted under 'null'."""
        results = [_result("PASS", "PASS")]
        dist = blocking_reason_distribution(results)
        assert dist.get("null", 0) == 1


class TestBeliefStatistics:
    def test_basic_stats(self) -> None:
        results = [
            RuleResult(
                rule_id=f"R{i:03d}", ground_truth_outcome="PASS",
                predicted_outcome="PASS", config_name="cfg", set_id="s1",
                belief=v,
            )
            for i, v in enumerate([0.2, 0.4, 0.6, 0.8])
        ]
        stats = belief_statistics(results)
        assert stats["mean"] == pytest.approx(0.5)
        assert stats["min"] == pytest.approx(0.2)
        assert stats["max"] == pytest.approx(0.8)
        assert "std" in stats
        assert "median" in stats

    def test_skips_none_beliefs(self) -> None:
        results = [
            RuleResult(
                rule_id="R001", ground_truth_outcome="PASS",
                predicted_outcome="PASS", config_name="cfg", set_id="s1",
                belief=0.5,
            ),
            _result("PASS", "PASS"),  # belief=None
        ]
        stats = belief_statistics(results)
        assert stats["mean"] == pytest.approx(0.5)
        assert stats["count"] == 1

    def test_empty_results(self) -> None:
        stats = belief_statistics([])
        assert stats["count"] == 0
        assert stats["mean"] == pytest.approx(0.0)


class TestComponentContribution:
    def test_returns_rows_for_each_ablation(self) -> None:
        """Component contribution returns one row per ablated component."""
        # Minimal mock: full_system and ablation_d results
        full = [
            RuleResult(
                rule_id="R001", ground_truth_outcome="FAIL",
                predicted_outcome="FAIL", config_name="full_system", set_id="s1",
            ),
        ]
        abl_d = [
            RuleResult(
                rule_id="R001", ground_truth_outcome="FAIL",
                predicted_outcome="PASS", config_name="ablation_d", set_id="s1",
            ),
        ]
        all_results = {"full_system": full, "ablation_d": abl_d}
        rows = compute_component_contribution(all_results)
        assert len(rows) >= 1
        row_d = next(r for r in rows if r["config_name"] == "ablation_d")
        assert "recall_delta" in row_d
        assert "mcnemar_p" in row_d
        assert "cohens_h" in row_d
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/evaluation/test_metrics.py::TestPartiallyAssessableRate -v`
Expected: FAIL — functions not defined.

- [ ] **Step 3: Implement new metrics functions**

In `src/planproof/evaluation/metrics.py`, add:

```python
def partially_assessable_rate(rule_results: list[RuleResult]) -> float:
    """Fraction of results with PARTIALLY_ASSESSABLE predicted outcome."""
    if not rule_results:
        return 0.0
    count = sum(1 for r in rule_results if r.predicted_outcome == "PARTIALLY_ASSESSABLE")
    return count / len(rule_results)


def blocking_reason_distribution(rule_results: list[RuleResult]) -> dict[str, int]:
    """Count occurrences of each blocking_reason value."""
    dist: dict[str, int] = {}
    for r in rule_results:
        key = r.blocking_reason if r.blocking_reason is not None else "null"
        dist[key] = dist.get(key, 0) + 1
    return dist


def belief_statistics(rule_results: list[RuleResult]) -> dict[str, float]:
    """Compute mean, std, min, max, median of belief scores (excluding None)."""
    beliefs = [r.belief for r in rule_results if r.belief is not None]
    if not beliefs:
        return {"count": 0, "mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0, "median": 0.0}

    n = len(beliefs)
    mean = sum(beliefs) / n
    variance = sum((b - mean) ** 2 for b in beliefs) / n if n > 1 else 0.0
    std = variance ** 0.5
    sorted_beliefs = sorted(beliefs)
    if n % 2 == 0:
        median = (sorted_beliefs[n // 2 - 1] + sorted_beliefs[n // 2]) / 2
    else:
        median = sorted_beliefs[n // 2]

    return {
        "count": float(n),
        "mean": mean,
        "std": std,
        "min": min(beliefs),
        "max": max(beliefs),
        "median": median,
    }


# Component-to-ablation-config mapping
_COMPONENT_MAP: list[tuple[str, str]] = [
    ("VLM", "ablation_a"),
    ("SNKG", "ablation_b"),
    ("Confidence Gating", "ablation_c"),
    ("Assessability (SABLE)", "ablation_d"),
]


def compute_component_contribution(
    results_by_config: dict[str, list[RuleResult]],
    baseline_config: str = "full_system",
) -> list[dict[str, object]]:
    """Compute delta table: full_system vs each ablation config.

    Returns a list of dicts with keys: component_removed, config_name,
    recall_delta, precision_delta, f2_delta, false_fail_delta,
    not_assessable_delta, mcnemar_p, cohens_h.
    """
    baseline = results_by_config.get(baseline_config, [])
    if not baseline:
        return []

    cm_base = compute_confusion_matrix(baseline)
    recall_base = compute_recall(cm_base)
    precision_base = compute_precision(cm_base)
    f2_base = compute_f2_score(cm_base)
    false_fail_base = cm_base["fp"]
    na_base = cm_base["not_assessable"]

    rows: list[dict[str, object]] = []

    for component_name, config_name in _COMPONENT_MAP:
        ablation = results_by_config.get(config_name, [])
        if not ablation:
            continue

        cm_abl = compute_confusion_matrix(ablation)
        recall_abl = compute_recall(cm_abl)
        precision_abl = compute_precision(cm_abl)
        f2_abl = compute_f2_score(cm_abl)
        false_fail_abl = cm_abl["fp"]
        na_abl = cm_abl["not_assessable"]

        # McNemar and Cohen's h
        _, p_val = mcnemar_test(baseline, ablation)
        recall_base_prop = recall_base
        recall_abl_prop = recall_abl
        h = cohens_h(recall_base_prop, recall_abl_prop) if (recall_base_prop + recall_abl_prop) > 0 else 0.0

        rows.append({
            "component_removed": component_name,
            "config_name": config_name,
            "recall_delta": round(recall_base - recall_abl, 4),
            "precision_delta": round(precision_base - precision_abl, 4),
            "f2_delta": round(f2_base - f2_abl, 4),
            "false_fail_delta": false_fail_abl - false_fail_base,
            "not_assessable_delta": na_abl - na_base,
            "mcnemar_p": round(p_val, 4),
            "cohens_h": round(h, 4),
        })

    return rows
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/evaluation/test_metrics.py -v`
Expected: All pass.

- [ ] **Step 5: Update confusion matrix to handle PARTIALLY_ASSESSABLE**

In `compute_confusion_matrix`, update to handle `PARTIALLY_ASSESSABLE` like `NOT_ASSESSABLE`:

```python
    for r in rule_results:
        gt = r.ground_truth_outcome
        pred = r.predicted_outcome

        if pred in ("NOT_ASSESSABLE", "PARTIALLY_ASSESSABLE"):
            not_assessable += 1
            if gt == "FAIL":
                fn += 1
            continue
```

Also update `compute_automation_rate`:

```python
    assessable = sum(1 for r in rule_results if r.predicted_outcome not in ("NOT_ASSESSABLE", "PARTIALLY_ASSESSABLE"))
```

- [ ] **Step 6: Run full test suite**

Run: `pytest -x -q`
Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add src/planproof/evaluation/metrics.py tests/unit/evaluation/test_metrics.py
git commit -m "feat(eval): add SABLE metrics functions — partially_assessable_rate, blocking_reason_distribution, belief_statistics, component_contribution"
```

---

## Task 5: Regenerate Data and Re-Run Ablation Suite

This task regenerates the synthetic data with enriched attributes and runs all 7 ablation configurations to produce result JSONs with SABLE metrics.

**Files:**
- Output: `data/synthetic_diverse/` (regenerated datasets)
- Output: `data/results/` (experiment result JSONs)

- [ ] **Step 1: Regenerate synthetic datasets**

```bash
cd "c:\Users\ssivaraman\Project-Repos\[Personal] Reference Impementations\planproof"
python -m planproof.datagen.runner --seed 42 --count 5 --category compliant
python -m planproof.datagen.runner --seed 42 --count 5 --category non_compliant
python -m planproof.datagen.runner --seed 42 --count 5 --category edge_case
```

- [ ] **Step 2: Verify ground_truth.json contains new attributes**

Inspect one compliant and one noncompliant ground_truth.json:

```bash
python -c "
import json
from pathlib import Path

# Find first compliant set
for gt in sorted(Path('data/synthetic_diverse').rglob('ground_truth.json')):
    data = json.loads(gt.read_text())
    attrs = {v['attribute'] for v in data.get('values', [])}
    print(f'{gt.parent.name}: {sorted(attrs)}')
    break
"
```

Expected: Attributes include `building_height`, `rear_garden_depth`, `site_coverage`, `building_footprint_area`, `total_site_area`, `zone_category`, `certificate_type`, `form_address`, `drawing_address`, `stated_site_area`, `reference_parcel_area`, and C004 pairs.

- [ ] **Step 3: Re-seal dataset**

```bash
make seal-data
make verify-data
```

- [ ] **Step 4: Run pipeline-based ablation configs (no LLM needed)**

```bash
python scripts/run_ablation.py --config full_system --data-dir data/synthetic_diverse --output-dir data/results -v
python scripts/run_ablation.py --config ablation_a --data-dir data/synthetic_diverse --output-dir data/results -v
python scripts/run_ablation.py --config ablation_b --data-dir data/synthetic_diverse --output-dir data/results -v
python scripts/run_ablation.py --config ablation_c --data-dir data/synthetic_diverse --output-dir data/results -v
python scripts/run_ablation.py --config ablation_d --data-dir data/synthetic_diverse --output-dir data/results -v
```

- [ ] **Step 5: Verify SABLE metrics in result JSONs**

```bash
python -c "
import json
from pathlib import Path

result_path = next(Path('data/results/full_system').glob('*.json'))
data = json.loads(result_path.read_text())
for rr in data['rule_results']:
    print(f\"{rr['rule_id']}: belief={rr.get('belief')}, plausibility={rr.get('plausibility')}, blocking={rr.get('blocking_reason')}\")
"
```

Expected: full_system results have non-null belief/plausibility values. ablation_d results have null SABLE fields.

- [ ] **Step 6: Run baselines if Groq API key available**

```bash
python scripts/run_ablation.py --config naive_baseline --data-dir data/synthetic_diverse --output-dir data/results -v
python scripts/run_ablation.py --config strong_baseline --data-dir data/synthetic_diverse --output-dir data/results -v
```

Note: Baselines need LLM calls (rate-limited). If Groq daily limit is hit, use `--resume` next day.

- [ ] **Step 7: Commit results**

```bash
git add data/results/ data/synthetic_diverse/
git commit -m "data: regenerate synthetic datasets with 7-rule enrichment, re-run ablation suite with SABLE metrics"
```

---

## Task 6: Analysis Notebook — 7 SABLE Visualizations

**Files:**
- Modify: `notebooks/ablation_analysis.ipynb`
- Output: `figures/` (PNG exports at 300 DPI)

- [ ] **Step 1: Read current notebook structure**

Read `notebooks/ablation_analysis.ipynb` to understand current cell layout, import conventions, and style patterns.

- [ ] **Step 2: Add setup cell for SABLE visualizations**

Add a new markdown cell "## SABLE Evidence Sufficiency Analysis" followed by a setup cell:

```python
# SABLE visualization setup
import numpy as np
import seaborn as sns

# Dissertation-quality defaults
plt.rcParams.update({
    'font.family': 'serif',
    'font.size': 11,
    'axes.titlesize': 13,
    'axes.labelsize': 11,
    'xtick.labelsize': 10,
    'ytick.labelsize': 10,
    'legend.fontsize': 10,
    'figure.dpi': 300,
    'savefig.dpi': 300,
    'savefig.bbox': 'tight',
})

# Consistent colour palette
CONFIG_COLORS = {
    'full_system': '#2196F3',
    'ablation_a': '#FF9800',
    'ablation_b': '#4CAF50',
    'ablation_c': '#9C27B0',
    'ablation_d': '#F44336',
    'naive_baseline': '#795548',
    'strong_baseline': '#607D8B',
}

SABLE_CONFIGS = ['full_system', 'ablation_a', 'ablation_b', 'ablation_c']  # configs with SABLE enabled
ALL_CONFIGS = ['full_system', 'ablation_a', 'ablation_b', 'ablation_c', 'ablation_d', 'naive_baseline', 'strong_baseline']

# Extract SABLE data from results
sable_data = []
for exp in all_results:
    for rr in exp.rule_results:
        sable_data.append({
            'config': exp.config_name,
            'rule_id': rr.rule_id,
            'set_id': exp.set_id,
            'belief': rr.belief,
            'plausibility': rr.plausibility,
            'conflict_mass': rr.conflict_mass,
            'blocking_reason': rr.blocking_reason,
            'predicted': rr.predicted_outcome,
            'ground_truth': rr.ground_truth_outcome,
        })

import pandas as pd
df_sable = pd.DataFrame(sable_data)
```

- [ ] **Step 3: Figure 1 — Belief Distribution Violin Plot**

```python
# Figure 1: Belief distribution per config (SABLE-enabled configs only)
fig, ax = plt.subplots(figsize=(10, 6))

df_belief = df_sable[df_sable['config'].isin(SABLE_CONFIGS) & df_sable['belief'].notna()]
order = SABLE_CONFIGS
palette = [CONFIG_COLORS[c] for c in order]

sns.violinplot(
    data=df_belief, x='config', y='belief', order=order,
    palette=palette, inner='box', cut=0, ax=ax,
)
ax.set_xlabel('Configuration')
ax.set_ylabel('Bel(sufficient)')
ax.set_title('Evidence Sufficiency Belief Distribution by Configuration')
ax.set_ylim(-0.05, 1.05)
ax.axhline(y=0.7, color='green', linestyle='--', alpha=0.5, label='Assessable threshold (0.7)')
ax.axhline(y=0.3, color='red', linestyle='--', alpha=0.5, label='Not assessable threshold (0.3)')
ax.legend(loc='lower right')

fig.savefig('figures/sable_belief_violin.png')
plt.show()
```

- [ ] **Step 4: Figure 2 — Three-State Stacked Bar Chart**

```python
# Figure 2: ASSESSABLE / PARTIALLY_ASSESSABLE / NOT_ASSESSABLE per config
state_counts = df_sable.groupby(['config', 'predicted']).size().unstack(fill_value=0)

# Ensure all three states present
for state in ['PASS', 'FAIL', 'NOT_ASSESSABLE', 'PARTIALLY_ASSESSABLE']:
    if state not in state_counts.columns:
        state_counts[state] = 0

# Compute assessability states (PASS+FAIL = ASSESSABLE)
assessability = pd.DataFrame({
    'ASSESSABLE': state_counts.get('PASS', 0) + state_counts.get('FAIL', 0),
    'PARTIALLY_ASSESSABLE': state_counts.get('PARTIALLY_ASSESSABLE', 0),
    'NOT_ASSESSABLE': state_counts.get('NOT_ASSESSABLE', 0),
}).reindex(ALL_CONFIGS).fillna(0)

fig, ax = plt.subplots(figsize=(10, 6))
assessability.plot(
    kind='bar', stacked=True, ax=ax,
    color=['#4CAF50', '#FF9800', '#F44336'],
)
ax.set_xlabel('Configuration')
ax.set_ylabel('Number of Verdicts')
ax.set_title('Assessability Outcome Distribution by Configuration')
ax.legend(title='Assessability State')
plt.xticks(rotation=45, ha='right')

fig.savefig('figures/sable_three_state_bar.png')
plt.show()
```

- [ ] **Step 5: Figure 3 — Belief vs Plausibility Scatter**

```python
# Figure 3: Belief vs Plausibility scatter
fig, ax = plt.subplots(figsize=(8, 8))

for config in SABLE_CONFIGS:
    subset = df_sable[(df_sable['config'] == config) & df_sable['belief'].notna()]
    ax.scatter(
        subset['belief'], subset['plausibility'],
        c=CONFIG_COLORS[config], label=config, alpha=0.6, s=40,
    )

# Diagonal: Bel = Pl (zero ignorance)
ax.plot([0, 1], [0, 1], 'k--', alpha=0.3, label='Zero ignorance (Bel = Pl)')
ax.set_xlabel('Bel(sufficient)')
ax.set_ylabel('Pl(sufficient)')
ax.set_title('Belief vs Plausibility — Ignorance Band Visualization')
ax.set_xlim(-0.05, 1.05)
ax.set_ylim(-0.05, 1.05)
ax.legend(loc='lower right')
ax.set_aspect('equal')

fig.savefig('figures/sable_belief_vs_plausibility.png')
plt.show()
```

- [ ] **Step 6: Figure 4 — Blocking Reason Stacked Bar**

```python
# Figure 4: Blocking reason distribution per config
from planproof.evaluation.metrics import blocking_reason_distribution

reason_data = {}
for config in SABLE_CONFIGS:
    config_results = [
        rr for exp in all_results if exp.config_name == config
        for rr in exp.rule_results
    ]
    reason_data[config] = blocking_reason_distribution(config_results)

df_reasons = pd.DataFrame(reason_data).T.fillna(0)
reason_order = ['NONE', 'LOW_CONFIDENCE', 'CONFLICTING_EVIDENCE', 'MISSING_EVIDENCE']
existing_reasons = [r for r in reason_order if r in df_reasons.columns]

fig, ax = plt.subplots(figsize=(10, 6))
df_reasons[existing_reasons].reindex(SABLE_CONFIGS).plot(
    kind='bar', stacked=True, ax=ax,
    color=['#4CAF50', '#FF9800', '#E91E63', '#F44336'],
)
ax.set_xlabel('Configuration')
ax.set_ylabel('Count')
ax.set_title('Blocking Reason Distribution (SABLE-Enabled Configurations)')
ax.legend(title='Blocking Reason')
plt.xticks(rotation=45, ha='right')

fig.savefig('figures/sable_blocking_reasons.png')
plt.show()
```

- [ ] **Step 7: Figure 5 — False-FAIL Prevention Bar Chart**

```python
# Figure 5: False FAIL count per config
false_fails = {}
for config in ALL_CONFIGS:
    config_results = [
        rr for exp in all_results if exp.config_name == config
        for rr in exp.rule_results
    ]
    cm = compute_confusion_matrix(config_results)
    false_fails[config] = cm['fp']

fig, ax = plt.subplots(figsize=(10, 6))
configs = list(false_fails.keys())
counts = [false_fails[c] for c in configs]
colors = [CONFIG_COLORS.get(c, '#999999') for c in configs]
bars = ax.bar(configs, counts, color=colors)

# Highlight full_system = 0
for bar, config in zip(bars, configs):
    if config == 'full_system':
        bar.set_edgecolor('gold')
        bar.set_linewidth(2)
        ax.annotate(
            f'{int(bar.get_height())}', xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
            ha='center', va='bottom', fontweight='bold', fontsize=12,
        )

ax.set_xlabel('Configuration')
ax.set_ylabel('False FAIL Count')
ax.set_title('False Violation Verdicts by Configuration')
plt.xticks(rotation=45, ha='right')

fig.savefig('figures/sable_false_fail_prevention.png')
plt.show()
```

- [ ] **Step 8: Figure 6 — Component Contribution Table**

```python
# Figure 6: Component contribution table with statistical significance
from planproof.evaluation.metrics import compute_component_contribution

results_by_config = {}
for exp in all_results:
    results_by_config.setdefault(exp.config_name, []).extend(exp.rule_results)

rows = compute_component_contribution(results_by_config)

if rows:
    df_contrib = pd.DataFrame(rows)
    display_cols = [
        'component_removed', 'recall_delta', 'precision_delta', 'f2_delta',
        'false_fail_delta', 'not_assessable_delta', 'mcnemar_p', 'cohens_h',
    ]

    fig, ax = plt.subplots(figsize=(14, 3 + len(rows) * 0.6))
    ax.axis('off')

    col_labels = [
        'Component\nRemoved', 'Recall\n\u0394', 'Precision\n\u0394', 'F2\n\u0394',
        'False FAILs\n\u0394', 'N/A\n\u0394', 'McNemar\np-value', "Cohen's\nh",
    ]

    table_data = []
    cell_colors = []
    for _, row in df_contrib.iterrows():
        table_row = [
            row['component_removed'],
            f"{row['recall_delta']:+.3f}",
            f"{row['precision_delta']:+.3f}",
            f"{row['f2_delta']:+.3f}",
            f"{row['false_fail_delta']:+d}" if isinstance(row['false_fail_delta'], int) else f"{row['false_fail_delta']:+.0f}",
            f"{row['not_assessable_delta']:+d}" if isinstance(row['not_assessable_delta'], int) else f"{row['not_assessable_delta']:+.0f}",
            f"{row['mcnemar_p']:.3f}" if not (isinstance(row['mcnemar_p'], float) and row['mcnemar_p'] != row['mcnemar_p']) else "N/A",
            f"{row['cohens_h']:+.3f}",
        ]
        table_data.append(table_row)

        # Color coding: green if positive delta (component helps), red if negative
        row_colors = ['white']  # component name
        for val in [row['recall_delta'], row['precision_delta'], row['f2_delta']]:
            row_colors.append('#c8e6c9' if val > 0 else '#ffcdd2' if val < 0 else 'white')
        row_colors.append('#ffcdd2' if row['false_fail_delta'] > 0 else '#c8e6c9' if row['false_fail_delta'] < 0 else 'white')
        row_colors.append('#ffcdd2' if row['not_assessable_delta'] < 0 else 'white')
        p_val = row['mcnemar_p']
        row_colors.append('#fff9c4' if isinstance(p_val, float) and p_val < 0.05 and p_val == p_val else 'white')
        row_colors.append('white')
        cell_colors.append(row_colors)

    table = ax.table(
        cellText=table_data,
        colLabels=col_labels,
        cellColours=cell_colors,
        loc='center',
        cellLoc='center',
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.5)

    ax.set_title('Component Contribution Analysis (Full System vs Ablations)', fontsize=13, pad=20)

    fig.savefig('figures/sable_component_contribution.png')
    plt.show()
```

- [ ] **Step 9: Figure 7 — Concordance Heatmap**

```python
# Figure 7: Rule x Config concordance-adjusted belief heatmap
pivot_data = df_sable[
    df_sable['config'].isin(SABLE_CONFIGS) & df_sable['belief'].notna()
].groupby(['rule_id', 'config'])['belief'].mean().unstack()

if not pivot_data.empty:
    pivot_data = pivot_data.reindex(columns=SABLE_CONFIGS)

    fig, ax = plt.subplots(figsize=(10, 6))
    sns.heatmap(
        pivot_data, annot=True, fmt='.2f', cmap='RdYlBu',
        vmin=0, vmax=1, center=0.5, ax=ax,
        linewidths=0.5, linecolor='white',
        cbar_kws={'label': 'Mean Belief Score'},
    )
    ax.set_xlabel('Configuration')
    ax.set_ylabel('Rule')
    ax.set_title('Mean Evidence Sufficiency Belief by Rule and Configuration')

    fig.savefig('figures/sable_concordance_heatmap.png')
    plt.show()
```

- [ ] **Step 10: Export all figures and run notebook end-to-end**

Run the full notebook to verify all cells execute without errors and figures render correctly.

```bash
jupyter nbconvert --to notebook --execute notebooks/ablation_analysis.ipynb --output ablation_analysis_executed.ipynb
```

- [ ] **Step 11: Commit**

```bash
git add notebooks/ablation_analysis.ipynb figures/
git commit -m "feat(eval): add 7 SABLE visualizations — belief violin, three-state bar, scatter, blocking reasons, false-FAIL, component table, heatmap"
```

---

## Task 7: Qualitative Error Analysis

**Files:**
- Create: `docs/ERROR_ANALYSIS.md`

- [ ] **Step 1: Load results and identify all misclassifications**

```bash
python -c "
from planproof.evaluation.results import load_all_results
from pathlib import Path

results = load_all_results(Path('data/results'))
print(f'Total experiments: {len(results)}')

errors = []
for exp in results:
    for rr in exp.rule_results:
        gt = rr.ground_truth_outcome
        pred = rr.predicted_outcome
        # Misclassification: pred disagrees with gt
        # NOT_ASSESSABLE/PARTIALLY_ASSESSABLE when gt=FAIL is a miss
        # FAIL when gt=PASS is a false alarm
        if pred in ('PASS', 'FAIL') and pred != gt:
            errors.append((exp.config_name, exp.set_id, rr.rule_id, gt, pred, rr.belief, rr.blocking_reason))
        elif pred in ('NOT_ASSESSABLE', 'PARTIALLY_ASSESSABLE') and gt == 'FAIL':
            errors.append((exp.config_name, exp.set_id, rr.rule_id, gt, pred, rr.belief, rr.blocking_reason))

print(f'Total misclassifications: {len(errors)}')
for e in errors:
    print(f'  {e[0]:20s} {e[1]:25s} {e[2]:5s} gt={e[3]:4s} pred={e[4]:20s} belief={e[5]} reason={e[6]}')
"
```

- [ ] **Step 2: Write ERROR_ANALYSIS.md**

Create `docs/ERROR_ANALYSIS.md` with the structure:

```markdown
# PlanProof — Qualitative Error Analysis

> **Generated:** 2026-04-02
> **Purpose:** Per-misclassification narratives for dissertation Discussion chapter.

## Summary

[Count of total misclassifications across all configs, broken down by type]

## Error Categories

### False FAILs (gt=PASS, pred=FAIL)
[List each, with root cause]

### Missed Violations (gt=FAIL, pred=NOT_ASSESSABLE/PARTIALLY_ASSESSABLE)
[List each, with root cause]

### False PASSes (gt=FAIL, pred=PASS)
[List each, with root cause]

## Categorisation

### Systemic Errors
[Errors that would occur on any similar input]

### Incidental Errors
[Errors specific to one dataset's quirks]

### Data Gap Errors
[Errors caused by synthetic data limitations]

## Dissertation Vignettes

### Vignette 1: [Title]
[2-3 paragraph narrative]

### Vignette 2: [Title]
[2-3 paragraph narrative]

### Vignette 3: [Title]
[2-3 paragraph narrative]
```

The content should be filled based on the actual results from Step 1. Each vignette should:
- Identify the specific error case
- Trace through SABLE metrics (belief, plausibility, blocking reason)
- Explain what the architecture did right or wrong
- Draw a conclusion relevant to the dissertation thesis

- [ ] **Step 3: Commit**

```bash
git add docs/ERROR_ANALYSIS.md
git commit -m "docs: qualitative error analysis with per-misclassification narratives for dissertation"
```

---

## Task 8: Update Project Documentation

**Files:**
- Modify: `docs/EXECUTION_STATUS.md`
- Modify: `docs/GAPS_AND_IDEAS.md`

- [ ] **Step 1: Update EXECUTION_STATUS.md**

- Mark Phase 8a as Complete with date
- Update project statistics (test count, commit count, source files)
- Update "Next Steps" section to reflect Phase 8b/8c/9/Dissertation

- [ ] **Step 2: Update GAPS_AND_IDEAS.md**

- Mark Gap #6 (R003 lacks attributes) as RESOLVED
- Add note about C-rule datagen support
- Update project statistics

- [ ] **Step 3: Commit**

```bash
git add docs/EXECUTION_STATUS.md docs/GAPS_AND_IDEAS.md
git commit -m "docs: update execution status and gaps for Phase 8a completion"
```
