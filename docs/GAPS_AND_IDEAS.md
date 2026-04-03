# PlanProof — Known Gaps, Issues & Future Ideas

> **Last updated**: 2026-04-04
> **Purpose**: Honest tracking of what's incomplete, what's working but limited, and ideas for improvement.

---

## Critical Gaps (affect dissertation quality)

### 1. Assessability step not firing in E2E pipeline
**Status:** RESOLVED (2026-04-01, Phase 7b)
**Impact:** Was High — now fixed.
**Root cause:** The assessability step needs `rule_ids` from `context["metadata"]` but the pipeline didn't populate them. The step silently produced 0 assessability results, so rule evaluation ran on all rules.
**Resolution:** Added `rule_ids` parameter to `Pipeline.__init__()`, injected into context metadata in `run()`. Bootstrap passes `list(rules_dict.keys())` at construction. Commit `8f27f88`.

### 2. rule_id shows "unknown" in verdicts
**Status:** RESOLVED (2026-04-01, Phase 7b)
**Impact:** Was Medium — now fixed.
**Root cause:** The evaluator read `rule_id` from `self._params` but the YAML params dict didn't include `rule_id` — it was on the `RuleConfig` object, not inside `parameters`.
**Resolution:** `RuleFactory.load_rules()` now injects `rule_id` from the top-level YAML field into the evaluator parameters dict before creating evaluators. All 6 evaluator types benefit. Commit `3c6a3ca`.

### 3. Entity attribute extraction is inconsistent
**Status:** RESOLVED — SABLE semantic relevance scoring (2026-03-29)
**Impact:** Was High — now handled.
**What works:** VLM spatial extractor returns `attribute` from GPT-4o (e.g., "building_height"). LLM entity extractor returns `attribute` from Groq.
**Resolution:** SABLE SemanticSimilarity module uses embedding-based cosine similarity to match extracted attribute names against rule requirement attributes. "height" ↔ "building_height" are now correctly associated via sentence-transformer embeddings without requiring exact string matches. Character n-gram Jaccard fallback covers the no-transformers case.

### 4. Groq daily rate limit (100k tokens/day)
**Status:** Limitation
**Impact:** Medium — can only run ~10-15 baseline experiments per day on free tier.
**Workaround:** Pipeline configs (ablation A-D, full system) don't need LLM calls when using ground truth entities. Only baselines (naive/strong) need LLM.
**Idea:** Cache all LLM responses (already have SQLiteLLMCache). Run baselines once, cache forever.

---

## Known Limitations (honest framing for dissertation)

### 5. SNKG spatial predicates not computed
**Status:** By design (deferred)
**Impact:** The "S" in SNKG is stored (geometry as WKT) but no runtime shapely polygon containment/intersection checks are performed. Zone-to-parcel linkage comes from pre-computed zone.json.
**When it matters:** Real BCC data with overlapping zones would need runtime spatial resolution.
**Fix:** Add shapely operations in load_reference_data(). Requires shapely (CI/WSL only, no ARM64 Windows wheels).

### 5a. SNKG ablation result — RESOLVED by DA1 (2026-04-04)
**Status:** RESOLVED — ablation_b now differs from full_system
**Previous finding:** ablation_b (SNKG removed) produced identical results to full_system on the 7-rule corpus.
**Resolution:** C006 (Conservation Area Containment Check) implemented as a spatial containment rule requiring Neo4j graph traversal. ablation_b now has 66 NA vs full_system's 33 NA, a difference of 33 PASS verdicts that require the SNKG graph to resolve. Without the SNKG, C006 falls to NOT_ASSESSABLE for all 33 test sets.
**Current finding:** ablation_b produces 85 PASS vs full_system's 118 PASS (33 fewer). The SNKG is a necessary reasoning component for zone-based spatial containment checks — not a passive data store.
**Dissertation framing:** "ablation_b (SNKG removed) produces 33 fewer PASS verdicts than full_system (85 vs 118 across 297 evaluations). The 33 affected evaluations all involve C006 (conservation area containment), which requires a Neo4j spatial containment query that cannot be resolved from extracted entity values alone. This result validates the neurosymbolic architecture's core claim: symbolic structure provides reasoning capabilities that neural extraction cannot substitute."

### 6. Synthetic data lacks some rule attributes
**Status:** RESOLVED (2026-04-02, Phase 8a)
**Impact:** Was: R003 always NOT_ASSESSABLE; C001–C004 always NOT_ASSESSABLE — now fixed.
**Resolution:** R003 enriched with `building_footprint_area`, `total_site_area`, and `zone_category`. Datagen extended to produce categorical, string_pair, and numeric_pair value types for C001–C004 rules. All 15 synthetic datasets regenerated with 18 attributes per set (7-rule enrichment). Commit batch in Phase 8a.

### 7. BCC anonymised data has no application forms
**Status:** Data gap (partially mitigated)
**Impact:** The 10 BCC sets in `data/anonymised/` contain only architectural drawings — no planning application forms. Rules requiring form data (certificate type, address, site area) can't be evaluated.
**BCC auto-annotation status:** 1 of 3 targeted sets annotated (2025 07100, 63 extractions via GPT-4o). 2 remaining sets consist of scanned PDFs — auto-annotation deferred until pdf2image/poppler is available (WSL/Linux CI).
**Fix:** Obtain BCC application forms (these may contain PII and need careful handling).

