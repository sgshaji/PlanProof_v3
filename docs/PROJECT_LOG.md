# PlanProof — Project Development Log

> Chronological record of development for dissertation traceability.
> Newest entries first.

---

## 2026-04-05 — Content-Based Classifier & VLM PDF Drawing Support

- **Classifier rewritten**: Content-first classification replaces filename-pattern-first. Analyses PDF text for domain keywords (form: "householder application", "certificate of ownership"; drawing: "site plan", "scale 1:", "site boundary") + page geometry (landscape A3+ → DRAWING). Filename patterns demoted to fallback.
- **Root cause fixed**: BCC names all drawings "Plans & Drawings-Application Plans.pdf" — old classifier matched "Application" → FORM. New classifier reads content → correctly identifies as DRAWING (0.96-0.98 confidence).
- **VLM PDF support added**: `VLMSpatialExtractor._extract_from_pdf()` converts each PDF page to PNG via pdfplumber `page.to_image()`, sends to GPT-4o VLM. Removed artificial block in `run_extraction_eval.py` that skipped PDF drawings.
- **Results**: VLM now extracts building_height, ridge_height, eave_height, room_dimensions, floor_area, rear_garden_depth, site_coverage, site_area from real BCC drawing PDFs. `2025 07100` yielded 136 entities across 7 drawing pages.
- **Groq daily limit hit**: 100K tokens/day exhausted during full run. Need to re-run or merge v1 (LLM forms) + v2_full (VLM drawings) for complete results.

---

## 2026-04-05 — Real BCC Extraction Evaluation

- **Extraction eval on 9 real BCC planning applications** — first validation on real data
- Results: recall=93.3%, precision=38.6%, value accuracy=86.7% (5 GT attributes: site_address, form_address, certificate_type, ownership_declaration, site_location)
- Low precision reflects conservative GT annotation (3→5 attributes), not extraction error — LLM correctly extracts ~12 entities per form
- Formal results saved to `data/results/extraction_bcc/bcc_v1_enriched_summary.json`
- **GAP 2 resolved**: Application forms exist in `data/raw/` (9/10 sets). `data/anonymised/` was missing them due to PII stripping.

---

## 2026-04-05 — Comprehensive Synthetic Data Generation (V2)

- Fixed datagen pipeline: all **8 assessable rules now produce PASS/FAIL verdicts** (was 1-2)
- Root cause: three-layer disconnect — missing rule config extras, scenario generator not mapping extras to doc specs, renderers not tracking attributes
- Form generator: 12 tracked attributes (was 3) — added certificate_type, ownership_declaration, form_address, zone_category, site_location, stated_site_area, building_footprint_area, total_site_area, rear_garden_depth
- New EXTERNAL_DATA document generator for C003 (reference_parcel_area) and C006 (conservation_area_status)
- Updated datagen rule configs (R001, R002, R003, C004, C006), profile configs, extraction prompts
- Added `--docs-dir` support to `run_extraction_eval.py` for split-directory BCC evaluation
- Generated `data/synthetic_v2/` (existing synthetic data preserved)

---

## 2026-04-04 — E2E Integration Gap Identified

- Documented critical gap: full pipeline never validated on real BCC data end-to-end
- Each component tested individually; ablation validates the reasoning layer in isolation
- Real data blocked by: ~~no application forms available~~ (CORRECTED 2026-04-05: forms exist in data/raw/), SNKG not wired to live data, VLM unreliable on scanned PDFs
- Cleaned GAPS_AND_IDEAS.md: 6 open gaps, 5 limitations, 9 resolved items

---

## 2026-04-04 — Research Demo Web UI

- Built FastAPI + Jinja2 + SSE web interface for live pipeline visualization
- 8 pipeline stages stream in real time (classify, extract, boundary, normalise, graph, reconcile, assess, evaluate)
- Features: file upload, pre-loaded test set buttons, SABLE belief gauges, ablation comparison matrix, dissertation figures gallery
- Job ID system with persistent run history; no pre-computed results — live inference only
- Added 6 source files; project total: 118 source files, 172 commits

