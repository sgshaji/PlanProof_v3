# Phase 7b–9: Bug Fixes, Evaluation Completion, Boundary Verification & Dissertation Readiness

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the two critical pipeline bugs, complete the ablation evaluation with richer synthetic data, re-run experiments with SABLE metrics, implement the three-tier boundary verification pipeline with HMLR INSPIRE land data, apply architectural polish, and leave the codebase dissertation-ready.

**Architecture:** Four phases of increasing scope — Phase 7b fixes bugs blocking correct E2E behaviour, Phase 8a enriches synthetic data and re-runs the full experiment suite, Phase 8b applies P0–P2 architectural polish, Phase 9 implements the three-tier boundary verification pipeline (VLM visual alignment, scale-bar measurement, HMLR INSPIRE address cross-reference). Each phase is independently committable and testable.

**Tech Stack:** Python 3.12, pytest, pydantic, sentence-transformers, Groq (llama-3.3-70b), OpenAI GPT-4o, Neo4j Aura, structlog, ruff, mypy --strict.

---

## Phase 7b: Critical Bug Fixes

Two bugs prevent correct E2E pipeline behaviour. Both are well-understood with pinpointed root causes.

---

### Task 1: Fix assessability step not firing in E2E pipeline (Gap #1)

**Root cause:** `pipeline.py:56` initialises `context["metadata"]` with only `{"input_dir": ...}`. The `AssessabilityStep.execute()` reads `context["metadata"]["rule_ids"]` which is never populated, so the for-loop body never executes.

**Fix strategy:** Populate `rule_ids` in `pipeline.py` context from the registered steps. The cleanest approach: add a `rule_ids` parameter to `Pipeline.__init__()` and inject it into context metadata at run-time. Bootstrap already has `rules_dict.keys()` available.

**Files:**
- Modify: `src/planproof/pipeline/pipeline.py` — add `rule_ids` parameter, inject into context metadata
- Modify: `src/planproof/bootstrap.py` — pass `list(rules_dict.keys())` to Pipeline constructor
- Test: `tests/pipeline/test_pipeline.py` — verify rule_ids flow into context
- Test: `tests/pipeline/steps/test_assessability.py` — verify step produces results when rule_ids present

- [ ] **Step 1: Write failing test — pipeline context includes rule_ids**

In `tests/pipeline/test_pipeline.py`, add a test that constructs a Pipeline with `rule_ids=["R001", "R002"]`, runs it, and asserts `context["metadata"]["rule_ids"]` is populated. This will fail because Pipeline doesn't accept `rule_ids` yet.

```python
def test_pipeline_injects_rule_ids_into_context():
    """rule_ids passed to Pipeline appear in context metadata."""
    pipeline = Pipeline(rule_ids=["R001", "R002"])
    # Register a no-op step that captures context
    captured: dict = {}

    class ContextCapture:
        name = "capture"
        def execute(self, context):
            captured.update(context)
            return {"success": True, "message": "ok", "artifacts": {}}

    pipeline.register(ContextCapture())
    pipeline.run(Path("/tmp/fake"))
    assert captured["metadata"]["rule_ids"] == ["R001", "R002"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/pipeline/test_pipeline.py::test_pipeline_injects_rule_ids_into_context -v`
Expected: FAIL — `TypeError: Pipeline.__init__() got an unexpected keyword argument 'rule_ids'`

- [ ] **Step 3: Modify Pipeline to accept and inject rule_ids**

In `src/planproof/pipeline/pipeline.py`:
- Add `rule_ids: list[str] | None = None` parameter to `__init__`
- Store as `self._rule_ids = rule_ids or []`
- In `run()`, add `"rule_ids": self._rule_ids` to the metadata dict

```python
# In __init__:
def __init__(self, rule_ids: list[str] | None = None) -> None:
    self._steps: list[Any] = []
    self._rule_ids = rule_ids or []

# In run(), the context initialisation:
context: PipelineContext = {
    "entities": [],
    "verdicts": [],
    "assessability_results": [],
    "metadata": {"input_dir": str(input_dir), "rule_ids": self._rule_ids},
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/pipeline/test_pipeline.py::test_pipeline_injects_rule_ids_into_context -v`
Expected: PASS

- [ ] **Step 5: Update bootstrap to pass rule_ids to Pipeline**

In `src/planproof/bootstrap.py`, change the `Pipeline()` construction (around line 133) to:

```python
pipeline = Pipeline(rule_ids=list(rules_dict.keys()))
```

This must happen after `rules_dict` is built (line 165), so move the Pipeline construction below the rules loading block, or pass rule_ids after construction via a setter. The simplest approach: build `rules_dict` first, then construct `Pipeline(rule_ids=list(rules_dict.keys()))`.

- [ ] **Step 6: Run full test suite**

Run: `pytest -x -q`
Expected: All tests pass, no regressions.

- [ ] **Step 7: Commit**

```bash
git add src/planproof/pipeline/pipeline.py src/planproof/bootstrap.py tests/pipeline/test_pipeline.py
git commit -m "fix: populate rule_ids in pipeline context so assessability step fires (Gap #1)"
```

---

### Task 2: Fix rule_id "unknown" in verdict reports (Gap #2)

**Root cause:** `NumericThresholdEvaluator.evaluate()` reads `rule_id` from `self._params` (the YAML parameters dict), but the YAML `parameters:` block doesn't include `rule_id` — it's on `RuleConfig.rule_id`. So evaluators fall back to `"unknown"`.

**Fix strategy:** Inject `rule_id` into the parameters dict when `RuleFactory.load_rules()` builds the `(config, evaluator)` pairs. This is the least disruptive change — no Protocol changes, no new arguments.

**Files:**
- Modify: `src/planproof/reasoning/evaluators/factory.py` — inject `rule_id` into params before creating evaluator
- Test: `tests/reasoning/evaluators/test_factory.py` — verify loaded evaluator has rule_id in params
- Test: `tests/pipeline/steps/test_rule_evaluation.py` — verify verdicts carry correct rule_id

- [ ] **Step 1: Write failing test — evaluator params contain rule_id**

In `tests/reasoning/evaluators/test_factory.py`:

```python
def test_loaded_evaluator_has_rule_id_in_params(tmp_path):
    """RuleFactory.load_rules injects rule_id into evaluator parameters."""
    rule_yaml = tmp_path / "r001_test.yaml"
    rule_yaml.write_text(
        "rule_id: R001\n"
        "description: test\n"
        "evaluation_type: numeric_threshold\n"
        "parameters:\n"
        "  attribute: building_height\n"
        "  operator: '<='\n"
        "  threshold: 8.0\n"
        "  unit: metres\n"
        "required_evidence:\n"
        "  - attribute: building_height\n"
        "    acceptable_sources: [DRAWING]\n"
        "    min_confidence: 0.7\n"
    )
    factory = RuleFactory()
    factory.register("numeric_threshold", NumericThresholdEvaluator)
    pairs = factory.load_rules(tmp_path)
    config, evaluator = pairs[0]
    assert evaluator._params["rule_id"] == "R001"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/reasoning/evaluators/test_factory.py::test_loaded_evaluator_has_rule_id_in_params -v`
Expected: FAIL — `KeyError: 'rule_id'` or assertion failure

- [ ] **Step 3: Inject rule_id into parameters in RuleFactory.load_rules()**

In `src/planproof/reasoning/evaluators/factory.py`, inside `load_rules()`, after parsing the YAML and before creating the evaluator, add:

```python
params = raw.get("parameters", {})
params["rule_id"] = raw["rule_id"]  # Inject so evaluators can read it
```