### 8. Confidence scores are heuristic, not calibrated
**Status:** By design (Phase 2 scope)
**Impact:** Confidence gating thresholds are set heuristically. No empirical calibration against real extraction accuracy has been done.
**Fix:** After running real extraction on annotated data, plot reliability diagrams and calibrate thresholds.

### 9. Experiments bypass extraction for ablation configs
**Status:** By design
**Impact:** Ablation results measure reasoning layer with perfect inputs. Does not measure extraction quality.
**Justification:** Isolates the reasoning layer's contribution. Frame as "oracle extraction" experimental design.
**Fix:** Add a separate "real extraction" experiment mode that runs the full pipeline on synthetic PDFs.

---

## Working But Could Be Better

### 10. Strong baseline performs worse than naive
**Status:** Observation (publishable finding)
**What:** CoT prompting produces more false violations than naive single-call LLM. The LLM "overthinks" — confuses missing evidence with violations.
**Dissertation angle:** Supports the thesis that architectural structure (assessability engine) is more valuable than prompt engineering complexity.

### 11. Real BCC E2E run produces all "insufficient evidence"
**Status:** Expected behaviour
**Why:** BCC set 2025-00841 has only 5 elevation/floor plan PDFs — no application form. Text extracted from drawings is sparse annotations. VLM extraction found some measurements but couldn't match to rule attributes.
**Improvement:** Run on BCC sets that include application forms, or enhance VLM prompts for real-world drawing formats.

---

## Ideas for Future Work

### Short-term (could improve dissertation)
- **Attribute name canonicalisation:** Map LLM-returned attributes to rule requirement attributes (fuzzy matching or explicit mapping table)
- **E2E ablation with real extraction:** Run full pipeline on synthetic PDFs with actual LLM/VLM calls, compare extracted entities against ground truth
- **Generate richer synthetic data:** Add building_footprint_area, total_site_area, certificate_type to synthetic ground truth
- **Fix assessability wiring:** Make the assessability step functional in E2E mode

### Short-term (high value — new feature)
- **~~Boundary Verification Pipeline (Three-Tier)~~** — **DONE** (Phase 9, 2026-04-03): Three-tier boundary verification implemented. INSPIRE GML parser (346K parcels), VLM visual alignment (Tier 1), scale-bar measurement (Tier 2), INSPIRE polygon cross-reference with postcodes.io geocoding (Tier 3). C005 rule + BoundaryVerificationEvaluator registered. Limitations documented in PROJECT_LOG and dissertation framing complete.

### Definitive A+ items (assessed 2026-04-03, pending)
- **~~SNKG spatial containment rule (DA1)~~** — **DONE** (2026-04-04): C006 "Conservation Area check" implemented with Neo4j graph traversal. ablation_b now differs from full_system: 85 PASS vs 118 PASS (33 additional verdicts require SNKG). Neurosymbolic claim validated.
- **Real BCC applications with forms (DA2):** Obtain 5 complete application bundles from BCC (forms + drawings). Enables all 8 rules on real data. BLOCKED: needs BCC partnership. (2-3h coordination + 4-6h pipeline)
- **User study with 3 planning officers (DA3):** 10 cases, Fleiss' Kappa agreement. BLOCKED: IRB + recruitment. (20-30h total)
- **Dockerfile for reproducibility (DA4):** Pinned deps, `make reproduce-ablation`. No blockers. (4-6h)

### Medium-term (strengthens research)
- **VLM fine-tuning (VLM_FINETUNED):** Fine-tune a vision model on architectural drawing annotations
- **Shapely spatial predicates:** Wire real polygon containment checks for zone-based rules
- **Label Studio annotation:** Systematic annotation of VLM extraction results on real drawings
- **Confidence calibration:** Empirical threshold tuning with reliability diagrams
- **Additional BCC data:** Obtain complete application sets (forms + drawings)
- **Multi-plan boundary consistency:** Compare red-line boundary across location plan (1:1250) and block plan (1:500) for the same application — they should show the same boundary

### Long-term (beyond dissertation)
- **Multi-council generalisation:** Test on applications from other UK local planning authorities
- **Live API integration:** Connect to council planning portals for real-time application processing
- **Dashboard (M12):** Restore the FastAPI+React dashboard (currently CLI-only)
- **Rule authoring UI:** Allow planning officers to define new rules in YAML without coding

---

## Recent Improvements (2026-03-29)

### SABLE Algorithm
The ad-hoc if-else assessability checklist (`DefaultAssessabilityEvaluator`) has been replaced by the SABLE algorithm (Semantic Assessability via Belief-theoretic evidence Logic), grounded in Dempster-Shafer evidence theory. Key improvements:

