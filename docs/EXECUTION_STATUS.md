# PlanProof — Execution Status

> **Last updated**: 2026-03-28
> **Current phase**: Phase 5 (Output Layer)
> **Overall status**: Phase 0 complete. **Phase 1 complete.** **Phase 2 complete** (M1 classifier + M2 text extraction + M3 VLM spatial). **Phase 3 complete** (M5 normalisation, Neo4jSNKG, FlatEvidenceProvider). **Phase 4 complete** (M6 reconciliation, M7 confidence gating, M8 assessability, M9 rule evaluation — all wired into bootstrap). Phase 5 (Output Layer) next.

---

## Phase Summary

| Phase | Name | Status | Date Started | Date Completed |
|-------|------|--------|-------------|----------------|
| **Phase 0** | Project Foundation | **Complete** | 2026-03-25 | 2026-03-25 |
| **Phase 1** | Data Pipeline & Synthetic Generation | **Complete** | 2026-03-25 | 2026-03-26 |
| **Phase 2a** | Ingestion Layer (M1, M2) | **Complete** | 2026-03-27 | 2026-03-27 |
| **Phase 2b** | Ingestion Layer (M3 VLM) | **Complete** | 2026-03-27 | 2026-03-27 |
| **Phase 3** | Representation Layer (M5) | **Complete** | 2026-03-28 | 2026-03-28 |
| **Phase 4** | Reasoning Layer (M6–M9) | **Complete** | 2026-03-28 | 2026-03-28 |
| Phase 5 | Output Layer (M10–M12) | Not Started | — | — |
| Phase 6 | Final Integration & Ablation Prep | Not Started | — | — |
| Phase 7 | Ablation Study & Evaluation | Not Started | — | — |
| Write-up | Dissertation | Not Started | — | — |

---

## Phase 0: Project Foundation — Detailed Status

### 0.1 Repository Structure
- [x] Directory structure created (2026-03-25)
- [x] All `__init__.py` files with module docstrings (2026-03-25)
- [x] Package is importable as `planproof.*` (2026-03-25)
- [x] GitHub repo: github.com/sgshaji/PlanProof_v3 (2026-03-25)

### 0.2 Tooling & Standards
- [x] `pyproject.toml` with hatchling build, all dependencies declared (2026-03-25)
- [x] `ruff` configured — lint passes clean (2026-03-25)
- [x] `mypy --strict` passes clean — 56 source files, 0 errors (2026-03-25)
- [x] `Makefile` with install, lint, typecheck, test targets (2026-03-25)
- [x] `.env.example` with all required env vars (2026-03-25)
- [x] `.gitignore` for Python, data, caches (2026-03-25)
- [x] GitHub Actions CI pipeline — `.github/workflows/ci.yml` (lint + typecheck + test on Linux) (2026-03-25)
- [x] pytest passing — 41 unit tests + 2 integration tests, all green (2026-03-25)

### 0.3 Infrastructure
- [x] Neo4j Aura (free cloud instance) configured as default (2026-03-25)
- [x] Groq (free cloud LLM) configured as default (2026-03-25)
- [x] Neo4j Aura instance created and credentials added to `.env` (2026-03-25)
- [x] Groq API key created and added to `.env` (2026-03-25)
- [x] Neo4j Aura connectivity verified — connect, query, write/read/cleanup all pass (2026-03-25)
- [ ] Label Studio instance — not yet started

### 0.4 Core Schemas (M4)
- [x] `schemas/entities.py` — EntityType, ExtractionMethod, ExtractedEntity, BoundingBox, etc. (2026-03-25)
- [x] `schemas/reconciliation.py` — ReconciliationStatus, ReconciledEvidence (2026-03-25)
- [x] `schemas/assessability.py` — BlockingReason, EvidenceRequirement, AssessabilityResult (2026-03-25)
- [x] `schemas/rules.py` — RuleConfig, RuleOutcome, RuleVerdict (2026-03-25)
- [x] `schemas/pipeline.py` — StepResult, ComplianceReport, EvidenceRequest (2026-03-25)
- [x] `schemas/config.py` — PipelineConfig (pydantic-settings), AblationConfig, ConfidenceThresholds (2026-03-25)
- [x] Schema round-trip tests — all schemas have JSON round-trip tests (2026-03-25)

