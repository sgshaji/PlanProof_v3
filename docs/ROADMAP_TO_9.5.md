# PlanProof — Roadmap: Current State → 9.5/10

> **Created**: 2026-04-05
> **Current rating**: 7.5/10
> **Target**: 9.5/10
> **Estimated effort**: 2-3 days

---

## Current state (what's strong)

- SABLE reasoning layer validated: 297 evaluations, 9 rules, 7 evaluation types, ablation study
- Extraction validated on 9 real BCC forms: recall 93.3%, value accuracy 86.7%
- VLM extracts measurements from real BCC drawing PDFs (building_height, ridge_height, room_dimensions, site_area)
- Content-based classifier correctly routes forms vs drawings
- Comprehensive datagen: all 8 assessable rules produce PASS/FAIL verdicts

## What's missing (4 items, in priority order)

---

### 1. End-to-end real-data verdicts
**Impact: Critical — this alone takes it from 7.5 → 8.5**

The extraction pipeline works on real data. SABLE works on synthetic data. They have never been connected on real data. No real BCC application has ever produced a verdict through the full pipeline.

**What to do:** Take the 9 BCC applications → extract entities (LLM forms + VLM drawings) → feed into reconciliation → SABLE assessability → rule evaluation → produce verdicts. Even if only C001 (certificate type) and C002 (address consistency) fire, showing "Certificate A detected from real form, SABLE belief=0.87, verdict=PASS" on a real application transforms the dissertation from "components tested separately" to "system that works on real planning applications."

**Concrete steps:**
- Wire extracted entities from `run_extraction_eval.py` output into SABLE pipeline
- Run on 9 BCC applications
- Produce per-application verdict table: rule_id, extracted evidence, belief score, verdict
- This is the dissertation's demo result

**Effort:** 1 day

---

### 2. Real non-compliant examples
**Impact: High — addresses the "all PASS, no FAIL" weakness**

All 9 BCC applications are approved (PASS on all rules). FAIL detection is only validated on synthetic planted violations. An examiner will ask: "how do you know it detects real non-compliance?"

**What to do (two options):**

**(A) Obtain refused BCC applications** — BCC planning portal has applications with status "Refused" or "Withdrawn". If 5-10 can be obtained, run the full pipeline on them and show FAIL verdicts.

**(B) Perturbation-based evaluation** — take 5 real applications, modify one extracted value (e.g. change building_height from 7.5 to 12.0, exceeding the 8.0m threshold). Show SABLE correctly flips from PASS to FAIL. This is a legitimate evaluation technique if framed honestly: "FAIL detection evaluated via controlled perturbation of real extracted values."

**Dissertation framing:** "We evaluate FAIL detection via controlled perturbation of real extracted values, since refused applications were not available in our dataset. For each of 5 applications, we inject a single non-compliant value and verify the system correctly identifies the violation."

**Effort:** Half day (option B)

---

### 3. Extraction confidence calibration
**Impact: Medium-high — strengthens SABLE's theoretical foundation**

Confidence scores are hardcoded (ADDRESS=0.85, MEASUREMENT=0.80). SABLE uses these as inputs to Dempster-Shafer mass functions. If confidence is miscalibrated, belief scores are unreliable. An examiner will ask: "are your confidence scores empirically grounded?"

**What to do:** Produce a reliability diagram. For each entity type, compute: "when the system reports confidence=X, what fraction of extractions are actually correct?" Plot predicted confidence vs actual accuracy. If misaligned, recalibrate. If aligned, show the diagram and claim "empirically calibrated."

**Data available:** v1 extraction results (predicted values + ground truth) already have everything needed. One script, one figure.

**Effort:** Half day

---

### 4. Statistical significance on ablation
**Impact: Medium — standard practice that reviewers expect**

297 evaluations across 5 ablation configs, but no confidence intervals or statistical tests. An examiner could ask: "is the difference between full_system and ablation_a statistically significant or just noise?"

**What to do:** McNemar's test or paired bootstrap confidence intervals on ablation results. Show p-values for each ablation variant vs full_system. Report 95% confidence intervals on recall/precision differences.

**Effort:** Few hours (one script using scipy.stats)

---

## Summary

| # | Item | Rating impact | Effort | Dependency |
|---|------|--------------|--------|------------|
| 1 | End-to-end real-data verdicts | 7.5 → 8.5 | 1 day | Combined extraction eval (Groq reset) |
| 2 | Non-compliant perturbation eval | 8.5 → 9.0 | Half day | Item 1 |
| 3 | Confidence calibration diagram | 9.0 → 9.3 | Half day | Extraction results from item 1 |
| 4 | Statistical significance tests | 9.3 → 9.5 | Few hours | Existing ablation results |

Items 1-2 are the critical path. Items 3-4 are polish that push into top-tier territory.

---

## Prerequisite (before item 1)

**Combined extraction eval** — merge v1 LLM form extractions + v2_full VLM drawing extractions, OR re-run full eval after Groq daily token limit resets. This gives comprehensive extracted entities per application that feed into the end-to-end pipeline.
