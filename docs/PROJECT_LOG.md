# PlanProof — Project Development Log

> **Purpose:** Chronological record of all development, decisions, experiments, and findings for dissertation traceability.
> **How to use:** Each entry is dated and categorised. Reference this log in the dissertation methodology/implementation chapters to demonstrate systematic development process.

---

## 2026-03-25 — Phase 0: Project Foundation

### Development
- Created complete project scaffold with SOLID architecture (106 source files planned)
- Established Protocol-based interfaces (7 files in `interfaces/`)
- Defined unified entity schemas (M4) — `ExtractedEntity`, `BoundingBox`, `ClassifiedDocument`, `RuleVerdict`, `AssessabilityResult`
- Set up pipeline skeleton with step registry pattern
- Created composition root (`bootstrap.py`) — single dependency injection point
- Configured tooling: ruff, mypy --strict, pytest, structlog JSON logging
- GitHub Actions CI pipeline (lint + typecheck + test on Linux)
- 3 Architecture Decision Records (ADRs): pipeline-step-registry, protocols-over-abcs, assessability-three-states

### Infrastructure
- Neo4j Aura (free cloud) instance created and verified
- Groq (free tier LLM) configured as default provider
- Switched from Docker to local Python + cloud services (ARM64 Windows compatibility)
- shapely and pymupdf deferred to optional deps (no ARM64 wheels)

### Decisions
- **Protocols over ABCs:** Structural subtyping, no inheritance hierarchies
- **Composition Root pattern:** One file wires all dependencies, business logic never imports concrete types
- **Cloud-first infrastructure:** Neo4j Aura + Groq free tier — zero local service dependencies

### Metrics
- 41 unit tests + 2 integration tests passing
- mypy --strict clean across all files
- ruff clean

---

## 2026-03-25 to 2026-03-26 — Phase 1: Synthetic Data Pipeline

### Development
- Designed and implemented 3-layer synthetic data generator:
  - Layer 1: Scenario generation (pure functions from YAML configs)
  - Layer 2: Document rendering (Protocol-based plugins — FormGenerator, SitePlanGenerator, FloorPlanGenerator, ElevationGenerator)
  - Layer 3: Degradation + output (affine bbox adjustment, PDF rasterisation)
- 9 YAML configs: 3 rules, 3 profiles, 3 degradation presets
- 5 edge-case strategies: missing_evidence, conflicting_values, low_confidence_scan, partial_documents, ambiguous_units
- Generated 50 synthetic application sets (20 compliant + 20 non-compliant + 10 edge-case)

### Data Management
- BCC real data: 10 application sets placed in `data/raw/`
- PII anonymisation script: classified 39 files, flagged 11 forms for PII, copied 28 safe drawings
- Seeded train/val/test split (60/20/20, deterministic)
- MD5 integrity manifest for dataset sealing

### Key Decision
- **Hybrid FP/OOP architecture for datagen:** Pure functions for data transforms, Protocol-based OOP for rendering plugins
- **Extraction-level ground truth:** Every placed value tracked with pixel-accurate bounding boxes

### Metrics
- 149 unit tests + 8 integration tests passing
- 50 synthetic sets with 350+ files generated

---

## 2026-03-27 — Phase 2a: Ingestion Layer (M1 + M2)

### Development
- **M1 RuleBasedClassifier:** Three-signal cascade (filename patterns → text density → image heuristics)
- **M2 Text Extraction:** PdfPlumberExtractor (text-layer PDFs) + LLMEntityExtractor (Groq LLM structured extraction) + VisionExtractor (GPT-4o)
- Two-path routing: `has_text_layer` routes to text path or vision path
- 4 prompt templates: form, report, certificate, drawing extraction
- Wired concrete implementations into bootstrap

### Decisions
- **Two-path router design:** ClassifiedDocument.has_text_layer determines extraction path
- **Provider-swappable:** pdfplumber → pymupdf, Groq → OpenAI — all config-level changes