Then pass `params` (not `raw.get("parameters", {})`) when constructing the evaluator.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/reasoning/evaluators/test_factory.py::test_loaded_evaluator_has_rule_id_in_params -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest -x -q`
Expected: All tests pass. Existing tests that checked `rule_id="unknown"` may need updating to expect the actual rule_id.

- [ ] **Step 6: Update any tests that asserted rule_id="unknown"**

Search for `rule_id.*unknown` in test files and update expectations to reflect the actual rule_id. The E2E test (`tests/test_e2e_pipeline.py`) has comments about this — update accordingly.

- [ ] **Step 7: Commit**

```bash
git add src/planproof/reasoning/evaluators/factory.py tests/
git commit -m "fix: inject rule_id into evaluator params so verdicts carry correct IDs (Gap #2)"
```

---

## Phase 8a: Evaluation Enrichment

With both bugs fixed, the pipeline produces correct assessability results and labelled verdicts. Now enrich synthetic data and re-run the full experiment suite.

---

### Task 3: Enrich synthetic data — add R003 required attributes (Gap #6)

**Root cause:** Datagen config `configs/datagen/rules/r003_site_coverage.yaml` only generates a single `site_coverage` percentage. Rule R003 requires `building_footprint_area`, `total_site_area`, and `zone_category` as separate evidence items.

**Files:**
- Modify: `configs/datagen/rules/r003_site_coverage.yaml` — add building_footprint_area, total_site_area, zone_category as evidence items
- Modify: `src/planproof/datagen/scenario/generator.py` — handle multi-attribute rules (if needed)
- Modify: `src/planproof/datagen/scenario/config_loader.py` — parse new evidence structure (if needed)
- Test: `tests/datagen/test_scenario_generator.py` — verify R003 produces three attributes

- [ ] **Step 1: Read current R003 datagen config and scenario generator to understand the generation model**

Read `configs/datagen/rules/r003_site_coverage.yaml` and `src/planproof/datagen/scenario/generator.py` to understand how values are generated from rule configs. Determine whether the generator supports multi-attribute rules or needs extension.

- [ ] **Step 2: Write failing test — R003 scenario contains building_footprint_area and total_site_area**

```python
def test_r003_scenario_has_footprint_and_site_area():
    """R003 scenario generates building_footprint_area and total_site_area."""
    scenario = generate_scenario(seed=42, category="compliant")
    r003_values = [v for v in scenario.values if "footprint" in v.attribute or "site_area" in v.attribute]
    assert len(r003_values) >= 2
```

- [ ] **Step 3: Update R003 datagen config to declare three evidence attributes**

Update `configs/datagen/rules/r003_site_coverage.yaml` to generate `building_footprint_area` (numeric, m²), `total_site_area` (numeric, m²), and `zone_category` (categorical). Set compliant ranges such that `building_footprint_area / total_site_area ≤ 0.50`.

- [ ] **Step 4: Update scenario generator if needed to support multi-attribute rules**

If the generator only handles single-attribute rules, extend it to iterate over multiple `evidence_attributes` per rule config and generate a value for each.

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/datagen/test_scenario_generator.py::test_r003_scenario_has_footprint_and_site_area -v`

- [ ] **Step 6: Add C-rule attributes to datagen if currently missing**

Check whether C001–C004 attributes (`certificate_type`, `address`, `boundary_status`, `plan_consistency`) are generated by datagen. If not, add simple categorical generators for them.

- [ ] **Step 7: Regenerate synthetic datasets**

Run: `python -m planproof.datagen.runner --seed 42 --count 5 --category compliant`
Run: `python -m planproof.datagen.runner --seed 42 --count 5 --category non_compliant`
Run: `python -m planproof.datagen.runner --seed 42 --count 5 --category edge_case`

Verify the output ground_truth.json files contain the new attributes.

- [ ] **Step 8: Re-seal the dataset**

Run: `make seal-data` then `make verify-data`

- [ ] **Step 9: Commit**

```bash
git add configs/datagen/ src/planproof/datagen/ tests/datagen/ data/synthetic/
git commit -m "feat: enrich R003 synthetic data with footprint_area, site_area, zone_category (Gap #6)"
```

---

### Task 4: Re-run ablation experiments with SABLE metrics

**Why:** Previous ablation results were generated before SABLE was implemented. Now that SABLE provides belief/plausibility/conflict_mass metrics, the ablation needs re-running to capture these richer signals. Also, the assessability step now fires correctly (Task 1 fix).

**Files:**
- Modify: `src/planproof/evaluation/results.py` — ensure result model captures SABLE metrics (belief, plausibility, conflict_mass)
- Modify: `scripts/run_ablation.py` (or equivalent) — add SABLE metric extraction from pipeline context
- Modify: `notebooks/analysis.ipynb` — add SABLE metric visualisations (belief distribution, concordance heatmap)
- Output: `results/` — new experiment result JSON files

- [ ] **Step 1: Read current result model and ablation runner**

Read `src/planproof/evaluation/results.py` and the ablation runner script to understand what metrics are currently captured.

- [ ] **Step 2: Extend result model to include SABLE metrics if not already present**