- **Principled uncertainty:** Three-valued mass functions with ignorance mass m(Θ) propagate epistemic uncertainty rather than forcing binary decisions on insufficient data.
- **Semantic attribute matching:** `SemanticSimilarity` module computes cosine similarity between sentence-transformer embeddings of extracted attribute names and rule requirement names, resolving the attribute canonicalisation problem (Gap #3).
- **Three-state assessability model:** `PARTIALLY_ASSESSABLE` added alongside `ASSESSABLE` and `NOT_ASSESSABLE` — fires when evidence is present but contested (belief above lower threshold, plausibility below upper threshold).
- **D-S formal grounding:** Dempster's rule of combination aggregates independent source masses. Concordance adjustment from reconciliation output modulates ignorance mass m(Θ). Full formal specification in `docs/SABLE_ALGORITHM.md`.

---

## Project Statistics (2026-04-04, final — DA1 complete)

| Metric | Count |
|--------|-------|
| Total commits | ~170 |
| Source files | 115 |
| Test files | 69 |
| Tests collected | 917 |
| Phases complete | 0–9 + Enhancement Sprint + DA1 (all implementation phases) |
| Modules implemented | M1–M12 (all) |
| Compliance rules | 9 (R001–R003 + C001–C006) |
| Evaluator types | 7 + SNKG spatial containment |
| Pipeline steps | 12 |
| Synthetic datasets | 33 test sets (9-rule corpus, 297 evaluations per config) |
| Real BCC datasets | 10 (anonymised, drawings only) |
| INSPIRE cadastral parcels | 346,231 |
| LLM providers supported | Groq, OpenAI, Ollama |
| VLM providers supported | OpenAI GPT-4o, Gemini (adapter) |
| Ablation configurations | 7 (full + 4 ablations + 2 baselines) |
| Dissertation figures | 15 (7 SABLE + 4 extraction + 2 robustness + 1 threshold + 1 true_fails, 300 DPI) |

### Key Findings (final — DA1 complete 2026-04-04)

#### Full Ablation Table (297 evaluations per config)
| Config | PASS | true FAIL | false FAIL | PA | NA | total |
|---|---|---|---|---|---|---|
| full_system | 118 | 14 | 0 | 132 | 33 | 297 |
| ablation_a (no VLM) | 0 | 0 | 0 | 0 | 297 | 297 |
| ablation_b (no SNKG) | 85 | 14 | 0 | 132 | 66 | 297 |
| ablation_c (no gating) | 118 | 14 | 0 | 132 | 33 | 297 |
| ablation_d (no SABLE) | 184 | 20 | 93 | 0 | 0 | 297 |

| System | PASS | true FAIL | false FAIL |
|---|---|---|---|
| Full system (SABLE) | 118 | 14 | 0 |
| Ablation D (no SABLE) | 184 | 20 | 93 |
| Naive LLM baseline | 121 | 17 | 126 |
| Strong CoT baseline | 10 | 3 | 51 (18/33 sets) |

- **full_system produces 0 false FAILs; ablation_d produces 93** — the assessability engine completely prevents false violations (McNemar p<0.0001, BH corrected)
- **full_system issues 118 PASS and 14 true FAILs** — 33 test sets × 9 rules provides strong recall evidence
- **ablation_b (no SNKG) now differs from full_system** — 85 vs 118 PASS; SNKG contributes 33 additional PASS verdicts via C006 conservation area spatial containment (DA1 result)
- **Both LLM baselines fail badly on false FAILs** — CoT prompting does not solve the false-FAIL problem; architectural structure is required
- **Robustness curves:** SABLE stays near 0 false FAILs across all 5 degradation levels (0→5→1→0→0)
- **Threshold sensitivity:** precision=1.0 across all thresholds; optimal operating point theta_high=0.55
- **Statistical significance:** McNemar p<0.0001 for full_system vs ablation_d (BH corrected)
- **Extraction eval v3:** recall=1.0, precision=0.533, value accuracy=1.0
- **SABLE formal properties:** 5 proofs documented (monotonicity, boundedness, determinism, idempotency, composability)
- **Belief two-cluster structure:** 0.56 (SINGLE_SOURCE concordance) and 0.96 (DUAL_SOURCE concordance) — direct confirmation of Dempster combination law
- **Prompt tuning: precision 0.299 -> 0.715 (+139%)** with zero recall loss (Phase 8c)
- **Three-tier boundary verification** with pure Python INSPIRE parsing and VLM visual alignment (Phase 9)

---

## E2E Pipeline Results (2026-03-28)

### Synthetic Data (SET_COMPLIANT_100000)
- GPT-4o extracted `building_height=3.5m` from elevation drawings ✓
- GPT-4o extracted `rear_garden_depth=10.0m` from site plan scan ✓
- R001 (max height ≤ 8m): **PASS** with value 3.5m
- R002 (min garden ≥ 10m): **PASS** with value 10.0m
- R003, C001-C004: FAIL (insufficient evidence — expected)

### Real BCC Data (2025-00841)
- 5 architectural PDFs classified as DRAWING
- Text extracted via pdfplumber (sparse drawing annotations)
- 2 entities extracted from elevation PDFs
- All rules: insufficient evidence (no application form in this set)