### Metrics
- 17 classifier tests + 49 extraction tests passing
- Integration tests against synthetic data

---

## 2026-03-27 — Phase 2b: VLM Spatial Extraction (M3)

### Development
- **VLMSpatialExtractor** with two ablation paths:
  - VLM_ZEROSHOT: single GPT-4o call requesting entities + bounding box coords
  - VLM_STRUCTURED: two-stage coarse-then-refine with image cropping
- Drawing subtype inference from filename patterns (SITE_PLAN, FLOOR_PLAN, ELEVATION)
- 3 spatial prompt templates: spatial_zeroshot, spatial_structured_stage1, spatial_structured_stage2
- VLMExtractionStep filters for drawings without text layers

### Key Decision
- **Two extraction methods as ablation dimension:** VLM_ZEROSHOT vs VLM_STRUCTURED — configurable via `vlm_extraction_method`
- **Bbox accuracy logged but not primary metric:** Value-match accuracy is primary; spatial grounding for audit trails

### Metrics
- 22 unit tests + 2 integration tests for M3
- All 24 M3 tests passing

---

## 2026-03-27 — Housekeeping: Fix Pre-existing Issues

### Fixes Applied
- Fixed test_anonymise.py collection error (Python 3.13 dataclass module loading)
- Fixed all ruff E501 line length violations
- Fixed all 29 mypy strict errors in datagen module
- Fixed 2 failing datagen integration tests (data path mismatch)

### Metrics
- 308 tests passing, 0 failures (was 278 passed, 2 failed)
- ruff: 0 errors (was 21)
- mypy --strict: 0 errors (was 29)

---

## 2026-03-28 — Phase 3: Representation Layer (M5)

### Development
- **Normalisation:** Extensible unit conversion registry (feet→metres, inches→mm, sqft→sqm + 8 more) + address canonicalisation + numeric precision rounding
- **Neo4jSNKG:** Implements 4 Protocols (EntityPopulator, ReferenceDataLoader, EvidenceProvider, RuleProvider) with Cypher queries
- **Reference data loaders:** GeoJSON parcel + zone JSON with WKT geometry conversion
- **FlatEvidenceProvider:** Ablation B alternative (flat list lookup, no graph traversal)
- All wired into bootstrap, stubs removed

### Key Decisions
- **Neo4j driver directly (no OGM):** Cypher queries in thin repository class — no neomodel dependency
- **Shapely deferred:** Geometry stored as WKT but no runtime spatial predicates (zone linkage from pre-computed zone.json)
- **FlatEvidenceProvider for Ablation B:** Deliberately degraded evidence lookup to isolate graph contribution

### Known Gap Identified
- SNKG stores geometry but doesn't compute spatial predicates (contains/intersects) — noted for future work

### Metrics
- 95 new representation tests, 403 total passing

---

## 2026-03-28 — Phase 4: Reasoning Layer (M6-M9)

### Development
- **M6 PairwiseReconciler:** Cross-source evidence reconciliation with configurable per-attribute tolerance. AGREED/CONFLICTING/SINGLE_SOURCE/MISSING states.
- **M7 ThresholdConfidenceGate:** Per extraction_method × entity_type thresholds loaded from YAML. Fail-open default for unconfigured combinations.
- **M8 DefaultAssessabilityEvaluator:** Core research contribution — tri-state logic (ASSESSABLE/NOT_ASSESSABLE) with blocking reasons (MISSING_EVIDENCE, CONFLICTING_EVIDENCE, LOW_CONFIDENCE). 100% test coverage.
- **M9 Rule Evaluators:** 6 types implemented — NumericThreshold (R001/R002), RatioThreshold (R003), FuzzyMatch (C002), EnumCheck (C001), NumericTolerance (C003), AttributeDiff (C004)
- All 4 pipeline steps implemented and wired through bootstrap

