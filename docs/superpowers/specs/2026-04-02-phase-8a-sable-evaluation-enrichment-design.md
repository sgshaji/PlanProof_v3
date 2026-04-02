# Phase 8a: SABLE-Centred Evaluation Enrichment — Design Spec

> **Date:** 2026-04-02
> **Status:** Approved
> **Goal:** Enrich synthetic data for all 7 rules, capture SABLE metrics in experiment results, produce 7 dissertation-quality visualizations, and generate a component contribution table with statistical significance.

---

## 1. Result Model Extension

**File:** `src/planproof/evaluation/results.py`

Extend `RuleResult` to carry SABLE signals:

- Change `predicted_outcome` from `Literal["PASS", "FAIL", "NOT_ASSESSABLE"]` to `Literal["PASS", "FAIL", "NOT_ASSESSABLE", "PARTIALLY_ASSESSABLE"]`
- Add fields:
  - `belief: float | None = None` — Bel(sufficient) from SABLE
  - `plausibility: float | None = None` — Pl(sufficient) from SABLE
  - `conflict_mass: float | None = None` — Dempster conflict K
  - `blocking_reason: str | None = None` — MISSING_EVIDENCE / CONFLICTING_EVIDENCE / LOW_CONFIDENCE / NONE
- All new fields default to None (baselines and ablation_d bypass SABLE)

No backward compatibility needed — all results will be regenerated.

---

## 2. Ablation Runner Enhancement

**File:** `scripts/run_ablation.py`

After pipeline execution, extract `AssessabilityResult` from `context["assessability_results"]` for each rule and populate the new `RuleResult` fields:

- For configs with assessability enabled (full_system, ablation_a, ablation_b, ablation_c): map `belief`, `plausibility`, `conflict_mass`, `blocking_reason` from each `AssessabilityResult` into the corresponding `RuleResult`
- For ablation_d (assessability disabled) and baselines (naive/strong): leave SABLE fields as None
- Map `PARTIALLY_ASSESSABLE` status through to `predicted_outcome` when SABLE returns it

---

## 3. Synthetic Data Enrichment

### 3a. R003 Site Coverage — Enrich Existing Config

**File:** `configs/datagen/rules/r003_site_coverage.yaml`

Currently generates only `site_coverage` (percentage). Extend to generate three attributes:

| Attribute | Type | Unit | Compliant Range | Non-Compliant Range |
|-----------|------|------|-----------------|---------------------|
| `building_footprint_area` | numeric | m² | 40–200 | 201–500 |
| `total_site_area` | numeric | m² | 200–1000 | (derived to make ratio > 0.50) |
| `zone_category` | categorical | — | {residential, suburban_residential} | {industrial, commercial} |

Compliant constraint: `building_footprint_area / total_site_area <= 0.50`.

### 3b. C-Rule Datagen Configs — New

**C001 Certificate Type Validity**
**File:** `configs/datagen/rules/c001_certificate_type.yaml`

| Attribute | Type | Compliant Values | Non-Compliant Values |
|-----------|------|-----------------|---------------------|
| `certificate_type` | categorical | A, B, C, D | X, E, null |
| `ownership_declaration` | categorical | sole_owner, part_owner, other | missing, invalid |

**C002 Address Consistency**
**File:** `configs/datagen/rules/c002_address_consistency.yaml`

| Attribute | Type | Compliant | Non-Compliant |
|-----------|------|-----------|---------------|
| `form_address` | string | "123 Example Street, Birmingham, B1 1AA" | "123 Example Street, Birmingham, B1 1AA" |
| `drawing_address` | string | "123 Example St, Birmingham, B1 1AA" (minor variation) | "456 Other Road, London, E1 2BB" (different address) |

Compliant: Levenshtein similarity >= 0.85. Non-compliant: divergent addresses.

**C003 Boundary Validation**
**File:** `configs/datagen/rules/c003_boundary_validation.yaml`

| Attribute | Type | Unit | Compliant | Non-Compliant |
|-----------|------|------|-----------|---------------|
| `stated_site_area` | numeric | m² | 200–1000 | 200–1000 |
| `reference_parcel_area` | numeric | m² | within ±15% of stated | >15% discrepancy |

**C004 Plan Change Detection**
**File:** `configs/datagen/rules/c004_plan_change.yaml`