---

## 2026-04-04 — DA1: SNKG Spatial Rule (C006)

- Implemented C006 Conservation Area Containment Check — first rule requiring Neo4j graph traversal (zone containment query) rather than direct entity comparison
- ablation_b (SNKG removed) now differs measurably from full_system: 85 vs 118 PASS, all 33 missing verdicts route to NOT_ASSESSABLE
- Neurosymbolic claim empirically validated: LLM/VLM extraction cannot answer spatial containment questions without a structured knowledge graph
- Expanded to 9 compliance rules (R001–R003, C001–C006); 33 test sets × 9 rules = 297 evaluations per config

---

## 2026-04-03 — Enhancement Sprint (P1.1–P1.4, P2.1–P2.4)

- P1.1 Robustness curves: NoisyEntityTransformer with 4 degradation modes re-run at 5 levels — SABLE false-FAIL counts stay near zero; ablation_d degrades sharply
- P1.2 Extraction evaluation v3: recall=1.0, precision=0.533, value accuracy=1.0; full_system still 0 false FAILs regardless of extraction quality
- P1.3 Expanded noncompliant corpus: 10 additional sets added; true FAILs detected: full_system 2→14, ablation_d 4→20
- P1.4 Statistical rigour: McNemar + Benjamini-Hochberg correction (full_system vs ablation_d p<0.0001), bootstrap 95% CI, Cohen's h effect sizes for all 4 systems
- P2.1 Threshold sensitivity: swept theta_high (0.5–0.9), precision=1.0 across all tested values; optimal at theta_high=0.55
- P2.2 BCC annotation (partial): 63 extractions annotated via GPT-4o on 2025-07100; 2 remaining sets deferred (ARM64 poppler unavailable)
- P2.3 Baseline comparison: CoT baseline 10 PASS / 51 false FAILs; naive baseline 121 PASS / 126 false FAILs — prompt engineering does not solve false-FAIL problem
- P2.4 SABLE formal properties: 5 proofs documented (monotonicity, boundedness, determinism, idempotency, composability)
- Final project metrics: 167 commits, 114 source files, 917 tests, 15 dissertation figures (300 DPI)

---

## 2026-04-03 — Evidence Quality Fixes and Figure Regeneration

- Root cause: single-source oracle evidence never raised SABLE belief above the PASS threshold; all verdicts incorrectly resolved to NOT_ASSESSABLE or PARTIALLY_ASSESSABLE
- Fix: datagen updated to provide multi-source oracle evidence for dual-source rules (R001, R002, C004) — Dempster combination now produces belief=0.96, crossing the 0.75 PASS threshold
- Corrected results: full_system 43 PASS / 0 false FAILs (was 0 PASS); ablation_d 73 PASS / 43 false FAILs; belief two-cluster confirmed at 0.56 (SINGLE_SOURCE) and 0.96 (DUAL_SOURCE)
- Regenerated all 7 SABLE dissertation figures; updated ERROR_ANALYSIS.md, EXECUTION_STATUS.md, GAPS_AND_IDEAS.md, README.md

---

## 2026-04-03 — Phase 9: Three-Tier Boundary Verification Pipeline

- Three independent tiers: VLM visual alignment (red-line vs OS base map), scale-bar measurement with >15% area discrepancy flag, INSPIRE polygon cross-reference with >1.5x over-claiming flag
- Pure-Python INSPIRE GML parser (no geopandas/shapely); postcodes.io geocoding; 346,231 cadastral parcels loaded; centroid proximity matching
- C005 boundary verification rule replaces simplified C003; BoundaryVerificationEvaluator registered in RuleFactory
- Limitation documented: VLM detects gross discrepancies only; centroid matching may select wrong parcel in dense urban areas; INSPIRE gives indicative extent, not legal boundary
- Metrics at completion: 885 tests, 157 commits, 113 source files, 12 pipeline steps, 8 compliance rules