### Key Decisions
- **Pairwise comparison only for reconciliation** (proposal scoping decision — majority voting deferred)
- **Confidence thresholds from YAML config:** Empirically calibratable without code changes
- **Rule evaluation deterministic:** No LLM in the evaluation path. Same inputs → same outputs.
- **Only ASSESSABLE rules evaluated:** NOT_ASSESSABLE rules skip evaluation entirely

### Metrics
- 102 reasoning unit tests + 11 integration tests
- DefaultAssessabilityEvaluator at 100% coverage
- 533 total tests passing

---

## 2026-03-28 — Phase 5: Output Layer (M10-M12)

### Development
- **M10 ComplianceScorer:** Aggregates verdicts + assessability results into ComplianceReport with summary counts
- **M11 MinEvidenceRequestGenerator:** Converts NOT_ASSESSABLE results to actionable EvidenceRequest items with YAML-driven guidance text
- **M12 MarkdownReportRenderer:** CLI compliance report (dashboard dropped per scope reduction)
- All wired into bootstrap, last stubs removed

### Key Decision
- **Dashboard dropped:** CLI Markdown sufficient for dissertation (F11 scope reduction guideline)

### Metrics
- 65 output unit tests + 13 integration tests
- 635 total tests passing

---

## 2026-03-28 — Phase 6: Integration & Ablation Prep

### Development
- FlatEvidenceProvider wired for Ablation B (last stub `_StubEvidenceProvider` removed)
- NaiveBaselineRunner: single LLM call, forced PASS/FAIL
- StrongBaselineRunner: per-rule CoT LLM calls with evidence citation
- CLI entry point: `python -m planproof.pipeline --input <dir> --ablation <yaml>`
- Ablation config validation tests for all 7 configurations

### Metrics
- 670 total tests passing
- All 7 ablation configs verified

---

## 2026-03-28 — Phase 7: Ablation Study & Evaluation

### Evaluation Infrastructure Built
- Experiment result data models + JSON I/O (`evaluation/results.py`)
- Metric computation: recall, precision, F2, bootstrap CI, McNemar, Cohen's h (`evaluation/metrics.py`)
- Ablation runner script (`scripts/run_ablation.py`) — runs all 7 configs × test sets
- Analysis notebook (`notebooks/ablation_analysis.ipynb`) with 5 dissertation-quality plots

### Experiment Run 1: Ground Truth Bypass (2026-03-28)

**Method:** Fed ground-truth entities directly into reasoning pipeline (bypasses extraction). Isolates reasoning layer contribution.

**Results on compliant data (5 sets):**

| Config | Pass | Fail | N/A | Finding |
|--------|------|------|-----|---------|
| Naive Baseline | 4 | 3 | 0 | LLM gets 3 rules wrong on compliant data |
| Strong Baseline (CoT) | 1-2 | 5-6 | 0 | CoT makes things WORSE — overthinks |
| Ablation A (no rules) | 0 | 0 | 7 | Expected — evidence only |
| Ablation B (no SNKG) | 2 | 0 | 5 | R001+R002 PASS, C-rules correctly N/A |
| Ablation C (no gating) | 2 | 0 | 5 | Same as full system (GT confidence=1.0) |
| Ablation D (no assessability) | 2 | 5 | 0 | Forces PASS/FAIL — 5 false FAILs |
| Full System | 2 | 0 | 5 | 0 false FAILs, 5 correctly N/A |

**Key Findings:**
1. **Assessability engine eliminates false verdicts:** Full system 0 false FAILs vs Ablation D 5 false FAILs
2. **Strong baseline paradox:** CoT prompting performs WORSE than naive — confuses missing evidence with violations
3. **Full system never guesses:** Correctly says "I don't know" instead of producing wrong answers

### Experiment Run 2: Synthetic Data Generated (2026-03-28)

- Generated 5 non-compliant sets (values exceeding rule thresholds)
- Generated 5 edge-case sets (partial/missing evidence)
- Re-ran ablation on all 15 sets
- Baselines hit Groq daily rate limit (100k tokens/day) — 3 strong baseline runs incomplete