| Attribute Pair | Type | Unit | Compliant | Non-Compliant |
|----------------|------|------|-----------|---------------|
| `proposed_building_height` / `approved_building_height` | numeric | metres | matching (±0.1m) | significant difference (>1m) |
| `proposed_footprint_area` / `approved_footprint_area` | numeric | m² | matching (±5%) | significant difference (>20%) |
| `proposed_storeys` / `approved_storeys` | integer | count | matching | different |

### 3c. Scenario Generator Extension

**File:** `src/planproof/datagen/scenario/generator.py`

Current `generate_values()` only handles single numeric attributes per rule. Extend to support:

- **Multi-attribute rules:** Iterate over multiple `evidence_attributes` per rule config, generate a value for each. For ratio rules (R003), enforce cross-attribute constraints (footprint/site <= threshold).
- **Categorical values:** Sample from a list of valid/invalid values based on category (compliant/non-compliant).
- **String values:** Generate address strings with controlled similarity (compliant = minor abbreviation differences, non-compliant = entirely different addresses).
- **Paired values:** For C003 and C004, generate correlated pairs where the relationship determines compliance.

The `Value` dataclass may need a `str_value: str | None` field alongside the existing numeric `value: float` to hold categorical/string data. Alternatively, encode categoricals as the `display_text` field with a sentinel `value` (e.g., 0.0 for categoricals). Prefer the former — explicit is better.

### 3d. Regenerate Datasets

- Regenerate 15 datasets: `--seed 42 --count 5` for each of compliant, non_compliant, edge_case
- Re-seal with `make seal-data` and verify with `make verify-data`
- Verify ground_truth.json files contain all new attributes for all 7 rules

---

## 4. Metrics Extension

**File:** `src/planproof/evaluation/metrics.py`

### 4a. Component Contribution Table

New function: `compute_component_contribution(all_results, baseline_config="full_system")`

Returns a list of rows, one per ablated component:

| Column | Description |
|--------|-------------|
| `component_removed` | Human-readable name (e.g., "SNKG", "Confidence Gating", "Assessability (SABLE)", "VLM") |
| `config_name` | Ablation config that removes this component |
| `recall_delta` | full_system recall minus this config's recall |
| `precision_delta` | full_system precision minus this config's precision |
| `f2_delta` | full_system F2 minus this config's F2 |
| `false_fail_delta` | this config's false FAILs minus full_system's false FAILs |
| `not_assessable_delta` | this config's NOT_ASSESSABLE count minus full_system's |
| `mcnemar_p` | McNemar test p-value (full_system vs this config) |
| `cohens_h` | Cohen's h effect size |

Component-to-config mapping:
- SNKG → ablation_b (no SNKG)
- Confidence Gating → ablation_c (no gating)
- Assessability (SABLE) → ablation_d (no assessability)
- VLM → ablation_a (no VLM)

### 4b. SABLE-Specific Metrics

- `partially_assessable_rate(results: list[RuleResult]) -> float` — proportion of PARTIALLY_ASSESSABLE outcomes
- `blocking_reason_distribution(results: list[RuleResult]) -> dict[str, int]` — counts per blocking reason (MISSING_EVIDENCE, CONFLICTING_EVIDENCE, LOW_CONFIDENCE, NONE, null)
- `belief_statistics(results: list[RuleResult]) -> dict[str, float]` — mean, std, min, max, median of belief scores (excluding None)

---

## 5. Analysis Notebook — 7 Visualizations

**File:** `notebooks/ablation_analysis.ipynb`

All figures: 300 DPI, dissertation-quality styling. Consistent colour palette across all plots. Clean sans-serif fonts. Proper axis labels with units. No default matplotlib chrome. Figures exported to `figures/` as PNGs.

### Figure 1: Belief Distribution Violin Plot
- X-axis: ablation config (full_system, ablation_a, b, c — configs with SABLE enabled)
- Y-axis: Bel(sufficient) [0, 1]
- One violin per config showing distribution of belief scores across all (rule, dataset) pairs
- Key story: full_system has tight, high-belief distribution; removing components widens/lowers it

### Figure 2: Three-State Stacked Bar Chart
- X-axis: all 7 configs
- Y-axis: count of verdicts
- Three segments: ASSESSABLE (green), PARTIALLY_ASSESSABLE (amber), NOT_ASSESSABLE (red)
- Key story: full_system has most ASSESSABLE; ablation_d has zero NOT_ASSESSABLE (forced binary); baselines have zero (no assessability concept)

