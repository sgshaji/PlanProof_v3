# PlanProof

**Assessability-Aware Multimodal Planning Compliance Validation Using Neurosymbolic AI and Dempster-Shafer Evidence Theory**

MSc Dissertation -- Data Science with Work Placement, 2025-2026
Partner Organisation: Birmingham City Council (BCC)

---

## Research Question

> *Can a neurosymbolic pipeline that explicitly models evidence sufficiency using Dempster-Shafer theory outperform LLM-only approaches at planning compliance validation, while eliminating false violation verdicts caused by insufficient evidence?*

**Answer: Yes.** The full system produces **zero false violations** across all evaluation scenarios, while removing the assessability engine (ablation_d) produces 93 and naive/CoT LLM baselines produce 126 and 51 respectively. The key mechanism is the SABLE algorithm -- a novel assessability engine grounded in Dempster-Shafer evidence theory that determines whether sufficient trustworthy evidence exists before any rule is evaluated. A spatial containment rule (C006) implemented in the SNKG confirms the neurosymbolic claim: ablation_b (no SNKG) now differs measurably from the full system (66 NA vs 33 NA).

---

## What Is PlanProof?

PlanProof is an AI system that validates UK householder planning applications against regulatory rules. Unlike existing tools that force binary PASS/FAIL verdicts on every rule regardless of available evidence, PlanProof asks a harder question: **is there enough trustworthy evidence to even evaluate this rule?**

When evidence is insufficient or contradictory, the system returns **NOT_ASSESSABLE** with a minimum evidence request -- telling the applicant exactly what's missing. When evidence is present but contested, it returns **PARTIALLY_ASSESSABLE** with belief/plausibility bounds. This mirrors how planning officers actually work: they don't guess when evidence is missing -- they request more information.

### Why This Matters

UK local planning authorities process ~460,000 householder applications per year. Each must be validated against a checklist of regulatory requirements before it can be assessed on planning merit. This validation is:
- **Manual** -- planning officers visually inspect submitted documents
- **Error-prone** -- missing evidence is often confused with non-compliance
- **Time-consuming** -- validation alone takes 30-60 minutes per application

False rejection of valid applications wastes applicant time and council resources. False approval of invalid applications creates legal risk. PlanProof addresses both failure modes.

---

## Novel Contributions

### 1. SABLE Algorithm (Semantic Assessability via Belief-theoretic evidence Logic)

The core research contribution. SABLE replaces ad-hoc if-else assessability logic with a principled framework grounded in Dempster-Shafer evidence theory:

- **Three-valued mass functions** with ignorance mass m(Theta) propagate epistemic uncertainty rather than forcing binary decisions on insufficient data
- **Semantic attribute matching** via sentence-transformer embeddings resolves the attribute canonicalisation problem (e.g., "height" matches "building_height")
- **Concordance adjustment** from reconciliation output modulates ignorance mass based on cross-document agreement
- **Three-state assessability model**: ASSESSABLE / PARTIALLY_ASSESSABLE / NOT_ASSESSABLE

Formal specification: [docs/SABLE_ALGORITHM.md](docs/SABLE_ALGORITHM.md)

### 2. Three-Tier Boundary Verification Pipeline

A novel approach to verifying that an applicant's red-line site boundary is consistent with authoritative land records:

| Tier | Method | What It Catches |
|------|--------|----------------|
| **Tier 1** | VLM visual alignment (GPT-4o) | Red line in wrong place -- extends into highway, cuts through neighbour |
| **Tier 2** | Scale-bar measurement (GPT-4o) | Area inflation -- drawing shows 300m but form claims 500m |
| **Tier 3** | INSPIRE polygon cross-reference | Land grab -- declared area 1.5x larger than Land Registry record |

**Key insight:** The OS base map is already embedded in UK location plan documents. The VLM can see both the red line and property boundaries in the same image -- no expensive GIS pipeline needed.

### 3. Neurosymbolic Architecture with Ablation-Validated Component Contribution

A 12-step pipeline where neural methods (LLMs, VLMs) extract facts and symbolic methods (knowledge graph, deterministic rules) evaluate compliance:

```
Documents ──> Classify ──> Extract (LLM/VLM) ──> Normalise ──> SNKG Graph
                                                                    |
             Compliance  <── Evaluate  <── Assess (SABLE)  <── Reconcile
              Report         Rules          Evidence            Sources
```

