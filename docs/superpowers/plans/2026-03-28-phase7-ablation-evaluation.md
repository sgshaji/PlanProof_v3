# Phase 7: Ablation Study & Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run all ablation experiments, compute metrics, produce dissertation-ready figures and tables.

**Architecture:** Runner script executes experiments and outputs JSON results. Jupyter notebook reads results and produces analysis. Clean separation: runner = data production, notebook = data consumption.

**Tech Stack:** Python 3.11+, pandas, matplotlib, seaborn, scipy (bootstrap/McNemar), jupyter

**Spec:** `docs/superpowers/specs/2026-03-28-phase7-ablation-evaluation-design.md`

---

## File Structure

### New Files
- `scripts/run_ablation.py` — Experiment runner (all 7 configs × test sets)
- `src/planproof/evaluation/metrics.py` — Metric computation functions (reusable by notebook)
- `src/planproof/evaluation/results.py` — Result data models + JSON I/O
- `notebooks/ablation_analysis.ipynb` — Analysis and visualization
- `tests/unit/evaluation/test_metrics.py`
- `tests/unit/evaluation/test_results.py`

### Modified Files
- `pyproject.toml` — Add pandas, matplotlib, seaborn, scipy to `[eval]` optional deps
- `Makefile` — Add `make evaluate` target
- `docs/EXECUTION_STATUS.md` — Phase 7 status

---

## Task 1: Result data models + JSON I/O

**Files:**
- Create: `src/planproof/evaluation/results.py`
- Create: `tests/unit/evaluation/test_results.py`

**What:** Pydantic models for storing experiment results.

- `RuleResult` — rule_id, ground_truth_outcome, predicted_outcome, predicted_assessability, config_name, set_id
- `ExperimentResult` — config_name, set_id, rule_results (list[RuleResult]), metadata (timing, entity counts)
- `save_result(result, output_dir)` — write to `data/results/{config}/{set_id}.json`
- `load_result(path) -> ExperimentResult` — read back
- `load_all_results(results_dir) -> list[ExperimentResult]` — load all
- `result_exists(config, set_id, output_dir) -> bool` — for resumability

Tests: round-trip save/load, result_exists check, load_all across configs.

- [ ] Write tests, implement, commit

---

## Task 2: Metric computation functions

**Files:**
- Create: `src/planproof/evaluation/metrics.py`
- Create: `tests/unit/evaluation/test_metrics.py`

**What:** Pure functions for computing evaluation metrics from ExperimentResult lists.

- `compute_confusion_matrix(results, config) -> dict` — TP, FP, FN, TN counts per rule and aggregate
- `compute_recall(cm) -> float` — TP / (TP + FN)
- `compute_precision(cm) -> float` — TP / (TP + FP)
- `compute_f2_score(cm) -> float` — recall-weighted F-score
- `compute_automation_rate(results, config) -> float` — assessable / total
- `compute_assessability_accuracy(results, config) -> float` — correct NOT_ASSESSABLE / total NOT_ASSESSABLE
- `bootstrap_ci(metric_fn, results, n_resamples=1000, ci=0.95) -> tuple[float, float]` — bootstrap confidence intervals
- `mcnemar_test(results_a, results_b) -> tuple[float, float]` — chi-squared statistic + p-value
- `cohens_h(p1, p2) -> float` — effect size for proportion comparison

Ground truth comes from synthetic data ground_truth.json (rule_verdicts field).

Treatment of NOT_ASSESSABLE: counts as FN for recall (conservative — missed violations).

Tests: known inputs → known outputs for each metric, edge cases (zero division, all same outcome).

- [ ] Write tests, implement, commit

---

## Task 3: Ablation runner script

**Files:**
- Create: `scripts/run_ablation.py`

**What:** CLI script that runs all experiments.

```
python scripts/run_ablation.py --data-dir data/synthetic_diverse --output-dir data/results
python scripts/run_ablation.py --config ablation_b --data-dir data/synthetic_diverse  # single config
python scripts/run_ablation.py --resume  # skip already-computed
```

Process:
1. Discover test sets in data_dir (split=test from the sealed split)
2. For each config in [naive, strong, ablation_a, ablation_b, ablation_c, ablation_d, full_system]:
   a. Load ablation YAML from configs/ablation/
   b. For each test set:
      - Skip if result already exists (--resume)
      - Load ground truth from set's ground_truth.json
      - For baselines: extract text, run NaiveBaselineRunner/StrongBaselineRunner
      - For pipeline configs: construct entities from ground truth extractions (to avoid real LLM calls in evaluation), run through reasoning pipeline
      - Compare verdicts against ground truth rule_verdicts
      - Save ExperimentResult to data/results/{config}/{set_id}.json
3. Print summary table when done

Key decision: For evaluation, we feed ground-truth entities directly into the reasoning pipeline (not re-running extraction). This isolates the reasoning layer's contribution. Real extraction quality is tested separately.

For baselines (naive/strong): these DO need LLM calls. Use cached LLM client. If no API key, skip with warning.

- [ ] Implement, test manually on one config, commit

---

## Task 4: Analysis notebook

**Files:**
- Create: `notebooks/ablation_analysis.ipynb`

**What:** Jupyter notebook that reads data/results/ and produces dissertation figures.

Sections:
1. **Data Loading** — load all ExperimentResults, merge with ground truth
2. **Summary Table** — all configs side-by-side: recall, precision, F2, automation rate
3. **Per-Rule Analysis** — breakdown by R001, R002, R003
4. **Confusion Matrices** — heatmap per config
5. **Bootstrap Confidence Intervals** — CI plots for recall and precision
6. **Statistical Comparisons** — McNemar's test: full system vs each ablation, effect sizes
7. **NOT_ASSESSABLE Analysis** — frequency by config, blocking reason distribution
8. **Qualitative Error Analysis** — per-misclassification narrative (template cells to fill in)
9. **Key Findings** — summary for dissertation results chapter

Uses matplotlib/seaborn for figures, pandas for tables. Figures saved to `data/results/figures/`.

- [ ] Create notebook with structure and code cells, commit

---

## Task 5: Makefile + deps + docs + push

**Files:**
- Modify: `pyproject.toml` — add `[eval]` optional deps: pandas, matplotlib, seaborn, scipy, jupyter
- Modify: `Makefile` — add `make evaluate` and `make notebook` targets
- Modify: `docs/EXECUTION_STATUS.md` — Phase 7 status
- Commit all docs, push

- [ ] Update, commit, push
