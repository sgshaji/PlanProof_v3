# Phase 6: Final Integration & Ablation Prep — Design Spec

**Date:** 2026-03-28 | **Depends on:** Phase 5 (all pipeline steps implemented)

## Goal

Harden the pipeline for evaluation: wire FlatEvidenceProvider for Ablation B, implement naive/strong baselines, add CLI entry point, verify all 7 ablation configs produce valid output, run E2E tests on synthetic data.

## Components

### 1. FlatEvidenceProvider wiring
- Replace `_StubEvidenceProvider` in bootstrap with `FlatEvidenceProvider` when `use_snkg=False`
- FlatEvidenceProvider is already implemented — just needs wiring into the assessability evaluator and reconciliation step

### 2. Naive + Strong Baselines
- `evaluation_strategy: "naive_llm"` — concatenate OCR text, single LLM call for all rules, forced PASS/FAIL
- `evaluation_strategy: "strong_llm"` — per-rule CoT LLM calls with evidence citation, forced PASS/FAIL
- Both bypass the normal pipeline — implemented as separate code paths in `build_pipeline()` or as a `BaselineRunner`
- These are comparison points for the ablation study, not the main system

### 3. CLI Entry Point
- `python -m planproof.pipeline --input <dir> --config <yaml>` or `--ablation <config>`
- Loads config, builds pipeline, runs on input directory
- Outputs: JSON compliance report + Markdown to stdout/file

### 4. E2E Integration Tests
- Run full pipeline on synthetic compliant/non-compliant/edge-case sets
- Verify against ground truth: correct PASS/FAIL/NOT_ASSESSABLE verdicts
- Verify all 7 ablation configs produce valid (non-crashing) output

### 5. Ablation Config Validation
- Each of the 7 configs (full, A-D, naive, strong) must produce output matching its contract
- Ablation A: entities + populated SNKG (no verdicts)
- Ablation B: verdicts from flat evidence (no graph)
- Ablation C: full pipeline minus gating
- Ablation D: full pipeline minus assessability (forced PASS/FAIL)

## Key decisions
- Naive/strong baselines are separate runners, not pipeline configurations — they have fundamentally different execution paths
- FlatEvidenceProvider wiring is the last stub removal
- CLI outputs both JSON and Markdown
