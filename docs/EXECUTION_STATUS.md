# PlanProof — Execution Status

> **Last updated**: 2026-03-25
> **Current phase**: Phase 1 (Data Pipeline & Synthetic Generation)
> **Overall status**: Phase 0 complete. **Phase 1 complete.** Synthetic data generator, PII anonymisation, test set sealing all done. Ready for Phase 2.

---

## Phase Summary

| Phase | Name | Status | Date Started | Date Completed |
|-------|------|--------|-------------|----------------|
| **Phase 0** | Project Foundation | **Complete** | 2026-03-25 | 2026-03-25 |
| **Phase 1** | Data Pipeline & Synthetic Generation | **Complete** | 2026-03-25 | 2026-03-26 |
| Phase 2 | Ingestion Layer (M1, M2, M3) | Not Started | — | — |
| Phase 3 | Representation Layer (M5) | Not Started | — | — |
| Phase 4 | Reasoning Layer (M6–M9) | Not Started | — | — |
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

## Next Steps

1. Begin Phase 2: Ingestion Layer (Document Classifier, Text Extraction, VLM Pipeline)
2. Set up Label Studio for VLM ground truth annotation (Phase 2.3)