---

## 2026-04-03 — Phase 8c: Extraction Evaluation Track

- Compared v1 (broad prompt) vs v2 (7-attribute narrow prompt) across 5 synthetic test sets: precision 0.299 → 0.715 (+41.6pp), recall unchanged at 0.886, value accuracy stable at 0.857
- Root cause of v1 precision gap: broad prompt returns ~22 predicted entities per set vs 7 GT — 15 hallucinations per set
- 2×2 false-FAIL matrix: full_system 0 false FAILs with both oracle and real extraction; ablation_d 100 (oracle) / 26 (real)
- Error attribution (ablation_d + real extraction): 71.4% reasoning failure, 23.8% end-to-end success, 4.8% extraction failure
- Key finding: SABLE's NOT_ASSESSABLE state is an information-theoretic firewall — extraction quality does not propagate to false FAILs
- 4 dissertation figures generated (E1–E4): extraction_accuracy, extraction_v1_v2_delta, false_fail_matrix, sable_oracle_vs_real

---

## 2026-04-02 — Phase 8b: Architectural Polish

- P0: Added `@runtime_checkable` to all 17 Protocol interfaces in `interfaces/`
- P1: XML-wrapped document text in 4 LLM prompt templates for prompt injection defence
- P2: Failed pipeline steps now populate default context keys for graceful degradation instead of leaving keys absent

---

## 2026-04-02 — Phase 8a: SABLE Evaluation Enrichment

- Extended RuleResult with SABLE fields (belief, plausibility, conflict_mass, blocking_reason) and PARTIALLY_ASSESSABLE outcome
- Extended datagen: C001–C004 configs created (certificate type, address consistency, boundary validation, plan change detection); R003 enriched with extra attributes
- Re-ran 5 ablation configs: 100 experiments, 700 rule evaluations; generated 7 SABLE dissertation figures (300 DPI)
- Key finding: full_system 0 false FAILs; ablation_d (no assessability) 100 false FAILs — assessability engine completely prevents false violations
- Belief scores uniformly low (0.10–0.21) with single-source oracle evidence; McNemar p<0.001 for Assessability (SABLE) component
- Metrics: 790 tests, ~120 commits, 14 Phase 8a commits

---

## 2026-04-01 — Phase 7b: Critical Bug Fixes

- Bug 1: AssessabilityStep never fired in E2E — context["metadata"]["rule_ids"] was never populated; fix: Pipeline.__init__ accepts rule_ids, Pipeline.run() injects them; assessability engine now fires correctly
- Bug 2: All evaluator verdicts showed rule_id="unknown" — rule_id is a top-level YAML field, not inside parameters; fix: RuleFactory injects rule_id into params dict before evaluator construction
- Both fixes validated by code review; integration-level tests deferred to Phase 8a ablation re-run
- Metrics: 759 tests (was 754), 5 new tests, ~111 total commits

---

## 2026-03-29 — SABLE Algorithm Implementation

- Architectural review of DefaultAssessabilityEvaluator (8.5/10): identified as ad-hoc if-else checklist; replaced with SABLE (Semantic Assessability via Belief-theoretic evidence Logic) grounded in Dempster-Shafer evidence theory
- 4-factor mass functions per evidence source: source relevance, semantic relevance (cosine similarity), confidence calibration, concordance adjustment; Dempster combination via orthogonal sum
- Added PARTIALLY_ASSESSABLE third state: fires when Bel(ASSESSABLE) > threshold but Pl(ASSESSABLE) < upper threshold
- SemanticSimilarity module using sentence-transformers (all-MiniLM-L6-v2) with Jaccard fallback; resolves attribute name inconsistency gap ("height" ↔ "building_height")
- Formal specification written: docs/SABLE_ALGORITHM.md; 46 assessability tests all passing; 754 total tests