### 0.5 LLM Response Cache
- [x] `infrastructure/llm_cache.py` — SQLiteLLMCache with composite key (2026-03-25)
- [x] `infrastructure/openai_client.py` — OpenAIClient with temperature=0 (2026-03-25)
- [x] `infrastructure/cached_llm.py` — CachedLLMClient decorator (2026-03-25)
- [ ] Cache integration test — not yet written

### 0.6 Pipeline Skeleton
- [x] `pipeline/pipeline.py` — Pipeline class with step registry, timing, error handling (2026-03-25)
- [x] 11 step stubs in `pipeline/steps/` — all accept Protocol-typed dependencies (2026-03-25)
- [x] `bootstrap.py` — composition root with conditional step registration (2026-03-25)
- [x] All stub classes match Protocol signatures — mypy strict passes (2026-03-25)
- [x] Pipeline skeleton tests — empty pipeline, step registration, execution order, error handling (2026-03-25)

### 0.7 Error Handling Strategy
- [x] StepResult with SUCCESS/PARTIAL/FAILED in schemas (2026-03-25)
- [x] Pipeline catches exceptions per step, wraps in StepResult (2026-03-25)
- [x] structlog configured for JSON logging (2026-03-25)

### Architecture & Documentation
- [x] Protocol interfaces — 7 files in `interfaces/` (2026-03-25)
- [x] Rule evaluator stubs — 6 evaluator types + RuleFactory (2026-03-25)
- [x] FlatEvidenceProvider stub for Ablation B (2026-03-25)
- [x] YAML rule configs — R001, R002, R003 (2026-03-25)
- [x] YAML ablation configs — full_system, naive_baseline, strong_baseline (2026-03-25)
- [x] Confidence thresholds YAML (2026-03-25)
- [x] ADR template + 3 ADRs (pipeline-step-registry, protocols-over-abcs, assessability-three-states) (2026-03-25)
- [x] `ARCHITECTURE.md` — component diagram, interface boundaries, data flow (2026-03-25)
- [x] `IMPLEMENTATION_PLAN.md` — directory structure updated to match refined architecture (2026-03-25)

---

## Deferred Dependencies (ARM64 Windows)

These libraries fail to build on ARM64 Windows (no pre-built wheels, require
Visual Studio 2022 Build Tools or native C headers). They are declared as
optional extras in `pyproject.toml` and will be installed when their respective
phases begin.

| Package | Optional Extra | Install Command | Needed In | Purpose |
|---------|---------------|-----------------|-----------|---------|
| `shapely` | `[geo]` | `pip install -e ".[geo]"` | Phase 3 (Representation) | Geospatial overlap checks for setback/boundary rules |
| `pymupdf` | `[pdf]` | `pip install -e ".[pdf]"` | Phase 2 (Ingestion) | PDF text extraction from planning documents |

**To install when ready:**
```bash
# Install one:
pip install -e ".[geo]"
pip install -e ".[pdf]"

# Install both:
pip install -e ".[geo,pdf]"

# Install everything (all extras + dev tools):
pip install -e ".[geo,pdf,dev]"
```

**Workarounds if build fails:**
1. Install Visual Studio 2022 Build Tools (includes C compiler for ARM64)
2. Use WSL (Windows Subsystem for Linux) where both install without issues
3. Use a CI/CD pipeline on Linux for full integration testing

---

## Blockers & Notes

| Date | Item | Status |
|------|------|--------|
| 2026-03-25 | `shapely` and `pymupdf` fail to build on ARM64 Windows | **Deferred** — moved to optional extras `[geo]` and `[pdf]`, not needed until Phase 2/3 |
| 2026-03-25 | No git repo initialized yet | **Resolved** — pushed to github.com/sgshaji/PlanProof_v3 |
| 2026-03-25 | Docker dev container approach | **Removed** — switched to local Python + cloud services (Neo4j Aura + Groq) |

---

## Phase 1: Synthetic Data Generator — Detailed Status