Each component's contribution is validated through systematic ablation, plus comparison against two LLM-only baselines:

| System | False FAILs | PASS | true FAIL | NA | Effect |
|---|---|---|---|---|---|
| None (full system) | 0 | 118 | 14 | 33 | Baseline — confident verdicts + zero false violations |
| VLM extraction removed | 0 | 0 | 0 | 297 | All NOT_ASSESSABLE (no evidence without VLM) |
| SNKG graph removed | 0 | 85 | 14 | 66 | 33 fewer PASS — C006 conservation area checks require SNKG graph |
| Confidence gating removed | 0 | 118 | 14 | 33 | Identical to full system — oracle evidence has no low-confidence noise |
| **Assessability removed (SABLE)** | **93** | 184 | 20 | 0 | **Forced binary = 93 false violations on compliant cases** |
| Naive LLM baseline | 126 | 121 | 17 | — | Single LLM call per rule — worse than no-assessability |
| Strong CoT baseline | 51 | 10 | 3 | — | Chain-of-Thought prompting — confuses missing evidence with violations |

---

## Key Results

### 4-System Comparison (final)

| System | PASS | true FAIL | false FAIL |
|---|---|---|---|
| Full system (SABLE) | 118 | 14 | 0 |
| Ablation D (no SABLE) | 184 | 20 | 93 |
| Naive LLM baseline | 121 | 17 | 126 |
| Strong CoT baseline | 10 | 3 | 51 (18/33 sets) |

- **Full system: 0 false FAILs, 118 PASS, 14 true FAILs** across 33 test sets × 9 rules (297 evaluations)
- **Ablation D (no assessability): 93 false FAILs** -- SABLE prevents all 93 by converting to PARTIALLY_ASSESSABLE or NOT_ASSESSABLE
- **ablation_b (no SNKG): 85 PASS vs full_system 118** — SNKG contributes 33 additional PASS verdicts via C006 conservation area spatial containment rule
- **Both LLM baselines far worse** -- CoT prompting does not solve the false-FAIL problem; architecture is required
- **McNemar p<0.0001** (Benjamini-Hochberg corrected) for full_system vs ablation_d
- **Robustness:** SABLE false-FAIL counts stay near 0 across 5 degradation levels (0→5→1→0→0)
- **Threshold sensitivity:** precision=1.0 across all tested thresholds; optimal at theta_high=0.55
- **Belief two-cluster structure:** 0.56 (SINGLE_SOURCE) and 0.96 (DUAL_SOURCE) — direct Dempster combination confirmation

### Extraction Evaluation (Phase 8c + v3)
- **Prompt tuning: precision 0.299 -> 0.715 (+139%)** by narrowing from broad entity types to 7 target attributes
- Recall (0.886 → 1.0) and value accuracy (0.857 → 1.0) on regenerated multi-source data (v3)
- **2x2 False-FAIL Matrix:**

|  | Full System | No Assessability |
|---|---|---|
| **Oracle extraction** | 0 | 93 |
| **Real extraction** | 0 | ~26 |

The architecture is resilient: SABLE produces zero false FAILs regardless of extraction quality.

### Error Attribution and Formal Theory
- The dominant failure mode is architectural (removing SABLE), not data quality or extraction quality
- Removing SABLE produces 93 false FAILs; imperfect extraction alone produces 0
- SABLE formal properties: 5 mathematical proofs (monotonicity, boundedness, determinism, idempotency, composability)

---

## Architecture

### Pipeline Steps (12)

| # | Step | Module | Purpose |
|---|------|--------|---------|
| 1 | Classification | M1 | Rule-based document type detection |
| 2 | Text Extraction | M2 | PdfPlumber + LLM structured extraction |
| 3 | VLM Extraction | M3 | GPT-4o spatial attribute extraction from drawings |
| 4 | Boundary Verification | M3b | Three-tier boundary consistency check |
| 5 | Normalisation | M5 | Unit conversion + address canonicalisation |
| 6 | Graph Population | M5 | Neo4j SNKG entity/relationship creation |
| 7 | Reconciliation | M6 | Pairwise cross-document evidence agreement |
| 8 | Confidence Gating | M7 | Per-method, per-type threshold filtering |
| 9 | Assessability (SABLE) | M8 | D-S evidence sufficiency evaluation |
| 10 | Rule Evaluation | M9 | 7 evaluator types (numeric, ratio, enum, fuzzy, tolerance, diff, boundary) + SNKG spatial containment |
| 11 | Compliance Scoring | M10 | Aggregate verdicts into report |
| 12 | Evidence Requests | M11 | Generate minimum evidence requests for NOT_ASSESSABLE rules |

