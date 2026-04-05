# PlanProof — Gaps, Limitations & Future Work

> **Last updated**: 2026-04-05
> **Purpose**: Honest tracking of what's incomplete, what's working but limited, and what needs to happen next. This document feeds directly into the dissertation Limitations and Future Work sections.

---

## OPEN GAPS (require action)

### GAP 1: End-to-End Pipeline Partially Validated on Real Data
**Severity:** MEDIUM (downgraded from HIGH)
**Status:** PARTIALLY RESOLVED (2026-04-05)

**What changed (2026-04-05):** Extraction evaluation run on 9 real BCC planning applications. Results: recall=93.3%, precision=38.6%, value accuracy=86.7% across 5 ground-truth attributes. Classification and text extraction work on real forms. LLM extraction successfully finds entities from Planning Portal forms.

**Remaining gaps:**
1. **SNKG not populated during live runs** — the ablation runner injects entities directly into memory. The live pipeline creates a Neo4j connection but never populates it with extracted entities.
2. **VLM unreliable on real drawings** — GPT-4o frequently refuses to extract from architectural drawings.
3. **Full SABLE pipeline not run end-to-end on real data** — extraction works, but extracted entities have not yet been fed through reconciliation → assessability → rule evaluation on real BCC data.

**Component-level status:**

| Component | Code | Unit tested | Works on synthetic | Works on real BCC | Works E2E |
|---|---|---|---|---|---|
| Classification (M1) | Done | Yes | Yes | **Yes (9/9 forms)** | Yes |
| Text Extraction (M2) | Done | Yes | Yes | **Yes (9/9 forms)** | Yes |
| LLM Extraction | Done | Yes | Yes (FORMs) | **Yes — recall 93.3%** | Partially |
| VLM Extraction | Done | Yes | Limited | Limited | Partially |
| Normalisation (M5) | Done | Yes | Yes | Yes | Yes |
| SNKG Population | Done | Yes | Simulated only | **Never** | **NO** |
| Reconciliation (M6) | Done | Yes | Yes | Yes | Yes |
| SABLE (M8) | Done | Yes | Yes | Not yet run on real extractions | Pending |
| Rule Evaluation (M9) | Done | Yes | Yes (oracle) | Not yet run on real extractions | Pending |
| Boundary Verification | Done | Yes | Never on real data | **Never** | **NO** |

**Dissertation framing:** "Extraction evaluated on 9 real BCC planning applications: 93.3% recall, 86.7% value accuracy. Reasoning layer validated through 297-evaluation ablation study with oracle entities. End-to-end integration from extraction through to verdicts on real data is the next step."

---

### ~~GAP 2: No Real Application Forms~~ → RESOLVED
**Severity:** ~~HIGH~~ N/A
**Status:** **RESOLVED** (2026-04-05)

**Resolution:** 9 of 10 BCC applications in `data/raw/` contain Planning Portal application forms (PDF with text layer). Only `2025 00841` has no form. The `data/anonymised/` directory was missing forms because they were stripped during anonymisation (forms contain PII). Working from `data/raw/` resolves this entirely. Ground truth annotations created for all 9 forms in `data/annotated/`.

---

### GAP 3: SNKG Not Populated in Live Pipeline
**Severity:** MEDIUM
**Status:** OPEN — code exists but not wired

Neo4j Aura is connected (tested 2026-04-04). `Neo4jSNKG` class exists with `load_reference_data()` and `populate_entities()` methods. `GraphPopulationStep` exists as a pipeline step. But in practice:
- The ablation runner injects entities directly (bypasses Neo4j)
- The web UI pipeline runner uses FlatEvidenceProvider (bypasses Neo4j)
- C006 conservation area check is simulated in the ablation runner, not queried from Neo4j

**How to fix:** Wire the live pipeline (web UI + CLI) to populate Neo4j with extracted entities during each run, then use SNKG as the evidence provider instead of FlatEvidenceProvider.

---

### GAP 4: Boundary Verification Untested on Real Data
**Severity:** MEDIUM
**Status:** OPEN

Three-tier boundary verification code is complete:
- Tier 1 (VLM visual alignment): needs a location plan image with red-line boundary
- Tier 2 (Scale-bar measurement): needs location plan with visible scale bar
- Tier 3 (INSPIRE polygon): needs postcode for geocoding (PII removed from BCC data)

None of the 10 BCC drawing sets have been confirmed to contain location plans. The pipeline step currently produces `INSUFFICIENT_DATA` for every application.

**How to fix:** Identify which BCC drawings are location plans. Obtain postcodes for test applications. Run boundary verification on at least 3 real location plans.

---

### GAP 5: Synthetic Data Not Representative of Real Applications
**Severity:** LOW (downgraded from MEDIUM)
**Status:** PARTIALLY MITIGATED (2026-04-05)

**What changed (2026-04-05):** Synthetic datagen pipeline upgraded to produce all 8 assessable rules' required attributes (was 3). Form generator now renders 12 tracked attributes including certificate_type, ownership_declaration, form_address, zone_category, site_location, stated_site_area, building_footprint_area, total_site_area, rear_garden_depth. New EXTERNAL_DATA document generator for C003/C006. Extraction prompts updated.

**Remaining gap:** Synthetic drawings (site plan, floor plan) are still visually simplistic compared to real architectural drawings. However, this is mitigated by evaluating extraction on real BCC data directly (9 applications, recall=93.3%). Ablation study uses oracle entities and does not depend on document quality.