### 1.2 Synthetic Dataset Generation — Complete
- [x] Design spec written and reviewed (2026-03-25)
- [x] Implementation plan (20 tasks) written and reviewed (2026-03-25)
- [x] Scenario models — Value, Verdict, DocumentSpec, Scenario (frozen dataclasses) (2026-03-25)
- [x] Config loader — Pydantic-validated YAML, 9 configs (rules, profiles, degradation) (2026-03-25)
- [x] Scenario generator — generate_values, compute_verdicts, build_scenario (pure FP) (2026-03-25)
- [x] 5 edge-case strategies (missing_evidence, conflicting_values, low_confidence_scan, partial_documents, ambiguous_units) (2026-03-25)
- [x] Rendering models + coordinate utils (PDF-point ↔ pixel conversion) (2026-03-25)
- [x] Document generator registry (Protocol-based plugin architecture) (2026-03-25)
- [x] FormGenerator — 7-page PDF planning application with bbox tracking (2026-03-25)
- [x] SitePlanGenerator — PDF with 5 shape families (rectangle, L-shaped, trapezoidal, L-building, angled) (2026-03-25)
- [x] FloorPlanGenerator — PDF with 5 layout families (simple, L-shaped, open plan, two-storey, bay window) (2026-03-25)
- [x] ElevationGenerator — PNG raster with varied width, windows, doors, chimney, roof type (2026-03-25)
- [x] Polygon diversity — seeded variation in property shapes, building footprints, room layouts (2026-03-25)
- [x] 8 degradation transforms with TransformResult affine tracking (2026-03-25)
- [x] compose() utility + YAML preset loader (2026-03-25)
- [x] BBox affine adjustment + PDF rasterisation (2026-03-25)
- [x] Output writers — sidecar (ground_truth.json), reference (parcel.geojson, zone.json), file (BCC naming) (2026-03-25)
- [x] CLI runner with --seed/--category/--count flags (2026-03-25)
- [x] Subtype-based dispatch — FORM, SITE_PLAN, FLOOR_PLAN, ELEVATION each use correct generator (2026-03-25)
- [x] Integration tests — 8 tests covering full pipeline, determinism, output structure (2026-03-25)
- [x] Coverage tests + verify_data module (2026-03-25)
- [x] Full evaluation dataset generated — 20 compliant + 20 noncompliant + 10 edgecase (50 sets, 350+ files) (2026-03-25)

### 1.1 BCC Real Data — Complete
- [x] 10 real BCC application sets placed in `data/raw/` (2026-03-25)
- [x] PII anonymisation script — classifies 39 files, flags 11 forms for PII, copies 28 safe drawings (2026-03-26)
- [x] pii_manifest.json generated with per-file PII classification (2026-03-26)
- [x] Provenance documentation — `data/raw/PROVENANCE.md` with source, composition, PII notice (2026-03-26)

### 1.3 Test Set Sealing — Complete
- [x] Seeded train/val/test split — `split.py` with 60/20/20 deterministic assignment (2026-03-26)
- [x] MD5 integrity manifest — `integrity.py` hashes every file in synthetic dataset (2026-03-26)
- [x] Verification script — `scripts/verify_dataset.py` validates structure, split, and hashes (2026-03-26)
- [x] Makefile targets: `make seal-data`, `make verify-data` (2026-03-26)

### Test Summary
- 149 unit tests + 8 integration tests, all passing (1 skipped — pymupdf page count)
- ruff clean, mypy --strict clean across all modules
- Full pipeline smoke-tested: seed 42 -> 50 sets with ground truth + reference files

### Architecture Highlights
- **Hybrid FP/OOP**: pure functions for scenario generation + degradation, Protocol-based plugins for rendering
- **Immutable data**: frozen dataclasses with tuple collections throughout
- **Seed deterministic**: same seed always produces identical output
- **Extraction-level ground truth**: every placed value tracked with pixel-accurate bounding boxes
- **Plugin extensible**: new rules = YAML config, new doc types = one generator class, new degradation = one pure function

---

## Phase 2a: Ingestion Layer (M1 + M2) — Detailed Status

### 2.1 Document Classifier (M1) — Complete
- [x] RuleBasedClassifier with three-signal cascade (filename, text density, image heuristics) (2026-03-27)
- [x] Configurable regex patterns in `configs/classifier_patterns.yaml` (2026-03-27)
- [x] `has_text_layer` routing signal added to `ClassifiedDocument` (2026-03-27)
- [x] Unit tests — 17 tests covering all classification signals (2026-03-27)
- [x] Integration tests against synthetic data (2026-03-27)