### Experiment Run 3: Real E2E Pipeline (2026-03-28)

**Method:** Full pipeline on actual synthetic PDFs with real LLM/VLM API calls.

**Synthetic data (SET_COMPLIANT_100000):**
- GPT-4o successfully extracted `building_height=3.5m` from elevation drawings
- GPT-4o extracted `rear_garden_depth=10.0m` from site plan scan
- R001 (max height ≤ 8m): **PASS** with extracted value 3.5m ✓
- R002 (min garden ≥ 10m): **PASS** with extracted value 10.0m ✓
- R003, C001-C004: Insufficient evidence (expected — attributes not in drawings)

**Real BCC data (2025-00841):**
- 5 architectural PDFs classified as DRAWING
- Text extracted via pdfplumber (sparse drawing annotations)
- 2 entities extracted from elevation PDFs
- All rules: insufficient evidence (no application form in this set)
- **Finding:** Pipeline correctly handles incomplete real-world data — produces honest "insufficient evidence" rather than guessing

### Critical Bug Fixed: Entity-to-Rule Linkage (2026-03-28)

**Problem discovered:** `ExtractedEntity` had no `attribute` field. LLM returned attribute names (e.g., "building_height") but they were silently discarded during entity creation. All entities were typed as generic MEASUREMENT with no way to match to specific rule requirements.

**Fix applied (3 changes):**
1. Added `attribute: str | None = None` to `ExtractedEntity` schema
2. All 4 entity parsers now preserve attribute from LLM/VLM response
3. Assessability evaluator filters by attribute name + source type (not just source type)
4. Reconciliation groups by attribute (not entity_type)

**Impact:** Enabled meaningful E2E verdicts. Before fix: all rules "insufficient evidence." After fix: R001 PASS (3.5m ≤ 8m), R002 PASS (10.0m ≥ 10m).

### Infrastructure: Gemini Vision Adapter (2026-03-28)

- Created `GeminiVisionAdapter` for free-tier VLM (Google AI Studio)
- Adapts Gemini API to OpenAI-compatible interface (drop-in replacement)
- Gemini free tier quota was 0 on both keys tested — reverted to OpenAI GPT-4o ($4.88 budget, ~$2-3 estimated cost)

### Infrastructure: Groq Model Upgrade (2026-03-28)

- `llama-3.1-70b-versatile` decommissioned by Groq
- Upgraded to `llama-3.3-70b-versatile` in config + groq_client defaults
- Baselines run successfully with new model

---

## 2026-03-29 — SABLE Algorithm Implementation

### Architectural Review
- Conducted full architectural review of Phase 4 assessability engine (rating: 8.5/10)
- Identified that the DefaultAssessabilityEvaluator was an ad-hoc if-else checklist — not a principled probabilistic model
- Decision: replace with SABLE (Semantic Assessability via Belief-theoretic evidence Logic)

### SABLE Algorithm Design & Implementation
- Designed SABLE grounded in Dempster-Shafer (D-S) evidence theory
- **4-factor mass functions:** each evidence source contributes m(ASSESSABLE), m(NOT_ASSESSABLE), m(Θ) via:
  1. Source relevance — does the source type match the rule's required sources?
  2. Semantic relevance — cosine similarity between extracted attribute embedding and rule attribute embedding
  3. Confidence calibration — extracted entity confidence mapped to belief mass
  4. Concordance adjustment — reconciliation outcome (AGREED/CONFLICTING/SINGLE_SOURCE) modulates ignorance mass
- **Three-valued mass functions:** explicit ignorance mass m(Θ) propagates epistemic uncertainty rather than forcing binary commitment
- **PARTIALLY_ASSESSABLE third state:** added to `AssessabilityResult` — fires when Bel(ASSESSABLE) > threshold but Pl(ASSESSABLE) < upper threshold; signals "evidence present but contested"
- **Dempster's rule of combination:** independent source masses combined via orthogonal sum

