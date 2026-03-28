# Phase 7: Ablation Study & Evaluation — Design Spec

**Date:** 2026-03-28 | **Depends on:** Phase 6 (all configs validated)

## Goal

Run rigorous ablation experiments, compute metrics, and produce dissertation-ready results.

## Two deliverables

### 1. `scripts/run_ablation.py` — Experiment Runner
- Runs all 7 configurations × test set (sealed synthetic data)
- For each (config, application_set): run pipeline, capture verdicts/assessability/evidence
- Outputs structured JSON results to `data/results/{config_name}/{set_id}.json`
- Resumable: skips already-computed results
- Uses LLM response cache (already built) for reproducibility
- Baselines (naive/strong) run via their respective runner classes
- Ablations A-D + full system run via `build_pipeline()` with appropriate config

### 2. `notebooks/ablation_analysis.ipynb` — Analysis Notebook
- Reads `data/results/` JSON files
- Computes metrics per configuration:
  - **Primary:** Rule violation recall (on non-compliant sets)
  - **Supporting:** Precision, F2 score, automation rate (% rules assessable), assessability rate
- Statistical analysis:
  - Bootstrap confidence intervals (1000 resamples)
  - McNemar's test for paired config comparisons
  - Cohen's h effect sizes
- Generates dissertation figures:
  - Comparison bar chart (all configs side-by-side)
  - Confusion matrices per rule per config
  - NOT_ASSESSABLE analysis (frequency, blocking reasons)
  - Bootstrap CI plots
- Qualitative error analysis section (per-misclassification narrative)

## Metrics definitions

| Metric | Formula | What it measures |
|--------|---------|-----------------|
| Violation recall | TP / (TP + FN) | How many actual violations are detected |
| Precision | TP / (TP + FP) | How many flagged violations are real |
| F2 score | (5 × P × R) / (4P + R) | Recall-weighted F-score (we care more about catching violations) |
| Automation rate | assessable_rules / total_rules | What % of rules the system can evaluate |
| Assessability accuracy | correct NOT_ASSESSABLE / total NOT_ASSESSABLE | Are NOT_ASSESSABLE flags justified |

TP = correctly detected violation (ground truth FAIL, system FAIL)
FP = false alarm (ground truth PASS, system FAIL)
FN = missed violation (ground truth FAIL, system PASS or NOT_ASSESSABLE)

## Key decisions
- Evaluate per-rule, not just per-application (20 apps × 7 rules = 140 evaluations)
- NOT_ASSESSABLE counts as FN for recall (conservative — missed violations matter)
- Frame small sample size honestly, use bootstrap CIs
- Results stored as JSON for reproducibility
