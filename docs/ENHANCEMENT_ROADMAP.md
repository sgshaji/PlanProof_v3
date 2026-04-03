# PlanProof — Enhancement Roadmap to Top 5% MSc Dissertation

> **Date:** 2026-04-03
> **Current grade estimate:** B+ / A- (strong architecture + valid findings, gaps in evaluation rigour)
> **Target:** A+ (top 5 percentile MSc Computer Science)

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

### 1.1 Extraction-Quality Robustness Curves
**Problem:** Ablation study uses oracle extraction. Real systems degrade.
**Solution:** Implement `NoisyEntityTransformer` that injects controlled degradation:
- Value perturbation: +/-5% Gaussian noise on measurements
- Attribute misattribution: swap building_height <-> rear_garden_depth (10-20%)
- Entity dropout: randomly remove 10-30% of entities
- Confidence degradation: resample 0.6-0.9 (instead of 1.0)

Run ablation suite at 5 degradation levels. Plot F2 vs degradation curves.

**Effort:** 15-20 hours | **Impact:** +8 points | **API needed:** No

### 1.2 End-to-End Real Extraction Evaluation (Updated)
**Problem:** Current extraction evaluation uses pre-fix synthetic data.
**Solution:** Re-run extraction eval with new multi-source data:
1. `python scripts/run_extraction_eval.py --version v3` on regenerated data
2. `python scripts/run_extraction_ablation.py` for updated 2x2 matrix
3. Document: does the pipeline work end-to-end with real LLM/VLM calls?

**Effort:** 4-6 hours | **Impact:** +6 points | **API needed:** Groq + OpenAI (~$5)

### 1.3 More Non-Compliant Test Cases
**Problem:** Only 2 true FAILs in the corpus. Weak recall evidence.
**Solution:** Generate 10 additional noncompliant sets with varied violations:
- 5 sets with building_height violations (8.5-15m)
- 5 sets with rear_garden_depth violations (3-9m)
Target: 8-10 true FAILs detected.

**Effort:** 2-3 hours | **Impact:** +4 points | **API needed:** No

### 1.4 Statistical Rigour: Confidence Intervals + Corrections
**Problem:** Current metrics lack error bars. No multiple-comparison correction.
**Solution:**
- Bootstrap 95% CI for all metrics (already implemented, just needs running on new data)
- Benjamini-Hochberg correction for multiple comparisons
- Effect sizes (Cohen's h) already computed — add to all tables

**Effort:** 6-8 hours | **Impact:** +4 points | **API needed:** No

---

## Priority 2: Strong Value (each adds credibility)

### 2.1 Confidence Threshold Sensitivity Analysis
Sweep SABLE thresholds (theta_high: 0.5-0.9, theta_low: 0.1-0.4). Plot precision-recall-automation operating curves. Find optimal operating point.

**Effort:** 8-12 hours | **Impact:** +5 points | **API needed:** No

### 2.2 Complete BCC Annotation (Remaining 2 Sets)
Install pymupdf, re-run auto_annotate_bcc.py for the 2 scanned-PDF sets. Gives 3 real-world sets for qualitative evaluation.

**Effort:** 2-4 hours | **Impact:** +3 points | **API needed:** OpenAI (~$2)

### 2.3 LLM-Only CoT Baseline Comparison
Run current strong_baseline (per-rule Chain-of-Thought LLM) on the regenerated data. Compare false-FAIL rates against full_system.

**Effort:** 4-6 hours | **Impact:** +5 points | **API needed:** Groq

### 2.4 SABLE Formal Properties (Appendix)
Write mathematical proofs for: monotonicity (more evidence -> higher belief), boundedness (output in [0,1]), determinism (same input -> same output). 2-3 pages.

**Effort:** 8-10 hours | **Impact:** +5 points | **API needed:** No

---

## Priority 3: Polish (presentation and credibility signals)

### 3.1 Reproducibility Infrastructure
- Dockerfile with pinned dependencies
- `make reproduce-ablation` target
- CITATION.cff for academic citation
- GitHub Actions runs full test suite

**Effort:** 8-12 hours | **Impact:** +4 points

### 3.2 Dashboard / Web UI
Restore FastAPI + React dashboard showing: rule verdicts, belief intervals, missing evidence requests, boundary map.

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

### Week 1 (30 hours): Core Evaluation Fixes
- [ ] 1.3 More noncompliant test cases (3h)
- [ ] 1.2 Re-run extraction evaluation (6h)
- [ ] 1.1 Robustness curves (20h)

### Week 2 (30 hours): Statistical + Baselines
- [ ] 1.4 Statistical rigour (8h)
- [ ] 2.1 Threshold sensitivity (10h)
- [ ] 2.3 CoT baseline comparison (6h)
- [ ] 2.2 Complete BCC annotation (4h)

### Week 3 (25 hours): Polish + Theory
- [ ] 2.4 SABLE formal properties (10h)
- [ ] 3.3 Literature gap analysis (4h)
- [ ] 3.4 Figure improvements (5h)
- [ ] 3.1 Reproducibility infrastructure (6h)

### Week 4 (20 hours): Write-up Integration
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

## What NOT To Do (Diminishing Returns)

- Don't add more rules beyond 8 — diminishing returns for dissertation
- Don't build a production deployment pipeline — out of scope
- Don't fine-tune VLMs — too much effort for MSc timeline
- Don't pursue multi-council without a partner — high coordination cost
- Don't over-engineer the dashboard — CLI is sufficient for evaluation