**Dissertation framing:** "Synthetic data provides comprehensive attribute coverage for ablation testing. Extraction accuracy is validated on real BCC documents, not synthetic data."

---

### GAP 6: VLM Extraction Unreliable
**Severity:** LOW (downgraded from MEDIUM)
**Status:** PARTIALLY RESOLVED (2026-04-05)

**What changed (2026-04-05):** VLM now processes PDF drawings (pdfplumber page-to-image → GPT-4o). Successfully extracts building_height, ridge_height, eave_height, room_dimensions, floor_area, rear_garden_depth, site_coverage, site_area from real BCC architectural drawings. `2025 07100` yielded 136 entities across 7 pages; `2025 00841` yielded 23 entities from 5 drawing pages.

**Remaining issues:** VLM sometimes hallucinates dimensions (e.g. returning values in mm vs metres inconsistently). Some scanned drawings with no text layer still produce limited results. Confidence calibration needed.

**How to fix further:** Post-processing to normalise units (detect mm vs m). Cross-validate VLM-extracted values across multiple pages of the same drawing set.

---

## KNOWN LIMITATIONS (documented for dissertation, no fix planned)

### Confidence Scores Are Heuristic
Extraction confidence values are hardcoded per entity type (ADDRESS: 0.85, MEASUREMENT: 0.80, etc.). No empirical calibration against real extraction accuracy. SABLE uses these as inputs to mass function construction, so uncalibrated confidence affects belief scores.

### Ablation Uses Oracle Extraction
The ablation study injects ground-truth entities (confidence=1.0) to isolate the reasoning layer. This is valid experimental design but means ablation results don't reflect real extraction noise. The robustness curves (Phase 8c enhancement) partially address this by testing with synthetic noise injection.

### 9 of 40+ BCC Rules Implemented
Real BCC planning validation has 40+ checks. We implement 9 (R001-R003, C001-C006). Findings may not generalise to the full rule set, though the architecture is extensible (new rule = YAML config + optional evaluator class).

### No User Study
No validation that system verdicts match planning officer judgment. Domain expert feedback would strengthen the practical validity claim. Requires IRB approval and BCC partnership.

### ARM64 Windows Development Platform
shapely, geopandas, fiona, pymupdf, poppler all fail to build on ARM64 Windows. This limits:
- No real polygon spatial predicates (shapely)
- No PDF rasterisation for scanned drawings (pymupdf/poppler)
- INSPIRE GML parsed with pure Python (workaround, not ideal)

---

## RESOLVED (kept for audit trail)

| # | Issue | Resolution | Date |
|---|---|---|---|
| R1 | Assessability step not firing | Added rule_ids to Pipeline context | 2026-04-01 |
| R2 | rule_id shows "unknown" | Injected into evaluator params | 2026-04-01 |
| R3 | Entity attribute matching | SABLE semantic similarity | 2026-03-29 |
| R4 | R003 always NOT_ASSESSABLE | Enriched datagen + extra_attributes | 2026-04-02 |
| R5 | ablation_b = full_system | C006 conservation area rule (DA1) | 2026-04-04 |
| R6 | Only 2 true FAILs | Expanded noncompliant corpus (14 true FAILs) | 2026-04-03 |
| R7 | Beliefs stuck at 0.21 | Multi-source evidence + fixed reliability weights | 2026-04-03 |
| R8 | Evaluators crash on scalar evidence | Hardened fuzzy_match, numeric_tolerance, attribute_diff | 2026-04-03 |
| R9 | Groq model decommissioned | Updated llama-3.1 → llama-3.3 | 2026-04-03 |
| R10 | GAP 2: No application forms in BCC data | Forms exist in `data/raw/` (9/10 apps). `data/anonymised/` was missing them due to PII strip. | 2026-04-05 |
| R11 | 7 of 9 rules NOT_ASSESSABLE | Datagen updated: 12 tracked form attributes, EXTERNAL_DATA generator, all 8 assessable rules fire | 2026-04-05 |
| R12 | Extraction never validated on real data | Extraction eval on 9 real BCC forms: recall=93.3%, value accuracy=86.7% | 2026-04-05 |
| R13 | Drawing PDFs misclassified as FORM | Content-based classifier: analyses keywords + page geometry, not filenames. All BCC drawing PDFs now correctly classified as DRAWING. | 2026-04-05 |
| R14 | VLM couldn't process PDF drawings | `VLMSpatialExtractor._extract_from_pdf()` converts pages to PNG via pdfplumber → GPT-4o. Building heights, room dims, site areas now extracted from real BCC drawings. | 2026-04-05 |

---

## FUTURE WORK (beyond dissertation)

- **Complete BCC data**: Obtain forms + drawings + certificates for 5+ applications
- **Production SNKG**: Populate Neo4j during live pipeline runs
- **VLM fine-tuning**: Train on architectural drawing annotations
- **Confidence calibration**: Reliability diagrams from real extraction data
- **Multi-council generalisation**: Test on Nottingham, Leeds, etc.
- **User study**: 3-5 planning officers validate system verdicts
- **Dashboard**: Full web UI for council admin use (Persona 2)
- **Dockerfile**: Pinned dependencies for reproducibility
- **Cross-interaction ablation**: Test component synergies (remove 2+ simultaneously)
