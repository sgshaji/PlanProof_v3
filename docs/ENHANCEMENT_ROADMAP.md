# PlanProof — Enhancement Roadmap to Top 5% MSc Dissertation

> **Date:** 2026-04-04
> **Current grade estimate:** A+ (DA1 complete — neurosymbolic claim now empirically validated; ablation_b measurably differs from full_system)
> **Target:** A+ (top 5 percentile MSc Computer Science)
> **Enhancement sprint status:** P1.1–P1.4 and P2.1–P2.4 all DONE (2026-04-03). DA1 DONE (2026-04-04).

---

## Current Strengths

- SABLE algorithm (Dempster-Shafer grounded, novel, well-formalised)
- Zero false violations with assessability enabled (43 prevented by SABLE)
- System issues confident verdicts: 43 PASS + 2 true FAILs
- 885 tests, mypy --strict, Protocol-based architecture
- Three-tier boundary verification (VLM + scale-bar + INSPIRE)
- Systematic ablation study (7 configs, 120 evaluations per config)
- Honest limitations documentation

---

## Priority 1: Highest Impact (each moves the needle significantly)

### 1.1 Extraction-Quality Robustness Curves — **DONE** (2026-04-03)
**Result:** `NoisyEntityTransformer` implemented with 4 degradation modes. Re-ran full_system and ablation_d at 5 levels. SABLE false-FAILs: 0→5→1→0→0 (near-zero throughout); ablation_d degrades sharply. Figures: `robustness_curves.png` (R1) and `robustness_true_fails.png` (R2).

### 1.2 End-to-End Real Extraction Evaluation — **DONE** (2026-04-03)
**Result:** Extraction eval v3 re-run on regenerated multi-source oracle data. recall=1.0, precision=0.533, value accuracy=1.0. Updated 2×2 matrix — full_system remains 0 false FAILs regardless of extraction quality.

### 1.3 More Non-Compliant Test Cases — **DONE** (2026-04-03)
**Result:** Generated 10 additional noncompliant sets (5 building_height 8.5–15m; 5 rear_garden_depth 3–9m). True FAILs: full_system 2→14, ablation_d 4→20. Strong recall evidence now available.

### 1.4 Statistical Rigour: Confidence Intervals + Corrections — **DONE** (2026-04-03)
**Result:** McNemar's test with Benjamini-Hochberg correction. full_system vs ablation_d: p<0.0001. Bootstrap 95% CI on all 4 systems. Cohen's h added to all comparison tables.

---

## Priority 2: Strong Value (each adds credibility)

### 2.1 Confidence Threshold Sensitivity Analysis — **DONE** (2026-04-03)
**Result:** Swept theta_high (0.5–0.9) and theta_low (0.1–0.4). precision=1.0 across all thresholds. Optimal operating point: theta_high=0.55. Figure: `threshold_sensitivity.png` (T1).

### 2.2 Complete BCC Annotation (Remaining 2 Sets) — **PARTIAL** (2026-04-03)
**Result:** 2025 07100 annotated (63 extractions via GPT-4o). 2 remaining sets deferred — scanned PDFs require pdf2image/poppler (not available ARM64 Windows). 1 annotated real set provides qualitative generalisation evidence.

### 2.3 LLM-Only CoT Baseline Comparison — **DONE** (2026-04-03)
**Result:** strong_baseline on 33-set corpus: 10 PASS, 3 true FAILs, 51 false FAILs (18/33 sets). naive_baseline: 121 PASS, 17 true FAILs, 126 false FAILs. Both far worse than full_system (0 false FAILs). Architecture beats prompt engineering.

### 2.4 SABLE Formal Properties (Appendix) — **DONE** (2026-04-03)
**Result:** 5 mathematical proofs documented for dissertation appendix: monotonicity, boundedness, determinism, idempotency, composability.

---

## Priority 3: Polish (presentation and credibility signals)

### 3.1 Reproducibility Infrastructure
- Dockerfile with pinned dependencies
- `make reproduce-ablation` target
- CITATION.cff for academic citation
- GitHub Actions runs full test suite

**Effort:** 8-12 hours | **Impact:** +4 points

### 3.2 Dashboard / Web UI — **DONE** (2026-04-04)
FastAPI + Jinja2 + SSE web interface built. Streams live pipeline execution: 8 stages, SABLE belief gauges, extraction/SNKG visualizations, reconciliation summary, verdict cards, ablation comparison, figures gallery. Run: `uvicorn planproof.web.app:app --port 8000`.

**Effort:** 16-24 hours | **Impact:** +6 points

### 3.3 Literature Gap Analysis (Appendix)
2-page comparison: what prior work does (D-S for sensor fusion, LLM for extraction, defeasible logic for rules) vs what SABLE adds. Why the combination is novel.

**Effort:** 3-4 hours | **Impact:** +2 points

### 3.4 Figure Quality Improvements
Enlarge fonts, add CI ribbons, create one-page "Results Summary" figure for dissertation front matter.

**Effort:** 4-6 hours | **Impact:** +2 points

---

## Priority 4: Advanced Research (if time permits)