### Figure 3: Belief vs Plausibility Scatter
- X-axis: Bel(sufficient)
- Y-axis: Pl(sufficient)
- Each dot = one (rule, dataset) pair, coloured by config
- The diagonal (Bel = Pl) means zero ignorance; gap between dot and diagonal = ignorance mass
- Key story: shows how evidence sufficiency varies and where uncertainty is highest

### Figure 4: Blocking Reason Stacked Bar
- X-axis: configs with assessability enabled
- Y-axis: count
- Four segments: MISSING_EVIDENCE, CONFLICTING_EVIDENCE, LOW_CONFIDENCE, NONE
- Key story: explains *why* rules are NOT_ASSESSABLE — MISSING dominates when attributes aren't extracted

### Figure 5: False-FAIL Prevention Bar Chart
- X-axis: all 7 configs
- Y-axis: false FAIL count
- Single colour bar per config
- Annotation: full_system = 0 (highlighted)
- Key story: the thesis punchline — assessability prevents false violations

### Figure 6: Component Contribution Table
- Rendered as a formatted matplotlib table figure (not just printed text)
- Columns: Component Removed, Recall delta, Precision delta, F2 delta, False FAILs delta, NOT_ASSESSABLE delta, McNemar p, Cohen's h
- Colour-coded: green = improvement from component, red = degradation
- Key story: one-glance summary of what each architectural component contributes

### Figure 7: Concordance Heatmap
- Rows: rules (R001, R002, R003, C001–C004)
- Columns: configs (full_system, ablation_a, b, c)
- Cell value: mean concordance-adjusted belief across datasets for that (rule, config) pair
- Colour scale: diverging (red = low, white = mid, blue = high)
- Key story: which rules are most sensitive to which component removal

---

## 6. Qualitative Error Analysis

**File:** `docs/ERROR_ANALYSIS.md`

### Process
1. Load all result JSONs from the re-run
2. Identify every misclassification: predicted != ground_truth (treating NOT_ASSESSABLE and PARTIALLY_ASSESSABLE as distinct from PASS/FAIL)
3. Group by: false FAILs, false PASSes, incorrect NOT_ASSESSABLE (should have been assessable)

### Per-Error Documentation
For each misclassification:
- Rule ID and dataset ID
- Ground truth outcome vs predicted outcome
- SABLE metrics (belief, plausibility, conflict_mass, blocking_reason)
- Which evidence was available vs required
- Root cause: extraction gap, reconciliation failure, confidence below threshold, or data limitation

### Categorisation
- **Systemic:** Would occur on any similar input (e.g., C-rules always fail when attribute types not supported)
- **Incidental:** Specific to one dataset's quirks
- **Data gap:** Caused by synthetic data limitations (e.g., missing doc types)

### Dissertation Vignettes
3–5 narrative paragraphs for the Discussion chapter, each telling the story of one informative error and what it reveals about the architecture's strengths/limitations.

---

## Out of Scope

- Granular reconciliation/confidence breakdowns (deferred)
- Extraction accuracy metrics (Phase 8c)
- Real BCC data re-runs (no ground truth available)
- Dashboard UI (later phase)
- VLM fine-tuning
- Shapely spatial predicates

---

## Dependencies

- Groq API key (for baseline re-runs — rate limited to ~10-15/day)
- OpenAI API key (for GPT-4o baselines if needed)
- sentence-transformers (for SABLE semantic similarity — already installed)
- All other dependencies already in pyproject.toml

---

## Success Criteria

1. All 7 rules produce non-trivial SABLE metrics (not all NOT_ASSESSABLE) for compliant and non-compliant datasets
2. Result JSONs contain belief/plausibility/conflict_mass/blocking_reason for SABLE-enabled configs
3. PARTIALLY_ASSESSABLE appears in at least some edge-case results
4. All 7 visualizations render at 300 DPI with dissertation-quality styling
5. Component contribution table shows statistically significant differences (p < 0.05) for at least assessability and one other component
6. Error analysis document contains 3–5 narrative vignettes with root cause attribution
7. All tests pass, ruff clean, mypy --strict clean