### 2.2 Text Extraction Pipeline (M2) — Complete
- [x] PdfPlumberExtractor — text-layer PDF extraction via pdfplumber (2026-03-27)
- [x] LLMEntityExtractor — LLM structured extraction with prompt templates (2026-03-27)
- [x] VisionExtractor — GPT-4o image-based extraction (2026-03-27)
- [x] Rasteriser utility for image handling (2026-03-27)
- [x] PromptLoader with YAML template system (2026-03-27)
- [x] Four prompt templates — form, report, certificate, drawing (2026-03-27)
- [x] Two-path routing in TextExtractionStep (text vs vision) (2026-03-27)
- [x] Bootstrap wired with concrete implementations (2026-03-27)
- [x] Unit tests — 49 tests for all components (2026-03-27)
- [x] Integration tests with mocked LLM (2026-03-27)
- [x] Determinism test (2026-03-27)

### Architecture Highlights
- **Two-path router**: ClassifiedDocument.has_text_layer routes to pdfplumber+Groq (text) or GPT-4o (vision)
- **Plugin extensibility**: new doc types = YAML pattern + prompt template, no code changes
- **Provider swappable**: pdfplumber → pymupdf, Groq → OpenAI — all config-level behind Protocol interfaces
- **M3-ready**: vision path infrastructure reusable for VLM spatial extraction

---

## Phase 2b: Ingestion Layer (M3 VLM) — Detailed Status

### 2.3 VLM Spatial Extraction (M3) — Complete
- [x] VLMSpatialExtractor with zero-shot GPT-4o path (2026-03-27)
- [x] VLMSpatialExtractor with structured two-stage path (2026-03-27)
- [x] Drawing subtype inference from filename patterns (2026-03-27)
- [x] Bounding box extraction and spatial grounding (2026-03-27)
- [x] Subtype-aware prompt templates — spatial_zeroshot, spatial_structured_stage1, spatial_structured_stage2 (2026-03-27)
- [x] VLMExtractionStep pipeline step with DRAWING filtering (2026-03-27)
- [x] Bootstrap wired with concrete VLMSpatialExtractor (2026-03-27)
- [x] Unit tests — 22 tests for all extraction paths and step logic (2026-03-27)
- [x] Integration tests with mocked VLM (2026-03-27)

### Architecture Highlights
- **Two extraction methods (ablation dimension)**: VLM_ZEROSHOT (single call) vs VLM_STRUCTURED (coarse-then-refine)
- **Subtype-aware prompting**: SITE_PLAN, FLOOR_PLAN, ELEVATION each get targeted attribute lists
- **Spatial grounding**: all entities include BoundingBox in source_region (logged for audit, not primary eval metric)
- **VLM_FINETUNED**: deferred for potential future phase

---

---

## Phase 3: Representation Layer (M5) — Detailed Status

### 3.1 Entity Normalisation — Complete
- [x] `Normaliser` with `UnitConversionRegistry` — imperial/metric + address casing (2026-03-28)
- [x] Canonical unit table (`feet`→`metres`, `inches`→`mm`, `sq_ft`→`square_metres`) (2026-03-28)
- [x] Address abbreviation expansion (St, Rd, Ave, Dr, Ln, etc.) (2026-03-28)
- [x] `NormalisationStep` wired with concrete `Normaliser()` in bootstrap (2026-03-28)

### 3.2 Neo4j SNKG — Complete
- [x] `Neo4jSNKG` implementing all four graph Protocols (EntityPopulator, ReferenceDataLoader, EvidenceProvider, RuleProvider) (2026-03-28)
- [x] `_create_snkg()` factory in bootstrap — lazy neo4j import, warns and returns None if `neo4j_uri` unset (2026-03-28)
- [x] `GraphPopulationStep` wired with `Neo4jSNKG` when `config.ablation.use_snkg=True` and URI configured (2026-03-28)
- [x] `_StubPopulator` removed — replaced by concrete `Neo4jSNKG` (2026-03-28)