### SemanticSimilarity Module
- Implemented `SemanticSimilarity` using sentence-transformers (`all-MiniLM-L6-v2`)
- Fallback to character n-gram Jaccard similarity when sentence-transformers not available
- Resolves Gap #3 (attribute name inconsistency): "height" ↔ "building_height" now matched via cosine similarity
- Embedding cache to avoid re-encoding repeated attribute strings

### Formal Specification
- Written `docs/SABLE_ALGORITHM.md` — full formal specification with notation, mass function definitions, combination rules, and worked example
- Written `docs/RESEARCH_IDEAS.md` — documents embedding-based hybrid approach chosen over LLM micro-prompts and graph proximity alternatives

### Metrics
- 46 assessability tests: 12 SABLE-specific + 6 semantic similarity + 28 existing — all passing
- 754 total tests passing (up from 728)

---

## 2026-03-28 — Documentation & Review

### Documents Updated/Created
- `docs/EXECUTION_STATUS.md` — comprehensive status for all 7 phases
- `docs/GAPS_AND_IDEAS.md` — 11 known gaps with severity, 4 idea categories
- Analysis notebook executed with 5 dissertation-quality figures (300 DPI)

### Architectural Review Conducted (2026-03-29)

**Rating: 8.5/10**

**SOLID compliance:** Excellent across all 5 principles. ISP exemplary (4 graph Protocols). DIP exemplary (composition root pattern).

**Design patterns identified:** Composition Root, Registry, Strategy, Adapter, Decorator, Factory, Pipeline, Protocol-based Structural Typing — all applied correctly. Zero anti-patterns detected.

**Security:** API keys via env vars (pydantic-settings), parameterised Cypher queries, no hardcoded secrets in code. Prompt injection mitigated but could add XML wrapping.

**Recommended improvements (P0-P4):**
- P0: Add `@runtime_checkable` to Protocols
- P1: XML-wrap document text in prompts
- P2: Default outputs for failed pipeline steps
- P3: Error-path tests
- P4: Cache versioning

### Final Project Statistics (2026-03-28)

| Metric | Count |
|--------|-------|
| Commits | 102 |
| Source files | 106 |
| Test files | 76 |
| Tests passing | 754 |
| Tests skipped | 14 |
| Lines of code (src) | 14,233 |
| Lines of code (tests) | 13,504 |
| Pipeline steps | 11 |
| Modules implemented | M1-M12 (all) |
| Rules configured | 7 (R001-R003 + C001-C004) |
| Ablation configurations | 7 |
| Synthetic datasets | 15 (5 compliant + 5 non-compliant + 5 edge-case) |
| Real BCC datasets | 10 (anonymised, drawings only) |
| LLM providers | 4 (Groq, OpenAI, Ollama, Gemini) |
| Design patterns | 10 (documented) |
| SOLID violations | 0 |
| Anti-patterns | 0 |

---

## Outstanding Items (as of 2026-03-29)

### Critical (affect dissertation quality)
- [ ] Fix assessability step not firing in E2E pipeline
- [ ] Fix rule_id "unknown" in verdict reports
- [x] Attribute name canonicalisation (LLM output → rule requirement names) — **DONE** (SABLE semantic relevance via embedding cosine similarity resolves this)

### Important (strengthen evaluation)
- [ ] Re-run ablation experiments with real extraction (not GT bypass)
- [ ] Complete strong baseline runs (Groq rate limit)
- [ ] Enrich synthetic data (add footprint_area, site_area, certificate_type)
- [ ] Qualitative error analysis (per-misclassification narrative)

### Nice-to-have
- [ ] Confidence threshold calibration
- [ ] Run E2E on more BCC sets
- [ ] Apply P0-P4 architectural improvements

### Known Deferred
- [ ] Shapely spatial predicates (stored but not computed)
- [ ] VLM fine-tuning (VLM_FINETUNED)
- [ ] Label Studio annotation tooling
- [ ] Web dashboard (M12 — CLI sufficient for dissertation)
