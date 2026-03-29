# PlanProof — Known Gaps, Issues & Future Ideas

> **Last updated**: 2026-03-29
> **Purpose**: Honest tracking of what's incomplete, what's working but limited, and ideas for improvement.

---

## Critical Gaps (affect dissertation quality)

### 1. Assessability step not firing in E2E pipeline
**Status:** Bug
**Impact:** High — rules go straight to evaluation even when evidence is missing, producing FAIL instead of NOT_ASSESSABLE.
**Root cause:** The assessability step needs `rule_ids` from `context["metadata"]` but the pipeline doesn't populate them. The step silently produces 0 assessability results, so rule evaluation runs on all rules.
**Fix:** Populate `context["metadata"]["rule_ids"]` in the pipeline, or have the assessability step load rules from the rules directory directly.

### 2. rule_id shows "unknown" in verdicts
**Status:** Bug
**Impact:** Medium — report readability. Rules appear as "unknown" instead of "R001", "R002", etc.
**Root cause:** The evaluator reads `rule_id` from `self._params` but the YAML params dict doesn't include `rule_id` — it's on the `RuleConfig` object, not inside `parameters`.
**Fix:** Pass `rule_id` explicitly when calling evaluator.evaluate(), or inject it into params dict before calling.

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

### 6. Synthetic data lacks some rule attributes
**Status:** By design
**Impact:** R003 (site coverage) always NOT_ASSESSABLE because synthetic ground truth doesn't include `building_footprint_area` and `total_site_area`. C-rules also lack required attributes.
**Fix:** Enhance the datagen to produce these attributes in ground truth extractions.

### 7. BCC anonymised data has no application forms
**Status:** Data gap
**Impact:** The 10 BCC sets in `data/anonymised/` contain only architectural drawings — no planning application forms. Rules requiring form data (certificate type, address, site area) can't be evaluated.
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

### Medium-term (strengthens research)
- **VLM fine-tuning (VLM_FINETUNED):** Fine-tune a vision model on architectural drawing annotations
- **Shapely spatial predicates:** Wire real polygon containment checks for zone-based rules
- **Label Studio annotation:** Systematic annotation of VLM extraction results on real drawings
- **Confidence calibration:** Empirical threshold tuning with reliability diagrams
- **Additional BCC data:** Obtain complete application sets (forms + drawings)

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

## Project Statistics (2026-03-29)

| Metric | Count |
|--------|-------|
| Total commits | ~107 |
| Source files | 106 |
| Test files | 76 |
| Tests passing | 754 |
| Tests skipped | 14 |
| Phases complete | 7 of 8 (Phase 7 in progress) |
| Modules implemented | M1-M12 (all) |
| Rules configured | 7 (R001-R003 + C001-C004) |
| Synthetic datasets | 15 (5 compliant + 5 non-compliant + 5 edge-case) |
| Real BCC datasets | 10 (anonymised, drawings only) |
| LLM providers supported | Groq, OpenAI, Ollama |
| VLM providers supported | OpenAI GPT-4o, Gemini (adapter) |
| Pipeline steps | 11 (classification → evidence requests) |
| Ablation configurations | 7 (full + 4 ablations + 2 baselines) |

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