Add `belief`, `plausibility`, `conflict_mass` fields to the per-rule result structure. These should be optional (None for baselines that don't use SABLE).

- [ ] **Step 3: Update ablation runner to extract SABLE metrics from assessability_results**

After pipeline execution, read `context["assessability_results"]` and extract `belief`, `plausibility`, `conflict_mass` from each `AssessabilityResult`.

- [ ] **Step 4: Run all 7 ablation configurations on the enriched synthetic data**

Run each config: `full_system`, `ablation_a` (no VLM), `ablation_b` (no SNKG), `ablation_c` (no reconciliation), `ablation_d` (no assessability), `naive_baseline`, `strong_baseline`.

Note: baselines need Groq LLM calls (rate-limited). Run ablation configs first (no LLM needed with ground truth entities), then baselines.

- [ ] **Step 5: Verify result files contain SABLE metrics**

Inspect the generated JSON result files — full_system and ablation_a/b/c should have non-null belief/plausibility values. ablation_d and baselines should have null (assessability disabled).

- [ ] **Step 6: Commit**

```bash
git add src/planproof/evaluation/ scripts/ results/
git commit -m "feat: re-run ablation suite with SABLE belief/plausibility metrics on enriched data"
```

---

### Task 5: Update analysis notebook with SABLE visualisations

**Files:**
- Modify: `notebooks/analysis.ipynb` — add SABLE-specific figures

- [ ] **Step 1: Read existing notebook structure**

Read `notebooks/analysis.ipynb` to understand current figure layout and style conventions.

- [ ] **Step 2: Add belief distribution violin plot**

For each ablation config that has SABLE metrics, plot the distribution of belief scores across rules. This shows how evidence sufficiency varies by component removal.

- [ ] **Step 3: Add concordance heatmap**

Create a rule × config heatmap showing concordance-adjusted belief. Highlights which rules are most sensitive to component removal.

- [ ] **Step 4: Add SABLE three-state confusion matrix**

Plot ASSESSABLE/PARTIALLY_ASSESSABLE/NOT_ASSESSABLE counts per config as a stacked bar chart. This is the key figure for the assessability engine's contribution.

- [ ] **Step 5: Add false-FAIL prevention figure**

Compare false FAIL counts across all configs. The thesis claim: full system produces 0 false FAILs; ablation_d (no assessability) produces the most.

- [ ] **Step 6: Export all figures at 300 DPI**

Re-run the notebook end-to-end, verify all figures render, export PNGs to `figures/`.

- [ ] **Step 7: Commit**

```bash
git add notebooks/analysis.ipynb figures/
git commit -m "feat: add SABLE visualisations — belief distributions, concordance heatmap, false-FAIL prevention"
```

---

### Task 6: Qualitative error analysis

**Why:** The dissertation needs per-misclassification narratives, not just aggregate metrics. This is the "why did it go wrong" section.

**Files:**
- Create: `docs/ERROR_ANALYSIS.md` — structured error analysis document

- [ ] **Step 1: Identify all misclassifications from ablation results**

Load result JSONs and find every case where the system verdict disagrees with ground truth. Group by: false FAILs, false PASSes, incorrect NOT_ASSESSABLE.

- [ ] **Step 2: For each misclassification, document root cause**

For each error, trace through the pipeline context and document:
- Which rule was affected
- What evidence was available vs what was needed
- Which pipeline component failed (extraction? reconciliation? confidence? assessability?)
- Whether the error is a genuine system limitation or a data gap

- [ ] **Step 3: Categorise errors into systemic vs incidental**

Group errors into: (a) systemic — would occur on any similar input; (b) incidental — specific to one data point's quirks; (c) data gap — caused by synthetic data limitations.

- [ ] **Step 4: Write narrative summaries for dissertation**

Write 2–3 paragraph narratives for the top 3–5 most informative errors. These become the "Discussion" section vignettes.

- [ ] **Step 5: Commit**

```bash
git add docs/ERROR_ANALYSIS.md
git commit -m "docs: qualitative error analysis with per-misclassification narratives"
```

---

## Phase 8b: Architectural Polish & Final Preparation

P0–P2 items from the architectural review, plus documentation cleanup.

---

### Task 7: P0 — Add @runtime_checkable to Protocol interfaces

**Why:** Enables `isinstance()` checks for Protocol types at runtime, improving debuggability.

**Files:**
- Modify: `src/planproof/interfaces/extraction.py`
- Modify: `src/planproof/interfaces/graph.py`
- Modify: `src/planproof/interfaces/reasoning.py`
- Modify: `src/planproof/interfaces/output.py`
- Modify: `src/planproof/interfaces/pipeline.py`
- Modify: `src/planproof/interfaces/cache.py`
- Modify: `src/planproof/interfaces/llm.py`

- [ ] **Step 1: Add `@runtime_checkable` decorator to every Protocol class in `interfaces/`**

Add `from typing import runtime_checkable` and decorate each Protocol class. For each file in `src/planproof/interfaces/`, add the decorator above every `class ...Protocol):` definition.

- [ ] **Step 2: Run mypy and tests**

Run: `make typecheck && make test`
Expected: All pass — `@runtime_checkable` is purely additive.

- [ ] **Step 3: Commit**

```bash
git add src/planproof/interfaces/
git commit -m "refactor: add @runtime_checkable to all Protocol interfaces (P0)"
```

---

### Task 8: P1 — XML-wrap document text in LLM prompts for injection defence

**Why:** LLM prompts should wrap user-supplied document text in `<document>` XML tags to reduce prompt injection attack surface.

**Files:**
- Modify: `configs/prompts/form.yaml`
- Modify: `configs/prompts/report.yaml`
- Modify: `configs/prompts/certificate.yaml`
- Modify: `configs/prompts/drawing.yaml`
- Modify: `src/planproof/ingestion/entity_extractor.py` (if text is interpolated there)
- Test: `tests/ingestion/test_entity_extractor.py` — verify prompt includes XML tags

- [ ] **Step 1: Read current prompt templates and entity extractor**

Read the YAML prompt templates and entity_extractor.py to understand how document text is interpolated into prompts.

- [ ] **Step 2: Wrap the `{document_text}` placeholder in XML tags**

In each prompt template, change `{document_text}` to:

```
<document>
{document_text}
</document>
```

- [ ] **Step 3: Write test verifying prompt contains XML tags**

```python
def test_prompt_wraps_document_text_in_xml():
    """Prompt template wraps document text in <document> tags."""
    prompt = loader.load("form", document_text="test content")
    assert "<document>" in prompt
    assert "test content" in prompt
    assert "</document>" in prompt
```

- [ ] **Step 4: Run tests**

Run: `pytest -x -q`

- [ ] **Step 5: Commit**

```bash
git add configs/prompts/ src/planproof/ingestion/ tests/ingestion/
git commit -m "security: wrap document text in XML tags for prompt injection defence (P1)"
```

---

### Task 9: P2 — Failed pipeline steps populate default outputs

**Why:** If a step fails mid-pipeline, downstream steps may KeyError on missing context keys. Each step should populate its default output keys on failure so the pipeline degrades gracefully.

**Files:**
- Modify: `src/planproof/pipeline/pipeline.py` — add default output population on step failure
- Test: `tests/pipeline/test_pipeline.py` — verify failed step produces default context keys

- [ ] **Step 1: Read pipeline error handling to understand current failure mode**

Read `src/planproof/pipeline/pipeline.py` exception handling to see what happens when a step raises.

- [ ] **Step 2: Write failing test — failed step still populates default keys**

```python
def test_failed_step_preserves_default_context_keys():
    """A failing step should not prevent downstream access to context keys."""
    pipeline = Pipeline()

    class FailingStep:
        name = "failing"
        def execute(self, context):
            raise RuntimeError("boom")

    class DownstreamStep:
        name = "downstream"
        def execute(self, context):
            # Should not KeyError — reconciled_evidence should have a default
            _ = context.get("reconciled_evidence", {})
            return {"success": True, "message": "ok", "artifacts": {}}

    pipeline.register(FailingStep())
    pipeline.register(DownstreamStep())
    report = pipeline.run(Path("/tmp/fake"))
    # Pipeline should complete (partial success) not crash
    assert report is not None
```

- [ ] **Step 3: Add default output population in pipeline exception handler**

In the exception handler for step execution, ensure common context keys have defaults:

```python
except Exception as exc:
    # Ensure downstream steps have safe defaults
    context.setdefault("reconciled_evidence", {})
    context.setdefault("assessability_results", [])
    context.setdefault("verdicts", [])
    # ... existing error handling
```

- [ ] **Step 4: Run tests**

Run: `pytest -x -q`

- [ ] **Step 5: Commit**

```bash
git add src/planproof/pipeline/pipeline.py tests/pipeline/test_pipeline.py
git commit -m "fix: populate default context keys on step failure for graceful degradation (P2)"
```

---

### Task 10: Update EXECUTION_STATUS.md and GAPS_AND_IDEAS.md

**Files:**
- Modify: `docs/EXECUTION_STATUS.md`
- Modify: `docs/GAPS_AND_IDEAS.md`

- [ ] **Step 1: Mark Gap #1 and Gap #2 as RESOLVED in GAPS_AND_IDEAS.md**

Update status to RESOLVED with date and brief fix description.

- [ ] **Step 2: Mark Gap #6 as RESOLVED if datagen was enriched**

Update R003 synthetic data gap status.

- [ ] **Step 3: Update EXECUTION_STATUS.md Phase 7 to Complete**

Mark all Phase 7 checklist items as done. Update project statistics (test count, commit count, etc.).

- [ ] **Step 4: Add Phase 8 section to EXECUTION_STATUS.md**

Document Phase 8a (evaluation enrichment) and Phase 8b (architectural polish) as complete with dates.

- [ ] **Step 5: Update "Next Steps" section**

Replace current next steps with dissertation write-up tasks: chapter structure, key figures to include, evaluation narrative.

- [ ] **Step 6: Commit**

```bash
git add docs/EXECUTION_STATUS.md docs/GAPS_AND_IDEAS.md
git commit -m "docs: update execution status and gaps for Phase 7b-8 completion"
```

---

## Phase 9: Boundary Verification Pipeline (Three-Tier)

This is the high-value new feature from GAPS_AND_IDEAS.md. It verifies that the applicant's red-line site boundary is consistent with authoritative land records using three independent verification tiers. The existing C003 rule (`configs/rules/c003_boundary_validation.yaml`) is a simplified area-comparison placeholder — Phase 9 replaces it with a real multi-source boundary verification system.

**Key insight:** The OS base map is already baked into UK location plan documents. The VLM can see both the red line and OS property boundaries in the same image — this replicates what a planning officer actually does. No expensive GIS pipeline needed.

---

### Task 11: Tier 1 — VLM Boundary Visual Alignment

**What:** Given a location plan image (which contains a red-line boundary drawn on an OS base map), use GPT-4o to assess whether the red line aligns with visible property boundaries, or whether it extends into highways, cuts through neighbours, etc.

**Output:** `ALIGNED / MISALIGNED / UNCLEAR` + specific issues list + confidence score.

**Files:**
- Create: `src/planproof/ingestion/boundary_verifier.py` — `BoundaryVisualVerifier` class implementing Tier 1
- Create: `configs/prompts/boundary_visual.yaml` — VLM prompt template for boundary alignment analysis
- Create: `src/planproof/schemas/boundary.py` — `BoundaryAlignmentResult`, `BoundaryVerificationStatus`, `BoundaryTierResult` schemas
- Test: `tests/ingestion/test_boundary_verifier.py`

- [ ] **Step 1: Define boundary verification schemas**

Create `src/planproof/schemas/boundary.py` with:
- `BoundaryVerificationStatus` enum: `CONSISTENT`, `DISCREPANCY_DETECTED`, `INSUFFICIENT_DATA`
- `BoundaryAlignmentResult` (Tier 1): `status` (ALIGNED/MISALIGNED/UNCLEAR), `issues` (list of strings), `confidence` (float)
- `BoundaryTierResult`: `tier` (1/2/3), `status`, `detail` (union of tier-specific results)
- `BoundaryVerificationReport`: `tier_results` (list), `combined_status`, `combined_confidence`

- [ ] **Step 2: Write failing test for BoundaryVisualVerifier**

```python
def test_boundary_visual_verifier_returns_alignment_result(mock_vision_client):
    """Tier 1 VLM verifier returns an alignment result from location plan image."""
    verifier = BoundaryVisualVerifier(vision_client=mock_vision_client)
    result = verifier.verify(image_path=Path("test_location_plan.png"))
    assert result.status in ("ALIGNED", "MISALIGNED", "UNCLEAR")
    assert 0.0 <= result.confidence <= 1.0
    assert isinstance(result.issues, list)
```

- [ ] **Step 3: Create VLM prompt template for boundary analysis**

Create `configs/prompts/boundary_visual.yaml`:
- System prompt explaining the task: inspect the red-line boundary on the location plan, compare against visible OS property boundaries
- Ask for: alignment status, list of specific issues (e.g. "red line extends beyond property boundary on north side"), confidence
- Output format: JSON with `status`, `issues`, `confidence` fields
- Include `<document>` XML wrapping per P1 convention

- [ ] **Step 4: Implement BoundaryVisualVerifier**

Create `src/planproof/ingestion/boundary_verifier.py`:
- Accepts a `VisionClient` (same interface as existing VLM pipeline)
- Loads the `boundary_visual` prompt template
- Sends the location plan image to GPT-4o with the prompt
- Parses the JSON response into `BoundaryAlignmentResult`
- Returns `UNCLEAR` with confidence 0.0 if the image is not a location plan or VLM call fails

- [ ] **Step 5: Run tests**

Run: `pytest tests/ingestion/test_boundary_verifier.py -v`

- [ ] **Step 6: Commit**

```bash
git add src/planproof/schemas/boundary.py src/planproof/ingestion/boundary_verifier.py configs/prompts/boundary_visual.yaml tests/ingestion/test_boundary_verifier.py
git commit -m "feat(boundary): Tier 1 VLM visual alignment verifier for red-line boundaries"
```

---

### Task 12: Tier 2 — Scale-Bar Measurement & Area Discrepancy

**What:** Extract the scale bar from the location plan, estimate site dimensions (frontage, depth, area in m²), and compare against the declared site area on the application form. Flag if discrepancy >15%.

**Output:** Estimated measurements + discrepancy flag + confidence.

**Files:**
- Modify: `src/planproof/ingestion/boundary_verifier.py` — add `ScaleBarMeasurer` class
- Create: `configs/prompts/boundary_scalebar.yaml` — VLM prompt for scale-bar extraction
- Modify: `src/planproof/schemas/boundary.py` — add `ScaleBarResult` schema
- Test: `tests/ingestion/test_boundary_verifier.py` — add Tier 2 tests

- [ ] **Step 1: Add ScaleBarResult schema**

In `src/planproof/schemas/boundary.py`, add:
- `ScaleBarResult`: `estimated_frontage_m` (float | None), `estimated_depth_m` (float | None), `estimated_area_m2` (float | None), `declared_area_m2` (float | None), `discrepancy_pct` (float | None), `discrepancy_flag` (bool), `confidence` (float)

- [ ] **Step 2: Write failing test for ScaleBarMeasurer**

```python
def test_scalebar_measurer_flags_discrepancy(mock_vision_client):
    """Tier 2 flags area discrepancy >15% between VLM estimate and declared area."""
    measurer = ScaleBarMeasurer(vision_client=mock_vision_client)
    result = measurer.measure(
        image_path=Path("test_location_plan.png"),
        declared_area_m2=200.0,
    )
    assert isinstance(result.discrepancy_flag, bool)
    assert result.estimated_area_m2 is not None
```

- [ ] **Step 3: Create VLM prompt template for scale-bar measurement**

Create `configs/prompts/boundary_scalebar.yaml`:
- Instruct VLM to identify the scale bar, read its ratio (e.g. 1:1250)
- Estimate site frontage and depth from the red-line boundary relative to scale
- Calculate approximate area in m²
- Output JSON: `scale_ratio`, `frontage_m`, `depth_m`, `area_m2`, `confidence`

- [ ] **Step 4: Implement ScaleBarMeasurer**

In `src/planproof/ingestion/boundary_verifier.py`:
- Sends location plan image + scale-bar prompt to VLM
- Parses estimated measurements
- Compares estimated area against `declared_area_m2`
- Sets `discrepancy_flag = True` if `abs(estimated - declared) / declared > 0.15`
- Returns `ScaleBarResult`

- [ ] **Step 5: Run tests**

Run: `pytest tests/ingestion/test_boundary_verifier.py -v`

- [ ] **Step 6: Commit**

```bash
git add src/planproof/ingestion/boundary_verifier.py src/planproof/schemas/boundary.py configs/prompts/boundary_scalebar.yaml tests/ingestion/test_boundary_verifier.py
git commit -m "feat(boundary): Tier 2 scale-bar measurement and area discrepancy detection"
```

---

### Task 13: Tier 3 — HMLR INSPIRE Address Cross-Reference

**What:** Given the site address and postcode, look up the UPRN via OS Places API (free tier), then query HMLR INSPIRE index polygons (free bulk download) for the registered title boundary area. Flag over-claiming if the declared area exceeds the INSPIRE polygon area by >50%.

**External data:**
- OS Places API (free tier) — UPRN lookup by address
- HMLR INSPIRE Index Polygons — free bulk download (GeoPackage/GML), contains registered title extents

**Files:**
- Create: `src/planproof/ingestion/boundary_reference.py` — `BoundaryReferenceProvider` with OS Places + INSPIRE lookup
- Create: `src/planproof/schemas/boundary.py` additions — `AddressCrossRefResult` schema
- Create: `configs/boundary_reference.yaml` — API endpoints, INSPIRE data path, thresholds
- Test: `tests/ingestion/test_boundary_reference.py`

- [ ] **Step 1: Add AddressCrossRefResult schema**

In `src/planproof/schemas/boundary.py`, add:
- `AddressCrossRefResult`: `uprn` (str | None), `inspire_polygon_area_m2` (float | None), `declared_area_m2` (float | None), `area_ratio` (float | None), `over_claiming_flag` (bool), `confidence` (float)

- [ ] **Step 2: Define BoundaryReferenceProvider Protocol**

In `src/planproof/interfaces/extraction.py` (or a new `src/planproof/interfaces/boundary.py`), add:

```python
class BoundaryReferenceProvider(Protocol):
    """Contract: cross-reference site boundary against authoritative land records."""
    def lookup_uprn(self, address: str, postcode: str) -> str | None: ...
    def get_inspire_area(self, uprn: str) -> float | None: ...
```

- [ ] **Step 3: Write failing test for BoundaryReferenceProvider**

```python
def test_boundary_reference_flags_overclaiming(mock_os_places, mock_inspire_data):
    """Tier 3 flags over-claiming when declared area > 1.5x INSPIRE polygon area."""
    provider = BoundaryReferenceProvider(
        os_places_client=mock_os_places,
        inspire_data_path=Path("test_inspire.gpkg"),
    )
    result = provider.cross_reference(
        address="123 Test Street",
        postcode="BS1 1AA",
        declared_area_m2=500.0,
    )
    assert result.over_claiming_flag is True  # INSPIRE area is 300m², ratio = 1.67
```

- [ ] **Step 4: Create boundary reference config**

Create `configs/boundary_reference.yaml`:
```yaml
os_places_api:
  base_url: "https://api.os.uk/search/places/v1"
  # API key loaded from env: OS_PLACES_API_KEY
inspire_data:
  path: "data/reference/inspire_polygons.gpkg"  # Downloaded from HMLR
over_claiming_threshold: 1.5  # Flag if declared / INSPIRE > this ratio
```

- [ ] **Step 5: Implement BoundaryReferenceProvider**

Create `src/planproof/ingestion/boundary_reference.py`:
- `lookup_uprn()`: GET request to OS Places API with address+postcode, parse UPRN from response
- `get_inspire_area()`: Load INSPIRE GeoPackage (fiona or geopandas), query by UPRN or spatial intersection, return polygon area in m²
- `cross_reference()`: Combines both lookups, computes area ratio, sets `over_claiming_flag`
- Graceful fallback: if OS Places returns no match or INSPIRE has no polygon, return `INSUFFICIENT_DATA` with confidence 0.0
- Note: INSPIRE data is a large bulk download (~2GB). For tests, use a small fixture GeoPackage with 2–3 test polygons.

- [ ] **Step 6: Run tests**

Run: `pytest tests/ingestion/test_boundary_reference.py -v`

- [ ] **Step 7: Commit**

```bash
git add src/planproof/ingestion/boundary_reference.py src/planproof/interfaces/boundary.py src/planproof/schemas/boundary.py configs/boundary_reference.yaml tests/ingestion/test_boundary_reference.py
git commit -m "feat(boundary): Tier 3 HMLR INSPIRE address cross-reference with over-claiming detection"
```

---

### Task 14: Combined Boundary Verification Pipeline Step

**What:** Wire the three tiers into a single `BoundaryVerificationStep` that runs all applicable tiers, combines results, and feeds into SABLE as evidence for boundary compliance rule C003.

**Files:**
- Create: `src/planproof/pipeline/steps/boundary_verification.py` — `BoundaryVerificationStep`
- Modify: `src/planproof/bootstrap.py` — wire BoundaryVerificationStep into pipeline
- Modify: `configs/rules/c003_boundary_validation.yaml` — update to use combined boundary evidence
- Test: `tests/pipeline/steps/test_boundary_verification.py`

- [ ] **Step 1: Write failing test for BoundaryVerificationStep**

```python
def test_boundary_verification_step_combines_tiers(mock_verifier, mock_measurer, mock_reference):
    """BoundaryVerificationStep runs available tiers and produces combined status."""
    step = BoundaryVerificationStep(
        visual_verifier=mock_verifier,
        scale_measurer=mock_measurer,
        reference_provider=mock_reference,
    )
    context = {
        "entities": [...],  # Must include location plan + address entities
        "metadata": {"input_dir": "/tmp/test"},
    }
    result = step.execute(context)
    assert result["success"]
    assert "boundary_verification" in context
    report = context["boundary_verification"]
    assert report.combined_status in ("CONSISTENT", "DISCREPANCY_DETECTED", "INSUFFICIENT_DATA")
```

- [ ] **Step 2: Implement BoundaryVerificationStep**

Create `src/planproof/pipeline/steps/boundary_verification.py`:
- Identify location plan images from `context["entities"]` (look for classified documents with type DRAWING, subtype LOCATION_PLAN)
- Run Tier 1 (visual alignment) on each location plan image
- Run Tier 2 (scale-bar) on each location plan image + declared site area from form entities
- Run Tier 3 (INSPIRE cross-ref) using address + postcode from form entities
- Combine: if any tier detects DISCREPANCY → `DISCREPANCY_DETECTED`; if all agree → `CONSISTENT`; if insufficient data → `INSUFFICIENT_DATA`
- Store `BoundaryVerificationReport` in `context["boundary_verification"]`
- Convert combined result to `ExtractedEntity` with attribute `boundary_status` so it flows into SABLE evidence

- [ ] **Step 3: Update C003 rule to use boundary verification evidence**

Update `configs/rules/c003_boundary_validation.yaml`:
```yaml
rule_id: C003
description: "Site boundary must be consistent with authoritative land records"
policy_source: "BCC Validation Checklist"
evaluation_type: enum_check
parameters:
  attribute: boundary_status
  allowed_values: ["CONSISTENT"]
required_evidence:
  - attribute: boundary_status
    acceptable_sources: ["BOUNDARY_VERIFICATION"]
    min_confidence: 0.60
    spatial_grounding: null
```

- [ ] **Step 4: Wire into bootstrap**

In `src/planproof/bootstrap.py`, add boundary verification step registration after VLM extraction and before reconciliation:
- Create `_create_boundary_verifier(config)` factory
- Only register if location plan documents are expected (configurable via ablation or always-on)
- Tier 3 is optional — only if `OS_PLACES_API_KEY` env var is set and INSPIRE data path exists

- [ ] **Step 5: Run tests**

Run: `pytest tests/pipeline/steps/test_boundary_verification.py -v`
Run: `pytest -x -q` (full suite)

- [ ] **Step 6: Commit**

```bash
git add src/planproof/pipeline/steps/boundary_verification.py src/planproof/bootstrap.py configs/rules/c003_boundary_validation.yaml tests/pipeline/steps/test_boundary_verification.py
git commit -m "feat(boundary): combined three-tier boundary verification pipeline step, replaces simplified C003"
```

---

### Task 15: Synthetic boundary test data & E2E test

**What:** Generate synthetic location plan images with red-line boundaries for boundary verification testing. Add an E2E test that exercises the full boundary pipeline.

**Files:**
- Modify: `src/planproof/datagen/rendering/site_plan_generator.py` — add location plan variant with red-line boundary + scale bar
- Create: `configs/datagen/rules/c003_boundary.yaml` — boundary verification datagen config
- Test: `tests/test_e2e_boundary.py` — E2E boundary verification test

- [ ] **Step 1: Add location plan generation with red-line boundary**

Extend `SitePlanGenerator` (or create a new `LocationPlanGenerator`) to render:
- A simplified OS base map grid (rectangles representing properties)
- A red-line boundary polygon overlaid on the grid
- A scale bar (e.g. "1:1250" with measured bar)
- For compliant: red line matches one property. For non-compliant: red line extends beyond property boundary.

- [ ] **Step 2: Add boundary datagen config**

Create `configs/datagen/rules/c003_boundary.yaml`:
```yaml
rule_id: C003
attribute: boundary_status
type: categorical
compliant_values: ["CONSISTENT"]
non_compliant_values: ["DISCREPANCY_DETECTED"]
evidence_locations:
  - doc_type: DRAWING
    drawing_type: location_plan
```

- [ ] **Step 3: Write E2E boundary verification test**

```python
def test_e2e_boundary_verification_consistent(synthetic_compliant_set):
    """Full pipeline correctly identifies consistent boundary from location plan."""
    config = PipelineConfig(...)
    pipeline = build_pipeline(config)
    report = pipeline.run(synthetic_compliant_set)
    c003_verdict = next(v for v in report.verdicts if v.rule_id == "C003")
    assert c003_verdict.outcome == "PASS"
```

- [ ] **Step 4: Run E2E test (requires GPT-4o API key)**

Run: `pytest tests/test_e2e_boundary.py -v --timeout=120`
Note: This requires `OPENAI_API_KEY` for VLM calls. Skip in CI, run locally.

- [ ] **Step 5: Commit**

```bash
git add src/planproof/datagen/ configs/datagen/rules/c003_boundary.yaml tests/test_e2e_boundary.py
git commit -m "feat(boundary): synthetic location plan generation and E2E boundary verification test"
```

---

### Task 16: Dissertation limitations section for boundary verification

**What:** Document the known limitations of boundary verification for honest framing in the dissertation.

**Files:**
- Modify: `docs/GAPS_AND_IDEAS.md` — update boundary verification entry with implementation status and limitations

- [ ] **Step 1: Update GAPS_AND_IDEAS.md boundary section**

Mark the Boundary Verification Pipeline as IMPLEMENTED. Document:
- VLM catches gross discrepancies, not survey-grade (1–2m) boundary precision
- Scan/photo quality affects reliability
- Cannot detect cases where OS base map itself is outdated
- Legal boundaries are deliberately imprecise ("general boundaries" under Land Registration Act 2002 s.60)
- Tier 3 depends on OS Places API (free tier, rate-limited) and HMLR INSPIRE data availability
- Multi-plan consistency (location plan vs block plan) is deferred

- [ ] **Step 2: Commit**

```bash
git add docs/GAPS_AND_IDEAS.md
git commit -m "docs: boundary verification limitations for dissertation"
```

---

## Phase 8c: Extraction Evaluation Track

Measures extraction accuracy independently from reasoning accuracy. Compares LLM/VLM-extracted entities against ground truth, then feeds real (imperfect) extractions into the reasoning layer to produce an error attribution analysis: **when the system gets a verdict wrong, was it extraction or reasoning that failed?**

Depends on Phase 8a completing (needs enriched synthetic data + oracle-extraction ablation results as baseline).

---

### Task 17: Extraction accuracy metrics infrastructure

**What:** Build the framework to compare extracted entities against ground truth entities from synthetic data. Measure per-attribute precision, recall, and value accuracy.

**Files:**
- Create: `src/planproof/evaluation/extraction_metrics.py` — `ExtractionEvaluator` class
- Create: `src/planproof/schemas/extraction_eval.py` — `ExtractionResult`, `AttributeMatch`, `ExtractionReport` schemas
- Test: `tests/evaluation/test_extraction_metrics.py`

- [ ] **Step 1: Define extraction evaluation schemas**

Create `src/planproof/schemas/extraction_eval.py` with:
- `AttributeMatch`: `attribute` (str), `expected_value` (Any), `extracted_value` (Any | None), `value_correct` (bool), `source_document` (str), `extraction_method` (str)
- `ExtractionReport`: `matches` (list[AttributeMatch]), `precision` (float), `recall` (float), `value_accuracy` (float — fraction of detected attributes with correct values)

- [ ] **Step 2: Write failing test for ExtractionEvaluator**

```python
def test_extraction_evaluator_computes_precision_recall():
    """Extraction evaluator compares extracted entities against ground truth."""
    gt_entities = [
        {"attribute": "building_height", "value": "3.5", "source": "elevation.pdf"},
        {"attribute": "rear_garden_depth", "value": "10.0", "source": "site_plan.pdf"},
        {"attribute": "site_area", "value": "200.0", "source": "form.pdf"},
    ]
    extracted_entities = [
        {"attribute": "building_height", "value": "3.5"},  # correct
        {"attribute": "rear_garden_depth", "value": "9.8"},  # close but wrong
        # site_area missed entirely
    ]
    evaluator = ExtractionEvaluator(tolerance=0.05)
    report = evaluator.evaluate(gt_entities, extracted_entities)
    assert report.recall == 2 / 3  # found 2 of 3
    assert report.precision == 1.0  # no false positives
    assert report.value_accuracy == 0.5  # 1 of 2 values correct within tolerance
```

- [ ] **Step 3: Implement ExtractionEvaluator**

Create `src/planproof/evaluation/extraction_metrics.py`:
- Match extracted entities to GT by attribute name (use SemanticSimilarity for fuzzy matching — already exists)
- For matched pairs, compare values with configurable numeric tolerance (default 5%)
- Compute precision (extracted that match a GT attribute / total extracted)
- Compute recall (GT attributes that were extracted / total GT)
- Compute value accuracy (correct values / total matched)
- Return `ExtractionReport` with per-attribute `AttributeMatch` details

- [ ] **Step 4: Run tests**

Run: `pytest tests/evaluation/test_extraction_metrics.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/planproof/schemas/extraction_eval.py src/planproof/evaluation/extraction_metrics.py tests/evaluation/test_extraction_metrics.py
git commit -m "feat(eval): extraction accuracy metrics — precision, recall, value accuracy"
```

---

### Task 18: Run extraction on synthetic PDFs and compare against GT

**What:** Run the full extraction pipeline (classification → text extraction → VLM extraction) on synthetic PDF documents, then compare extracted entities against ground truth from `ground_truth.json` sidecar files.

**Files:**
- Create: `scripts/run_extraction_eval.py` — script that runs extraction on synthetic data and evaluates
- Output: `results/extraction/` — per-set and aggregate extraction accuracy results

- [ ] **Step 1: Write the extraction evaluation runner script**

Create `scripts/run_extraction_eval.py`:
- Load synthetic dataset sets (compliant + non-compliant + edge-case)
- For each set: run classification + text extraction + VLM extraction steps only (not reasoning)
- Load `ground_truth.json` sidecar for each set
- Compare extracted entities against GT using `ExtractionEvaluator`
- Save per-set results as JSON to `results/extraction/`
- Save aggregate summary (mean precision, recall, value accuracy across all sets, broken down by document type and extraction method)

- [ ] **Step 2: Run extraction on the 15 synthetic sets**

Run: `python scripts/run_extraction_eval.py --data-dir data/synthetic --output-dir results/extraction`

Note: Requires `OPENAI_API_KEY` for GPT-4o VLM calls and `GROQ_API_KEY` for Groq LLM calls. Budget ~$2-3 for GPT-4o. Cache all responses via SQLiteLLMCache for reproducibility.

- [ ] **Step 3: Inspect results — document extraction accuracy per attribute and per method**

Review the JSON output. Expected findings:
- Text extraction (pdfplumber + Groq) should be high accuracy on form data
- VLM extraction (GPT-4o) should be moderate accuracy on drawing measurements
- Some attributes may be completely missed (especially R003 area attributes)

- [ ] **Step 4: Commit**

```bash
git add scripts/run_extraction_eval.py results/extraction/
git commit -m "feat(eval): run extraction evaluation on synthetic PDFs, measure accuracy"
```

---

### Task 19: Analyse extraction failures and identify worst-performing prompts

**What:** Using extraction eval results from Task 18, identify which attributes/document types have the worst extraction accuracy. Categorise failure modes (missed entirely, wrong value, wrong unit, hallucinated) and determine which prompts need improvement.

**Files:**
- Create: `docs/EXTRACTION_FAILURE_ANALYSIS.md` — structured analysis of extraction failures
- No code changes — this is analysis only, feeding into Task 20

- [ ] **Step 1: Load extraction results and group failures by category**

From `results/extraction/` JSON files, categorise each GT attribute that was missed or wrong:
- `MISSED` — attribute not extracted at all
- `WRONG_VALUE` — attribute found but numeric value incorrect beyond tolerance
- `WRONG_UNIT` — value correct but unit misinterpreted (e.g. feet vs metres)
- `HALLUCINATED` — extracted attribute not in GT (false positive)
- `WRONG_ATTRIBUTE_NAME` — value correct but attribute name doesn't match (semantic similarity would catch this)

- [ ] **Step 2: Rank prompts by failure rate**

For each prompt template (form, drawing, spatial_zeroshot, spatial_structured_stage1/2):
- Count failures per template
- Identify the most common failure mode per template
- Note specific examples of what went wrong

- [ ] **Step 3: Document findings in EXTRACTION_FAILURE_ANALYSIS.md**

Structure:
- Per-prompt failure summary table
- Top 5 worst failure examples with extracted text vs GT
- Hypothesised root causes (prompt too vague, missing attribute guidance, wrong output format, etc.)
- Specific improvement recommendations for each prompt

- [ ] **Step 4: Commit**

```bash
git add docs/EXTRACTION_FAILURE_ANALYSIS.md
git commit -m "docs: extraction failure analysis — categorised failures by prompt and attribute"
```

---

### Task 20: Improve extraction prompts based on failure analysis

**What:** Revise LLM/VLM prompt templates to address the specific failure modes identified in Task 19. This is an iterative prompt tuning loop: improve → re-run → measure delta.

**Files:**
- Modify: `configs/prompts/form.yaml` — improve based on form extraction failures
- Modify: `configs/prompts/drawing.yaml` — improve based on drawing extraction failures
- Modify: `configs/prompts/spatial_zeroshot.yaml` — improve based on VLM extraction failures
- Modify: `configs/prompts/spatial_structured_stage1.yaml` and `spatial_structured_stage2.yaml` — improve structured VLM
- Test: Re-run extraction eval to measure improvement

Improvements to apply (based on common VLM/LLM extraction failure patterns):
- **Explicit attribute list per document type** — tell the LLM exactly which attributes to look for (e.g. "Extract: building_height, rear_garden_depth, number_of_storeys" for elevation drawings)
- **Unit disambiguation** — instruct "always return values in metres, convert from feet if necessary"
- **Plausible range hints** — "building_height is typically 2–15m; rear_garden_depth is typically 3–30m"
- **Output schema enforcement** — tighten JSON schema in prompt to reduce hallucinated fields
- **Drawing-subtype specific attribute lists** — ELEVATION gets height attributes, SITE_PLAN gets area/setback attributes, FLOOR_PLAN gets room dimensions

- [ ] **Step 1: Revise form extraction prompt**

Update `configs/prompts/form.yaml`:
- Add explicit attribute list for planning application forms (site_area, certificate_type, address, applicant_name, etc.)
- Add unit expectations and plausible ranges
- Tighten JSON output schema

- [ ] **Step 2: Revise drawing/VLM prompts**

Update spatial prompts:
- Add per-subtype attribute target lists (what to look for in elevations vs site plans vs floor plans)
- Add measurement conventions (UK planning uses metres for height, m² for area)
- Add "if you cannot find a value, omit it — do not guess" instruction
- Add plausible range constraints

- [ ] **Step 3: Add post-extraction validation**

Create `src/planproof/ingestion/extraction_validator.py`:
- `ExtractionValidator` checks extracted entities against plausible ranges
- Reject or flag entities with values outside bounds (e.g. building_height > 100m, site_area < 0)
- Reject entities where the extraction confidence is below a minimum (e.g. 0.3)
- Wire into the text extraction and VLM extraction pipeline steps

- [ ] **Step 4: Write tests for ExtractionValidator**

```python
def test_validator_rejects_implausible_height():
    """Heights > 100m are rejected as implausible."""
    entity = ExtractedEntity(attribute="building_height", value="250.0", confidence=0.8, ...)
    validator = ExtractionValidator.from_yaml("configs/extraction_validation.yaml")
    result = validator.validate(entity)
    assert result.valid is False
    assert "implausible" in result.reason
```

- [ ] **Step 5: Create validation config**

Create `configs/extraction_validation.yaml`:
```yaml
plausible_ranges:
  building_height: {min: 0.5, max: 100.0, unit: metres}
  rear_garden_depth: {min: 0.5, max: 100.0, unit: metres}
  site_area: {min: 10.0, max: 100000.0, unit: square_metres}
  building_footprint_area: {min: 5.0, max: 50000.0, unit: square_metres}
min_confidence: 0.3
```

- [ ] **Step 6: Re-run extraction eval with improved prompts**

Run: `python scripts/run_extraction_eval.py --data-dir data/synthetic --output-dir results/extraction_v2`

Compare v1 (Task 18) vs v2 results. Document the delta — which attributes improved, which didn't. This becomes a dissertation figure: "Extraction accuracy before and after prompt tuning."

- [ ] **Step 7: Commit**

```bash
git add configs/prompts/ configs/extraction_validation.yaml src/planproof/ingestion/extraction_validator.py tests/ingestion/test_extraction_validator.py results/extraction_v2/
git commit -m "feat(extraction): improved prompts from failure analysis + post-extraction validation"
```

---

### Task 21: Measure extraction improvement delta

**What:** Produce a before/after comparison of extraction accuracy (Task 18 baseline vs Task 20 improved). This is a key dissertation figure showing that systematic prompt tuning improves extraction.

**Files:**
- Modify: `notebooks/analysis.ipynb` — add extraction improvement comparison figures
- Create: `results/extraction_delta.json` — summary of improvements

- [ ] **Step 1: Compute per-attribute delta**

Compare `results/extraction/` (v1) vs `results/extraction_v2/` (v2):
- Per-attribute: recall delta, value accuracy delta
- Per-document-type: overall precision/recall delta
- Per-extraction-method: text vs VLM improvement

- [ ] **Step 2: Add extraction improvement figures to notebook**

Add to `notebooks/analysis.ipynb`:
- Grouped bar chart: v1 vs v2 recall per attribute
- Grouped bar chart: v1 vs v2 value accuracy per attribute
- Summary table: aggregate precision/recall/value accuracy before and after
- Highlight which prompt changes had the most impact

- [ ] **Step 3: Commit**

```bash
git add notebooks/analysis.ipynb results/extraction_delta.json
git commit -m "feat(eval): extraction improvement delta — before/after prompt tuning comparison"
```

---

### Task 22: Real extraction ablation — feed improved extractions into reasoning

**What:** Instead of oracle (GT) entities, feed real LLM/VLM-extracted entities (with improved prompts from Task 20) into the full reasoning pipeline. Compare verdicts against oracle-extraction results from Phase 8a Task 4 to measure how extraction errors propagate.

**Files:**
- Create: `scripts/run_real_extraction_ablation.py` — runs full pipeline with real extraction
- Modify: `src/planproof/evaluation/results.py` — add `extraction_mode` field (oracle vs real)
- Output: `results/real_extraction/` — verdict results with real extraction

- [ ] **Step 1: Add extraction_mode to result model**

In `src/planproof/evaluation/results.py`, add `extraction_mode: str` field ("oracle" or "real") to the experiment result model so results can be compared side by side.

- [ ] **Step 2: Write real extraction ablation script**

Create `scripts/run_real_extraction_ablation.py`:
- Run the full pipeline (all 11 steps including extraction) on synthetic PDF sets
- Use `full_system` ablation config (all components enabled)
- Save verdicts to `results/real_extraction/`
- Tag results with `extraction_mode="real"`

- [ ] **Step 3: Run on synthetic datasets**

Run: `python scripts/run_real_extraction_ablation.py --data-dir data/synthetic --output-dir results/real_extraction`

- [ ] **Step 4: Commit**

```bash
git add scripts/run_real_extraction_ablation.py src/planproof/evaluation/results.py results/real_extraction/
git commit -m "feat(eval): real extraction ablation — full pipeline with LLM/VLM extraction"
```

---

### Task 23: Error attribution analysis — extraction vs reasoning failures

**What:** Compare oracle-extraction verdicts (Phase 8a) against real-extraction verdicts (Task 22). For every disagreement, trace whether the error originated in extraction (wrong/missing entity) or reasoning (wrong verdict given correct entities). This is the key analysis for the dissertation.

**Files:**
- Create: `src/planproof/evaluation/error_attribution.py` — `ErrorAttributor` class
- Create: `scripts/run_error_attribution.py` — comparison script
- Modify: `notebooks/analysis.ipynb` — add error attribution visualisations
- Output: `results/error_attribution.json` — per-rule, per-set attribution results

- [ ] **Step 1: Define error attribution categories**

Create `src/planproof/evaluation/error_attribution.py`:
- For each (set, rule) pair, compare oracle verdict vs real verdict
- Categories:
  - `BOTH_CORRECT` — same correct verdict in both modes
  - `EXTRACTION_ERROR` — oracle correct, real wrong → extraction caused the failure
  - `REASONING_ERROR` — oracle wrong, real correct or both wrong differently → reasoning layer issue
  - `BOTH_WRONG` — both modes produce wrong verdict → systematic issue
  - `ASSESSMENT_SAVED` — oracle PASS/FAIL, real NOT_ASSESSABLE → assessability correctly caught insufficient real extraction

- [ ] **Step 2: Write failing test**

```python
def test_error_attributor_identifies_extraction_failure():
    """When oracle passes but real fails, attribution is EXTRACTION_ERROR."""
    oracle = {"R001": "PASS"}
    real = {"R001": "FAIL"}
    gt = {"R001": "PASS"}
    result = ErrorAttributor().attribute(oracle, real, gt)
    assert result["R001"] == "EXTRACTION_ERROR"
```

- [ ] **Step 3: Implement ErrorAttributor**

Compare oracle vs real vs ground truth verdicts. Produce per-rule attribution with explanatory detail (which entity was missing or wrong in real extraction).

- [ ] **Step 4: Write comparison script and run**

Create `scripts/run_error_attribution.py`:
- Load oracle results from `results/` (Phase 8a)
- Load real results from `results/real_extraction/` (Task 22)
- Load GT verdicts from synthetic data
- Run ErrorAttributor on all (set, rule) pairs
- Output summary: how many errors are extraction vs reasoning vs both

- [ ] **Step 5: Add error attribution visualisations to analysis notebook**

Add to `notebooks/analysis.ipynb`:
- Stacked bar chart: error attribution categories per rule
- Sankey diagram or confusion matrix: oracle verdict → real verdict flow
- Key statistic: "X% of errors are caused by extraction, Y% by reasoning, Z% caught by assessability"

- [ ] **Step 6: Commit**

```bash
git add src/planproof/evaluation/error_attribution.py scripts/run_error_attribution.py results/error_attribution.json notebooks/analysis.ipynb
git commit -m "feat(eval): error attribution analysis — extraction vs reasoning failure decomposition"
```

---

### Task 24: Run extraction evaluation on real BCC data

**What:** Run the extraction pipeline on the 10 anonymised BCC drawing sets. No ground truth available — this is qualitative analysis only. Document what the VLM extracts from real architectural drawings and whether attribute names and values are plausible.

**Files:**
- Create: `scripts/run_bcc_extraction.py` — extraction runner for BCC data
- Create: `docs/BCC_EXTRACTION_ANALYSIS.md` — qualitative findings
- Output: `results/bcc_extraction/` — extracted entities per BCC set

- [ ] **Step 1: Write BCC extraction runner**

Create `scripts/run_bcc_extraction.py`:
- Load BCC anonymised sets from `data/anonymised/`
- Run classification + extraction steps only
- Save extracted entities as JSON per set
- No GT comparison (no labels available)

- [ ] **Step 2: Run on all 10 BCC sets**

Run: `python scripts/run_bcc_extraction.py --data-dir data/anonymised --output-dir results/bcc_extraction`

- [ ] **Step 3: Qualitative analysis**

Inspect extracted entities manually. Document in `docs/BCC_EXTRACTION_ANALYSIS.md`:
- What attributes does GPT-4o extract from real elevation/floor plan/site plan drawings?
- Are extracted values plausible (e.g. building heights in 2–15m range)?
- What does it miss that a human would find?
- How does extraction quality vary by drawing type and scan quality?
- What would need to change for production-grade extraction?

- [ ] **Step 4: Commit**

```bash
git add scripts/run_bcc_extraction.py results/bcc_extraction/ docs/BCC_EXTRACTION_ANALYSIS.md
git commit -m "feat(eval): extraction evaluation on real BCC data with qualitative analysis"
```

---

## Phase Summary

| Phase | Tasks | Focus | Status |
|-------|-------|-------|--------|
| **7b** | Tasks 1–2 | Critical bug fixes (assessability wiring, rule_id) | **Complete** |
| **8a** | Tasks 3–6 | Reasoning evaluation — enrich data, re-run ablation, error analysis | Pending |
| **8b** | Tasks 7–10 | Architectural polish, documentation | Pending |
| **8c** | Tasks 17–24 | Extraction evaluation — measure, improve, re-measure, error attribution | Pending |
| **9** | Tasks 11–16 | Three-tier boundary verification with HMLR INSPIRE land data | Pending |

### Phase 8c Task Flow

```
Task 17 (extraction metrics infra)
  └──► Task 18 (run extraction v1 — baseline measurement)
         └──► Task 19 (analyse failures — which prompts/attributes are worst?)
                └──► Task 20 (improve prompts + add post-extraction validation)
                       └──► Task 21 (re-run extraction v2 — measure improvement delta)
                              └──► Task 22 (real extraction ablation — feed improved extractions into reasoning)
                                     └──► Task 23 (error attribution — extraction vs reasoning) ◄── key finding
  └──► Task 24 (BCC extraction — qualitative, independent after Task 17)
```

### Full Dependency Graph

```
Task 1 (assessability fix) ──┐  ✅ DONE
Task 2 (rule_id fix) ────────┤  ✅ DONE
                              │
                              ├──► Task 3 (enrich data) ──► Task 4 (re-run ablation) ──► Task 5 (visualisations)
                              │                                                      └──► Task 6 (error analysis)
                              │
                              ├──► Task 7 (runtime_checkable) — independent
                              ├──► Task 8 (XML prompts) — independent
                              └──► Task 9 (default outputs) — independent
                                                                    └──► Task 10 (docs update) — after 8a/8b/8c

Phase 8a ──► Task 17 (extraction metrics) ──► Task 18 (extraction v1 baseline)
                                                  └──► Task 19 (failure analysis)
                                                        └──► Task 20 (improve prompts + validation)
                                                              └──► Task 21 (extraction v2 delta)
                                                                    └──► Task 22 (real extraction ablation)
                                                                          └──► Task 23 (error attribution) ◄── key finding
             Task 24 (BCC extraction) — independent, runs anytime after Task 17

Task 11 (Tier 1 VLM boundary) ──► Task 12 (Tier 2 scale-bar) ──► Task 14 (combined step)
Task 13 (Tier 3 INSPIRE) ───────────────────────────────────────► Task 14 (combined step)
                                                                      └──► Task 15 (synthetic data + E2E)
                                                                      └──► Task 16 (limitations docs)
```

**Execution order:**
1. Phase 8a first (enriched data + oracle ablation baseline — everything depends on this)
2. Phase 8b + 8c + 9 can run in parallel after 8a
3. Phase 8c has an internal pipeline: measure → analyse → improve → re-measure → ablate → attribute
4. Task 10 (docs update) runs last after everything
5. Task 23 (error attribution) is the key dissertation finding — extraction vs reasoning failure decomposition
