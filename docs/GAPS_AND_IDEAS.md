# PlanProof — Gaps, Limitations & Future Work

> **Last updated**: 2026-04-04
> **Purpose**: Honest tracking of what's incomplete, what's working but limited, and what needs to happen next. This document feeds directly into the dissertation Limitations and Future Work sections.

---

## OPEN GAPS (require action)

### GAP 1: End-to-End Pipeline Not Validated on Real Data
**Severity:** HIGH
**Status:** OPEN

The full pipeline (upload real PDFs → classify → extract → SNKG → reconcile → SABLE → evaluate → verdicts) has never produced meaningful verdicts on a real BCC planning application. Each component works individually. The ablation study validates the reasoning layer with oracle entities. But the complete chain breaks on real data.

**Why it breaks:**
1. **No application forms in BCC data** — only architectural drawings. Rules needing form data (C001 certificate, C002 address, C003 area) can never fire.
2. **SNKG not populated during live runs** — the ablation runner injects entities directly into memory. The live pipeline creates a Neo4j connection but never populates it with extracted entities.
3. **Entity-to-rule attribute mismatch** — LLM extracts attributes like "building_height" but the source_document prefix doesn't always match rule `acceptable_sources` requirements.
4. **VLM unreliable on real drawings** — GPT-4o frequently responds "I'm unable to analyze the content of the image" for both synthetic and real architectural drawings.

**Component-level status:**

| Component | Code | Unit tested | Works on synthetic | Works on real BCC | Works E2E |
|---|---|---|---|---|---|
| Classification (M1) | Done | Yes | Yes | Yes | Yes |
| Text Extraction (M2) | Done | Yes | Yes | Partially | Yes |
| LLM Extraction | Done | Yes | Yes (FORMs) | 1 set (63 entities) | Partially |
| VLM Extraction | Done | Yes | Limited | Limited | Partially |
| Normalisation (M5) | Done | Yes | Yes | Yes | Yes |
| SNKG Population | Done | Yes | Simulated only | **Never** | **NO** |
| Reconciliation (M6) | Done | Yes | Yes | Yes | Yes |
| SABLE (M8) | Done | Yes | Yes | All NOT_ASSESSABLE | No meaningful verdicts |
| Rule Evaluation (M9) | Done | Yes | Yes (oracle) | Never reached | **NO** |
| Boundary Verification | Done | Yes | Never on real data | **Never** | **NO** |

**How to fix:**
1. Obtain 5 complete BCC application bundles (forms + drawings + certificates)
2. Wire GraphPopulationStep to actually populate Neo4j during live pipeline runs
3. Fix entity source_document prefixes to consistently match rule acceptable_sources
4. Improve VLM prompts for real architectural drawing formats
5. Add attribute mapping between LLM-returned names and rule requirement names

**Dissertation framing:** "The reasoning layer is validated through a 297-evaluation ablation study. End-to-end integration on real documents is architecturally supported but requires further development in extraction-to-rule matching and SNKG population for operational deployment."

---

### GAP 2: No Real Application Forms
**Severity:** HIGH
**Status:** BLOCKED — needs BCC partnership

The 10 BCC sets in `data/anonymised/` contain only architectural drawings. No planning application forms exist in our data. This means:
- R001/R002 can't get `zone_category` from FORM source
- C001 can't check certificate type
- C002 can't compare form address vs drawing address
- C003 can't compare stated area vs reference area

**How to fix:** Contact BCC planning department. Request 5 anonymised complete application bundles (forms + drawings + certificates). Redact PII.

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
**Severity:** MEDIUM
**Status:** OPEN

Synthetic data is generated by our own code with planted values. Real BCC applications have:
- Complex multi-page form layouts with checkboxes, signatures, stamps
- Handwritten annotations on drawings
- Scanned/photographed documents (not clean PDFs)
- Inconsistent naming conventions across applicants
- Multiple revisions of the same drawing

Our synthetic data has none of this complexity.

**How to fix:** Use 10 BCC drawing sets as reference to generate more realistic synthetic documents. Or focus evaluation on the reasoning layer (ablation study) and acknowledge extraction evaluation as limited.

---

### GAP 6: VLM Extraction Unreliable
**Severity:** MEDIUM
**Status:** OPEN

GPT-4o frequently refuses to extract measurements from architectural drawings, responding "I'm unable to analyze the content of the image directly." This affects both synthetic elevation/site plan PNGs and real BCC scanned drawings.

**How to fix:** Improve VLM prompts with more specific instructions. Test with different VLM providers (Claude Vision, Gemini). Consider fine-tuning an open-source vision model on architectural drawing annotations.

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