### Compliance Rules (9)

| Rule | Description | Type |
|------|-------------|------|
| R001 | Max building height <= 8m | Numeric threshold |
| R002 | Min rear garden depth >= 10m | Numeric threshold |
| R003 | Max site coverage <= 50% | Ratio threshold |
| C001 | Certificate type validity (A/B/C/D) | Enum check |
| C002 | Address consistency (form vs drawing) | Fuzzy string match |
| C003 | Boundary area validation (stated vs reference) | Numeric tolerance |
| C004 | Plan change detection (proposed vs approved) | Attribute diff |
| C005 | Three-tier boundary verification | Boundary verification |
| C006 | Conservation area containment check | SNKG spatial containment (Neo4j graph traversal) |

### Design Principles

- **Protocol-based interfaces** -- 17 `@runtime_checkable` Protocol classes, no inheritance hierarchies
- **Composition root** -- single `bootstrap.py` wires all dependencies; business logic never imports concrete types
- **Immutable data** -- frozen dataclasses with tuple collections throughout
- **Seed deterministic** -- same seed always produces identical output
- **Plugin extensible** -- new rules = YAML config, new doc types = one generator class

---

## Quick Start

### Prerequisites

- Python 3.12+
- Groq API key (free: https://console.groq.com) for LLM extraction
- OpenAI API key for GPT-4o VLM extraction and boundary verification

### Installation

```bash
# Clone
git clone https://github.com/sgshaji/PlanProof_v3.git planproof && cd planproof

# Install
pip install -e ".[dev]"

# Configure
cp .env.example .env
# Edit .env with your API keys

# Verify
make lint        # ruff
make typecheck   # mypy --strict
make test        # pytest (917 collected)
```

### Running the Pipeline

```bash
# Run on synthetic data
python -m planproof.pipeline.runner --input data/synthetic_diverse/compliant/SET_COMPLIANT_42000

# Run ablation experiments
python scripts/run_ablation.py --config full_system --data-dir data/synthetic_diverse

# Run extraction evaluation
source .env && python scripts/run_extraction_eval.py --version v1
```

### Research Demo Web UI

A live FastAPI + Jinja2 web interface visualizes the 12-step pipeline in real time using Server-Sent Events (SSE). The UI streams extraction, SNKG population, reconciliation, assessability, and rule evaluation as it happens.

**Features:**
- File upload with document type auto-detection
- Pre-loaded test set buttons (compliant, non-compliant, edge-case)
- SABLE belief gauges for each rule
- Extraction and SNKG graph visualizations
- Reconciliation cross-document agreement
- Three-state assessability badges (ASSESSABLE, PARTIALLY_ASSESSABLE, NOT_ASSESSABLE)
- Verdict cards with evidence summaries
- Ablation comparison matrix
- Dissertation figures gallery

**Run the demo:**

```bash
# Ensure API keys are set
source .env

# Start the web server
uvicorn planproof.web.app:app --port 8000

# Open in browser
# http://localhost:8000
```

The demo runs the full live pipeline (no pre-computed results) — each rule evaluation, extraction step, and SNKG query executes in real time. This allows exploring how different components contribute to verdicts.

---

## Evaluation Infrastructure

### Synthetic Data Generator
- 15 synthetic planning application sets (5 compliant + 5 non-compliant + 5 edge-case)
- 18 attributes per set across 7 rules
- Deterministic generation from YAML configs with seed-based reproducibility
- 8 degradation transforms (scan simulation, rotation, noise, blur)

### Ablation Configurations (7)
| Config | What's Disabled |
|--------|----------------|
| full_system | Nothing (all components) |
| ablation_a | VLM extraction |
| ablation_b | SNKG graph |
| ablation_c | Confidence gating |
| ablation_d | Assessability (SABLE) |
| naive_baseline | Everything except single LLM call |
| strong_baseline | Everything except per-rule CoT LLM |

### Metrics
- Confusion matrix (TP/FP/FN/TN/NOT_ASSESSABLE)
- Recall, Precision, F2 (recall-weighted)
- Automation rate
- Bootstrap confidence intervals
- McNemar's test + Cohen's h effect sizes
- SABLE-specific: belief statistics, blocking reason distribution, component contribution

### Dissertation Figures (15)
All at 300 DPI in `figures/`:
1. Belief distribution violin plot
2. Three-state stacked bar chart
3. Belief vs plausibility scatter
4. Blocking reason distribution
5. False-FAIL prevention bar chart
6. Component contribution table (with McNemar p-values)
7. Concordance heatmap (rule x config)
8. Extraction accuracy (v1 vs v2)
9. Extraction improvement delta
10. 2x2 False-FAIL matrix
11. SABLE oracle vs real extraction comparison
12. Robustness curves (false-FAIL vs degradation level)
13. Robustness true-FAIL retention
14. Threshold sensitivity (precision-recall-automation)
15. True-FAIL distribution across systems

---

## Project Statistics

| Metric | Count |
|--------|-------|
| Total commits | 172 |
| Source files | 118 |
| Test files | 69 |
| Tests collected | 917 |
| Pipeline steps | 12 |
| Compliance rules | 9 (R001–R003 + C001–C006) |
| Evaluator types | 7 |
| Ablation configurations | 7 |
| Synthetic datasets | 33 (9 rules × 33 test sets = 297 evaluations per config) |
| Real BCC datasets | 10 (anonymised, drawings only) |
| INSPIRE cadastral parcels | 346,231 |
| Dissertation figures | 15 |
| Research demo web components | 6 (app.py, pipeline_runner.py, index.html, style.css, app.js, utils.js) |

---

## Documentation

| Document | What It Covers |
|----------|---------------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Component diagram, interface boundaries, data flow |
| [SABLE_ALGORITHM.md](docs/SABLE_ALGORITHM.md) | Formal specification of the SABLE assessability algorithm |
| [EXECUTION_STATUS.md](docs/EXECUTION_STATUS.md) | Phase-by-phase progress tracker |
| [PROJECT_LOG.md](docs/PROJECT_LOG.md) | Chronological development log for dissertation traceability |
| [GAPS_AND_IDEAS.md](docs/GAPS_AND_IDEAS.md) | Known limitations and future work |
| [ERROR_ANALYSIS.md](docs/ERROR_ANALYSIS.md) | Qualitative error analysis with dissertation vignettes |
| [EXTRACTION_ERROR_ATTRIBUTION.md](docs/EXTRACTION_ERROR_ATTRIBUTION.md) | Extraction vs reasoning failure decomposition |
| [docs/adr/](docs/adr/) | Architecture Decision Records |

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.12 |
| Type checking | mypy --strict |
| Linting | ruff |
| Testing | pytest |
| Schemas | pydantic + frozen dataclasses |
| LLM | Groq (llama-3.3-70b-versatile) |
| VLM | OpenAI GPT-4o |
| Knowledge graph | Neo4j Aura (free cloud) |
| Semantic similarity | sentence-transformers |
| GML parsing | xml.etree.ElementTree (pure Python) |
| Geocoding | postcodes.io (free, no API key) |
| Logging | structlog (JSON) |
| CI | GitHub Actions |

---

## Development Phases

| Phase | Name | Status |
|-------|------|--------|
| 0 | Project Foundation | Complete |
| 1 | Synthetic Data Pipeline | Complete |
| 2 | Ingestion Layer (M1-M3) | Complete |
| 3 | Representation Layer (M5) | Complete |
| 4 | Reasoning Layer (M6-M9) | Complete |
| 5 | Output Layer (M10-M12) | Complete |
| 6 | Integration & Ablation Prep | Complete |
| 7 | Ablation Study & SABLE | Complete |
| 8a | SABLE Evaluation Enrichment | Complete |
| 8b | Architectural Polish | Complete |
| 8c | Extraction Evaluation & Error Attribution | Complete |
| 9 | Three-Tier Boundary Verification | Complete |
| DA1 | SNKG Spatial Containment Rule (C006) | Complete |
| -- | Dissertation Write-up | In Progress |

---

## Adding a New Compliance Rule

1. Create `configs/rules/r004_your_rule.yaml` with rule definition
2. If the `evaluation_type` matches an existing one (e.g., `numeric_threshold`), you're done
3. If you need new evaluation logic, create a class in `src/planproof/reasoning/evaluators/` and register it in `bootstrap.py`
4. Add a datagen config in `configs/datagen/rules/` to generate test data
5. Run `python scripts/run_ablation.py` to evaluate

---

## License

This project is part of an MSc dissertation. Contact the author for licensing information.
