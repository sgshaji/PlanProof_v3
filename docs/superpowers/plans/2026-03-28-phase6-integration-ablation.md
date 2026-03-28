# Phase 6: Final Integration & Ablation Prep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the pipeline — wire last stub, implement baselines, add CLI, verify all ablation configs, run E2E tests.

**Architecture:** FlatEvidenceProvider replaces last stub for Ablation B. Naive/Strong baselines as separate runner classes. CLI entry point via `__main__.py`.

**Tech Stack:** Python 3.11+, argparse, existing pipeline infrastructure

**Spec:** `docs/superpowers/specs/2026-03-28-phase6-integration-ablation-design.md`

---

## File Structure

### New Files
- `src/planproof/pipeline/__main__.py` — CLI entry point
- `src/planproof/evaluation/__init__.py` — already exists (empty)
- `src/planproof/evaluation/baselines/__init__.py` — already exists (empty)
- `src/planproof/evaluation/baselines/naive.py` — NaiveBaselineRunner
- `src/planproof/evaluation/baselines/strong.py` — StrongBaselineRunner
- `tests/unit/evaluation/__init__.py`
- `tests/unit/evaluation/test_baselines.py`
- `tests/integration/test_e2e_pipeline.py`
- `tests/integration/test_ablation_configs.py`

### Modified Files
- `src/planproof/bootstrap.py` — Wire FlatEvidenceProvider, remove _StubEvidenceProvider, add baseline runner factory
- `docs/EXECUTION_STATUS.md` — Phase 6 status

---

## Task 1: Wire FlatEvidenceProvider into bootstrap

**Files:**
- Modify: `src/planproof/bootstrap.py`

**What:**
- When `config.ablation.use_snkg` is False (or Neo4j URI not configured):
  - Don't register GraphPopulationStep
  - Use FlatEvidenceProvider as the evidence_provider for AssessabilityEvaluator
  - FlatEvidenceProvider needs entities — but entities aren't available at bootstrap time. Solution: create a lazy wrapper or populate FlatEvidenceProvider during pipeline execution.
  - Pragmatic approach: make FlatEvidenceProvider accept a mutable reference (pass the same list that context["entities"] will point to), or create a `LazyFlatEvidenceProvider` that reads from context at query time.
- Remove `_StubEvidenceProvider` class and `_stub_evidence_provider()` function — this is the last stub

- [ ] Implement, run full test suite, commit

---

## Task 2: Naive Baseline Runner

**Files:**
- Create: `src/planproof/evaluation/baselines/naive.py`
- Create: `tests/unit/evaluation/test_baselines.py`

**What:** `NaiveBaselineRunner` — bypasses the pipeline entirely.

Input: application directory (with classified documents)
Process:
1. Extract text from all documents (OCR/pdfplumber)
2. Concatenate all extracted text into one string
3. Single LLM call: "Given this planning application text, evaluate each rule: R001, R002, R003. For each, respond PASS or FAIL with a brief explanation."
4. Parse JSON response into list[RuleVerdict]
5. No NOT_ASSESSABLE — forced binary PASS/FAIL

Uses existing CachedLLMClient infrastructure. Output contract: `list[RuleVerdict]` with forced PASS/FAIL.

Tests: mock LLM response, verify correct parsing, verify all verdicts are PASS or FAIL (no NOT_ASSESSABLE).

- [ ] Write tests, implement, commit

---

## Task 3: Strong Baseline Runner

**Files:**
- Create: `src/planproof/evaluation/baselines/strong.py`
- Modify: `tests/unit/evaluation/test_baselines.py` (append)

**What:** `StrongBaselineRunner` — per-rule CoT LLM calls.

Input: application directory
Process:
1. Extract text from all documents (same as naive)
2. For each rule (loaded from YAML configs):
   - Construct a rule-specific prompt with chain-of-thought instructions
   - Include rule description, threshold, required evidence
   - Ask LLM to cite specific evidence from the text
   - Parse structured JSON response: {verdict: PASS/FAIL, evidence_cited: [...], explanation: "..."}
3. Assemble list[RuleVerdict] with cited evidence

Output contract: `list[RuleVerdict]` with forced PASS/FAIL + cited evidence (but may cite wrong evidence — that's the point of measuring).

Tests: mock LLM, verify per-rule calls, verify evidence citation in output.

- [ ] Write tests, implement, commit

---

## Task 4: CLI Entry Point

**Files:**
- Create: `src/planproof/pipeline/__main__.py`

**What:** CLI that runs the pipeline on an input directory.

```
python -m planproof.pipeline --input data/synthetic_diverse/compliant/SET_COMPLIANT_100000 --config configs/default.yaml
python -m planproof.pipeline --input <dir> --ablation configs/ablation/ablation_b.yaml
python -m planproof.pipeline --input <dir> --baseline naive
python -m planproof.pipeline --input <dir> --baseline strong
```

Arguments:
- `--input` (required): path to application directory
- `--config` (optional): pipeline config YAML, default `configs/default.yaml`
- `--ablation` (optional): ablation config YAML to override ablation settings
- `--baseline` (optional): "naive" or "strong" — runs baseline instead of pipeline
- `--output` (optional): output file path for JSON report, default stdout
- `--markdown` (optional): output file for Markdown report

Process: load config, build pipeline (or baseline runner), execute, output report as JSON + Markdown.

Tests: basic CLI argument parsing test (not full E2E).

- [ ] Implement, test argument parsing, commit

---

## Task 5: Ablation Config Validation Tests

**Files:**
- Create: `tests/integration/test_ablation_configs.py`

**What:** Verify all 7 ablation configs load and produce valid pipeline configurations.

For each config in configs/ablation/:
1. Load the YAML
2. Merge with default PipelineConfig
3. Call build_pipeline(config) — verify it doesn't crash
4. Verify the expected steps are registered (or not) based on toggles

This doesn't run the pipeline — just verifies bootstrap wiring works for every config.

Skip tests that require Neo4j (full_system, ablation_a) when URI not configured.

- [ ] Write tests, run, commit

---

## Task 6: E2E Integration Tests

**Files:**
- Create: `tests/integration/test_e2e_pipeline.py`

**What:** Run the full pipeline on synthetic data and verify outputs against ground truth.

Test cases:
1. Compliant set → load entities from ground truth, run through pipeline (with FlatEvidenceProvider), verify all Tier 1 rules PASS
2. Non-compliant set → at least one FAIL detected
3. Edge case set → at least one NOT_ASSESSABLE

Use FlatEvidenceProvider (no Neo4j dependency). Mock LLM calls. Feed pre-extracted entities into the pipeline context.

Skip if synthetic data not available.

- [ ] Write tests, run, commit

---

## Task 7: Update execution status + docs + push

**Files:**
- Modify: `docs/EXECUTION_STATUS.md`

**What:**
- Phase 6 → Complete
- Update Next Steps to Phase 7
- Commit all docs, push

- [ ] Update, commit, push