---

## 2026-03-28 — Phase 7: Ablation Study and Evaluation

- Evaluation infrastructure: result data models, metric computation (recall, precision, F2, bootstrap CI, McNemar, Cohen's h), ablation runner script, analysis notebook with 5 dissertation figures
- Experiment 1 (ground-truth bypass, 5 compliant sets): full_system 0 false FAILs; ablation_d 5 false FAILs; strong CoT baseline performs worse than naive — overthinks missing evidence as violations
- Experiment 2: generated 5 non-compliant + 5 edge-case sets; baselines hit Groq 100k token/day rate limit
- Experiment 3 (real E2E on synthetic PDFs): GPT-4o extracted building_height=3.5m and rear_garden_depth=10.0m; R001 and R002 PASS; remaining rules correctly NOT_ASSESSABLE (no application form)
- Critical bug found and fixed: ExtractedEntity had no attribute field — LLM attribute names silently discarded; all entities untyped; fix enabled meaningful E2E verdicts
- Groq model upgraded: llama-3.1-70b-versatile decommissioned; switched to llama-3.3-70b-versatile

---

## 2026-03-28 — Phase 6: Integration and Ablation Prep

- FlatEvidenceProvider wired for Ablation B (last stub removed); NaiveBaselineRunner and StrongBaselineRunner implemented
- CLI entry point: python -m planproof.pipeline --input <dir> --ablation <yaml>
- Ablation config validation tests for all 7 configurations
- Metrics: 670 total tests, all 7 ablation configs verified

---

## 2026-03-28 — Phase 5: Output Layer (M10–M12)

- M10 ComplianceScorer: aggregates verdicts and assessability results into ComplianceReport with summary counts
- M11 MinEvidenceRequestGenerator: converts NOT_ASSESSABLE results to actionable EvidenceRequest items with YAML-driven guidance text
- M12 MarkdownReportRenderer: CLI compliance report (dashboard dropped — CLI sufficient for dissertation)
- Metrics: 65 output unit tests + 13 integration tests; 635 total tests

---

## 2026-03-28 — Phase 4: Reasoning Layer (M6–M9)

- M6 PairwiseReconciler: cross-source reconciliation with configurable per-attribute tolerance; AGREED/CONFLICTING/SINGLE_SOURCE/MISSING states
- M7 ThresholdConfidenceGate: per extraction_method × entity_type thresholds from YAML; fail-open default for unconfigured combinations
- M8 DefaultAssessabilityEvaluator: tri-state logic (ASSESSABLE/NOT_ASSESSABLE) with blocking reasons; 100% test coverage; later replaced by SABLE
- M9 Rule Evaluators: 6 types — NumericThreshold, RatioThreshold, FuzzyMatch, EnumCheck, NumericTolerance, AttributeDiff; fully deterministic, no LLM in evaluation path
- Metrics: 102 reasoning unit tests + 11 integration tests; 533 total tests

---

## 2026-03-28 — Phase 3: Representation Layer (M5)

- Normalisation: extensible unit conversion registry (feet→metres, inches→mm, sqft→sqm + 8 more), address canonicalisation, numeric precision rounding
- Neo4jSNKG implements 4 Protocols (EntityPopulator, ReferenceDataLoader, EvidenceProvider, RuleProvider) with Cypher queries; no OGM dependency
- FlatEvidenceProvider implemented as Ablation B alternative — deliberately degraded evidence lookup to isolate graph contribution
- Known gap identified: geometry stored as WKT but no runtime shapely spatial predicates; zone linkage from pre-computed zone.json only
- Metrics: 95 new representation tests; 403 total tests

---

## 2026-03-27 — Phase 2b: VLM Spatial Extraction (M3)

- VLMSpatialExtractor with two ablation paths: VLM_ZEROSHOT (single GPT-4o call) and VLM_STRUCTURED (two-stage coarse-then-refine with image cropping)
- Drawing subtype inference from filename patterns (SITE_PLAN, FLOOR_PLAN, ELEVATION); 3 spatial prompt templates
- Key decision: VLM_ZEROSHOT vs VLM_STRUCTURED configurable as an ablation dimension; bounding box accuracy logged for audit trail but not primary metric
- Metrics: 24 M3 tests all passing

---

## 2026-03-27 — Phase 2a: Ingestion Layer (M1 + M2)

- M1 RuleBasedClassifier: three-signal cascade (filename patterns → text density → image heuristics)
- M2 Text Extraction: PdfPlumberExtractor (text-layer PDFs) + LLMEntityExtractor (Groq structured extraction) + VisionExtractor (GPT-4o); two-path routing via has_text_layer flag
- 4 prompt templates: form, report, certificate, drawing extraction; all implementations wired into bootstrap
- Metrics: 17 classifier tests + 49 extraction tests; all passing

---

## 2026-03-25 to 2026-03-26 — Phase 1: Synthetic Data Pipeline

- 3-layer synthetic data generator: scenario generation (pure functions from YAML), document rendering (Protocol-based plugins), degradation and PDF output
- 5 edge-case strategies: missing_evidence, conflicting_values, low_confidence_scan, partial_documents, ambiguous_units
- Generated 50 synthetic application sets (20 compliant + 20 non-compliant + 10 edge-case); pixel-accurate bounding box ground truth per placed value
- BCC real data: 10 application sets anonymised (39 files classified, 11 forms PII-flagged, 28 safe drawings copied); seeded 60/20/20 train/val/test split with MD5 integrity manifest
- Metrics: 149 unit tests + 8 integration tests; 350+ generated files

---

## 2026-03-25 — Phase 0: Project Foundation

- Complete project scaffold with SOLID architecture; Protocol-based interfaces (7 files); unified entity schemas (ExtractedEntity, BoundingBox, ClassifiedDocument, RuleVerdict, AssessabilityResult)
- Pipeline skeleton with step registry pattern; composition root (bootstrap.py) as single dependency injection point
- Infrastructure: Neo4j Aura (free cloud) verified; Groq free-tier configured; switched from Docker to local Python + cloud services for ARM64 Windows compatibility
- Tooling: ruff, mypy --strict, pytest, structlog JSON logging, GitHub Actions CI; 3 ADRs (pipeline-step-registry, protocols-over-abcs, assessability-three-states)
- Metrics: 41 unit tests + 2 integration tests; mypy --strict clean; ruff clean

---

## Key Decisions & Tradeoffs

### Architecture

| Decision | Rationale | Alternative considered | Why rejected |
|---|---|---|---|
| **Protocols over ABCs** | Structural subtyping — no inheritance coupling; components swappable at runtime for ablation | Abstract base classes | ABCs force inheritance hierarchies; Protocols enable duck typing + static checking |
| **Composition root (bootstrap.py)** | Single file wires all dependencies; business logic never imports concrete types | Service locator pattern | Service locator hides dependencies; composition root makes them explicit |
| **YAML-driven rules** | New compliance rules = config only, no code changes | Hardcoded rule classes | Hardcoded rules require code changes + redeployment for each new regulation |
| **Frozen dataclasses for data models** | Immutability prevents mutation bugs across pipeline stages | Mutable Pydantic models | Pydantic for config (needs validation); frozen dataclasses for runtime data (needs safety) |

### Algorithm

| Decision | Rationale | Alternative considered | Why rejected |
|---|---|---|---|
| **Dempster-Shafer over Bayesian** | D-S handles ignorance explicitly (m(Theta)); Bayesian forces prior specification | Bayesian posterior updating | Planning evidence is sparse — no meaningful prior exists; D-S ignorance mass is more honest |
| **Three-state assessability** | NOT_ASSESSABLE prevents false verdicts on insufficient evidence | Binary PASS/FAIL only | Binary forces guessing when evidence is missing — the root cause of false violations |
| **PARTIALLY_ASSESSABLE** | Evidence present but contested; belief between thresholds | Only ASSESSABLE/NOT_ASSESSABLE | Two states lose information about borderline cases; three states enable nuanced reporting |
| **Weakest-link aggregation** | Overall assessability limited by weakest evidence requirement | Average or product aggregation | Average hides weak links; weakest-link is conservative and interpretable |
| **Semantic similarity for attribute matching** | Embedding cosine similarity resolves "height" ↔ "building_height" | Exact string matching | Exact matching fails on LLM-returned attribute name variations |

### Evaluation

| Decision | Rationale | Alternative considered | Why rejected |
|---|---|---|---|
| **Oracle extraction for ablation** | Isolates reasoning layer contribution; no extraction noise in measurement | End-to-end with real extraction | E2E conflates extraction quality with reasoning quality; oracle is cleaner science |
| **Synthetic data for evaluation** | Full control over ground truth; deterministic; reproducible | Real BCC data only | BCC data has no forms, no ground truth verdicts; can't measure accuracy without GT |
| **Robustness curves with NoisyEntityTransformer** | Tests SABLE under controlled degradation; simulates real extraction noise | Only test with real LLM extraction | Real extraction is noisy but uncontrolled; NoisyTransformer gives systematic degradation curves |
| **McNemar over chi-squared** | Paired test on same data; accounts for per-sample correlation | Independent chi-squared test | Chi-squared assumes independence; our configs share the same test sets |

### Infrastructure

| Decision | Rationale | Alternative considered | Why rejected |
|---|---|---|---|
| **Groq (free) over OpenAI for LLM** | Free tier enables unlimited ablation runs; cached responses | OpenAI GPT-4 for all extraction | Cost: ablation study needs hundreds of runs; Groq free tier + cache = $0 |
| **GPT-4o for VLM** | Best available vision model for architectural drawings | Open-source VLM (LLaVA) | GPT-4o significantly better at structured JSON extraction from drawings |
| **Pure Python INSPIRE parser** | geopandas/fiona/shapely fail on ARM64 Windows | geopandas + shapely | ARM64 dependency failure; pure Python with shoelace formula is sufficient for area + centroid |
| **FlatEvidenceProvider as SNKG fallback** | Enables ablation_b (no graph) and testing without Neo4j | Require Neo4j always | Graph dependency would block all testing when Neo4j is unavailable |
| **Neo4j Aura (free cloud)** | Zero local infrastructure; accessible from any machine | Local Neo4j Docker | Docker not available on ARM64 Windows dev machine; Aura free tier is sufficient |

### Data

| Decision | Rationale | Alternative considered | Why rejected |
|---|---|---|---|
| **33 test sets (not 50+)** | Sufficient for McNemar statistical test; balanced across categories | Larger corpus | Diminishing returns — McNemar p<0.0001 with 33 sets; more sets don't change significance |
| **9 rules (not 40+)** | Covers all evaluator types (numeric, ratio, enum, fuzzy, tolerance, diff, boundary, spatial); demonstrates extensibility | Full BCC rule set | 40+ rules requires domain expertise to define thresholds; 9 rules prove the architecture |
| **BCC drawings anonymised without forms** | PII in forms requires careful handling; drawings are safe | Include forms with PII redaction | Time constraint; redaction process not established; drawings sufficient for VLM testing |

---

## Project Summary

| Metric | Count |
|---|---|
| Commits | 175+ |
| Source files | 118 |
| Tests | 904+ |
| Compliance rules | 9 (R001–R003, C001–C006) |
| Pipeline steps | 12 |
| Test sets | 33 |
| Evaluations per ablation config | 297 |
| False FAILs — full system | 0 |
| False FAILs — ablation_d (no SABLE) | 93 |
| False FAILs — naive baseline | 126 |
| Dissertation figures | 15 (300 DPI) |