### 3.3 Flat Evidence Provider — Complete
- [x] `FlatEvidenceProvider` — in-memory flat list EvidenceProvider for Ablation B (`use_snkg=False`) (2026-03-28)
- [x] Pairwise conflict detection without graph traversal (2026-03-28)
- [x] Imported in bootstrap composition root (wired into ReconciliationStep in Phase 4) (2026-03-28)

### 3.4 Reference Data — Complete
- [x] `load_reference_set` utility for parcel GeoJSON + zone JSON (2026-03-28)
- [x] `Neo4jSNKG.load_reference_data()` merges Parcel/Zone/Rule nodes with relationships (2026-03-28)

---

---

## Phase 4: Reasoning Layer (M6–M9) — Detailed Status

### 4.1 Pairwise Reconciler (M6) — Complete
- [x] `PairwiseReconciler` — numeric tolerance + exact string pairwise comparison (2026-03-28)
- [x] AGREED / CONFLICTING / SINGLE_SOURCE / MISSING status outcomes (2026-03-28)
- [x] Per-attribute configurable tolerances, default 0.5 (2026-03-28)
- [x] `ReconciliationStep` wired with concrete `PairwiseReconciler()` in bootstrap (2026-03-28)
- [x] `_StubReconciler` removed (2026-03-28)

### 4.2 Confidence Gating (M7) — Complete
- [x] `ThresholdConfidenceGate` — per-method, per-entity-type thresholds with fail-open default (2026-03-28)
- [x] `ThresholdConfidenceGate.from_yaml()` factory loads from `configs/confidence_thresholds.yaml` (2026-03-28)
- [x] `ConfidenceGatingStep` wired with concrete gate in bootstrap (2026-03-28)
- [x] `_StubGate` removed (2026-03-28)

### 4.3 Assessability Evaluator (M8) — Complete
- [x] `DefaultAssessabilityEvaluator` — tri-state logic (ASSESSABLE / NOT_ASSESSABLE) (2026-03-28)
- [x] Source matching, confidence gating, reconciliation conflict detection pipeline (2026-03-28)
- [x] Priority ordering: MISSING > CONFLICTING > LOW_CONFIDENCE > NONE (2026-03-28)
- [x] `AssessabilityStep` wired with concrete evaluator + SNKG evidence_provider in bootstrap (2026-03-28)
- [x] `_StubAssessability` removed (2026-03-28)

### 4.4 Rule Evaluation (M9) — Complete
- [x] 6 evaluator types registered: numeric_threshold, ratio_threshold, enum_check, fuzzy_string_match, numeric_tolerance, attribute_diff (2026-03-28)
- [x] `RuleEvaluationStep` wired with `RuleFactory` + rules_dir in bootstrap (2026-03-28)
- [x] `rapidfuzz` optional — `FuzzyMatchEvaluator` falls back to `difflib.SequenceMatcher` gracefully (2026-03-28)

### 4.5 Bootstrap Wiring (Task 6) — Complete
- [x] `_create_reconciler()` factory replacing `_stub_reconciler()` (2026-03-28)
- [x] `_create_confidence_gate(config)` loading from `configs/confidence_thresholds.yaml` (2026-03-28)
- [x] `_create_assessability_evaluator(...)` wiring SNKG or stub as evidence_provider (2026-03-28)
- [x] Rules loaded once (`RuleFactory.load_rules()`) and shared between assessability + rule evaluation (2026-03-28)
- [x] Evidence provider selection: Neo4jSNKG if `use_snkg=True` and URI configured, else `_StubEvidenceProvider` (Phase 5) (2026-03-28)
- [x] 533 tests passing, 7 skipped — ruff clean, mypy --strict clean (2026-03-28)
- [x] Integration tests: compliant→PASS, non-compliant→FAIL, missing→NOT_ASSESSABLE, low-confidence→NOT_ASSESSABLE, conflicting→NOT_ASSESSABLE (2026-03-28)

---

## Next Steps

1. Begin Phase 5: Output Layer (M10 scoring, M11 evidence requests, M12 report generation)
2. Wire `FlatEvidenceProvider` into reasoning steps when `use_snkg=False` (replacing `_StubEvidenceProvider`)
3. Wire `_StubEvidenceRequestGenerator` with concrete implementation
4. Set up Label Studio for VLM ground truth annotation
5. Consider VLM fine-tuning if zero-shot accuracy insufficient