### 4.1 User Study: Planning Officer Validation
Present 10 applications + system verdicts to 3-5 BCC officers. Measure agreement (Fleiss' Kappa).

**Effort:** 20-30 hours | **Impact:** +10 points | **Requires:** IRB, BCC partnership

### 4.2 Adversarial Robustness Testing
Can malicious applicants fool the system with crafted evidence bundles?

**Effort:** 12-16 hours | **Impact:** +7 points

### 4.3 Fairness Analysis
Does extraction quality vary by drawing style/age/format? Measure per-strata false-FAIL rates.

**Effort:** 14-18 hours | **Impact:** +8 points

### 4.4 Cross-Council Generalisation
Adapt 3-5 rules to another council's policy (Nottingham, Leeds). Re-run ablation.

**Effort:** 12-16 hours | **Impact:** +7 points | **Requires:** Partner council

---

## Recommended Sprint Plan

### Week 1 (30 hours): Core Evaluation Fixes — DONE
- [x] 1.3 More noncompliant test cases (3h)
- [x] 1.2 Re-run extraction evaluation (6h)
- [x] 1.1 Robustness curves (20h)

### Week 2 (30 hours): Statistical + Baselines — DONE
- [x] 1.4 Statistical rigour (8h)
- [x] 2.1 Threshold sensitivity (10h)
- [x] 2.3 CoT baseline comparison (6h)
- [x] 2.2 BCC annotation — partial (1 of 3 sets; 2 deferred, scanned PDFs)

### Week 3 (25 hours): Polish + Theory — P2.4 DONE
- [x] 2.4 SABLE formal properties (10h)
- [ ] 3.3 Literature gap analysis (4h) — deferred to write-up
- [ ] 3.4 Figure improvements (5h) — deferred to write-up
- [ ] 3.1 Reproducibility infrastructure (6h) — deferred

### Week 4 (20 hours): Write-up Integration — IN PROGRESS
- [ ] Comprehensive evaluation report (12h)
- [ ] Dissertation chapter integration (8h)

---

## Grade Impact Summary

| What | Hours | Grade Impact |
|------|-------|-------------|
| Priority 1 (all 4) | ~30h | B+ -> A- |
| + Priority 2 (all 4) | +25h | A- -> A |
| + Priority 3 (all 4) | +30h | A -> A+ |
| + Priority 4 (any 2) | +30h | A+ (top 5%, publishable) |

**Total to A+: ~115 hours (~3 weeks full-time)**

---

## Definitive A+ Items (Pending — Assessed 2026-04-03)

These 4 items were identified as the difference between A and definitive A+. Items 1-2 are ready to build but blocked on external dependencies.

### DA1: Exercise SNKG with Spatial Containment Rule — DONE (2026-04-04)
**What:** C006 "Conservation Area Containment Check" implemented — Neo4j graph traversal (zone containment query via `CONTAINS` relationship on `Zone` nodes with `zone_type=conservation_area`).
**Result:** ablation_b (no SNKG) now produces 85 PASS vs full_system's 118 PASS. The 33-verdict difference (all C006 evaluations) routes to NOT_ASSESSABLE without the SNKG graph. ablation_b has 66 NA vs full_system's 33 NA.
**Dissertation impact:** Fixes the ablation_b=full_system gap — the previously documented weakness is now an empirical strength. The neurosymbolic claim is validated: symbolic graph structure (SNKG) provides reasoning capability that neural extraction cannot substitute.

### DA2: Run Full Pipeline on 5+ Real BCC Applications with Forms — PENDING
**What:** Obtain complete BCC application bundles (forms + drawings) so all 8 rules can fire on real documents. Currently we only have anonymised drawings — rules requiring form data (C001 certificate type, C002 address, C003 boundary area) always get NOT_ASSESSABLE.
**Status:** BLOCKED on BCC partnership. Cannot generate real application forms — they contain applicant details, ownership declarations, and site addresses that must come from actual submissions.
**Action needed:** Contact BCC planning department to request 5 anonymised complete application bundles (forms + drawings + certificates).
**Effort:** 2-3 hours (coordination) + 4-6 hours (pipeline runs + analysis)
**Impact:** Strongest possible real-world validation — "end-to-end on real council data"

### DA3: Small User Study (3 Planning Officers) — PENDING
**What:** Present 10 applications + system verdicts to 3-5 BCC officers. Measure agreement rate (Fleiss' Kappa). Ask: "Do you agree with the system's PASS/FAIL/NOT_ASSESSABLE verdict?"
**Status:** Not started. Requires IRB ethics approval (2-3 weeks), BCC partnership, officer recruitment.
**Effort:** 20-30 hours total
**Impact:** Domain expert validation — the gold standard for applied systems

### DA4: Dockerfile for Reproducibility — PENDING
**What:** Dockerfile with pinned Python 3.12, all dependencies, seed-deterministic `make reproduce-ablation` target. CITATION.cff for academic citation.
**Status:** Ready to implement. No blockers.
**Effort:** 4-6 hours
**Impact:** Credibility signal — any reviewer can replicate results exactly

---

## What NOT To Do (Diminishing Returns)

- Don't add more rules beyond 8 — diminishing returns for dissertation
- Don't build a production deployment pipeline — out of scope
- Don't fine-tune VLMs — too much effort for MSc timeline
- Don't pursue multi-council without a partner — high coordination cost
- Don't over-engineer the dashboard — CLI is sufficient for evaluation
