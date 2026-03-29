# PlanProof — Research-Oriented Ablation & Experiment Ideas

> **Purpose:** Concrete ideas for making the ablation study more rigorous and novel. Ranked by research impact and feasibility. Reference in dissertation methodology chapter.
> **Last updated:** 2026-03-29

---

## Current State: What the Ablation Measures

The ablation runner feeds ground-truth entities (confidence=1.0) directly into the reasoning pipeline. This measures the **reasoning layer under ideal conditions** — perfect extraction, no OCR errors, no misattributed values.

**Answered:** "Given flawless evidence, does the architecture help?"
**Not answered:** "Given realistic, noisy extraction, does the architecture help?"

---

## Tier 1: High Impact, Feasible Now

### A. Extraction-Quality Ablation (Noisy Oracle) ★

Instead of confidence=1.0, inject synthetic noise into ground truth entities to simulate real extraction errors. Creates a second experimental axis.

**Noise types to inject:**
- Value perturbation: building_height = 7.5 → 7.8 (±5% Gaussian)
- Attribute misattribution: swap building_height ↔ rear_garden_depth
- Source misclassification: DRAWING entity labelled as FORM
- Missing entities: randomly drop 10–30% of entities
- Confidence degradation: set confidence to 0.6–0.9 (now gating actually matters)

**Why novel:** No existing planning compliance paper tests how their system degrades under extraction noise. Produces robustness curves — publishable and novel.

**Implementation:** Add a `NoisyEntityTransformer` that takes oracle entities and applies parameterised degradation profiles. ~2-3 hours.

### B. Cross-Interaction Ablation (Pairwise Component Interactions)

Currently each ablation removes one component. But components might interact — gating might only matter when assessability is also active.

2-factor design:
```
                    Confidence Gating
                    ON          OFF
Assessability ON    Full        Ablation C
Assessability OFF   Ablation D   New: C+D off
```

Compute interaction effects: does loss(C+D) > loss(C) + loss(D)? If yes → synergy between gating and assessability. Standard factorial experimental design — rigorous and publishable.

**Implementation:** Add one new ablation config (C+D both off). ~1 hour.

### C. Sensitivity Analysis on Confidence Thresholds

Sweep thresholds from 0.3 to 0.95 in 0.05 increments:

```
Threshold  │ Precision  Recall  F2    Automation Rate
───────────┼──────────────────────────────────────────
   0.30    │  0.60      0.95    0.85     0.92
   0.50    │  0.72      0.88    0.84     0.85
   0.70    │  0.85      0.75    0.78     0.71   ← current
   0.90    │  0.95      0.40    0.48     0.45
```

Produces a precision-recall operating curve parameterised by confidence threshold. Shows the tradeoff explicitly and recommends optimal operating point.

**Implementation:** Loop in the ablation runner. ~2 hours.

---

## Tier 2: Higher Novelty, More Effort

### D. Extraction → Reasoning Error Propagation Analysis ★★

Run actual LLM/VLM extraction on synthetic PDFs (not oracle), compare extracted entities to ground truth, then measure how extraction errors propagate through reasoning:

```
Extraction Error Type    │ Without Assessability  │ With Assessability
─────────────────────────┼────────────────────────┼─────────────────────
Wrong value (7.5→8.2)    │ False PASS → dangerous │ Still PASS (close)
Missing attribute        │ False FAIL             │ NOT_ASSESSABLE ← caught!
Source misattribution    │ False FAIL             │ NOT_ASSESSABLE ← caught!
Low confidence (0.4)     │ Used anyway → risky    │ Filtered → NOT_ASSESSABLE
```

**Why novel:** Directly demonstrates the safety argument for assessability — it catches extraction errors that would otherwise become silent failures. Most compelling research result possible.

**Implementation:** Run full pipeline on synthetic PDFs (already proven working). ~3-4 hours + ~$2 API cost.

### E. NOT_ASSESSABLE as Information-Theoretic Signal

Measure the information gain of NOT_ASSESSABLE:
- H_binary = entropy of {PASS, FAIL} verdicts alone
- H_ternary = entropy of {PASS, FAIL, NOT_ASSESSABLE} verdicts
- Compute: "Of rules that were NOT_ASSESSABLE, what fraction would have been incorrectly classified as FAIL if forced to decide?" → **false conviction rate**

**Why novel:** No existing compliance system quantifies the value of "I don't know" as a signal.

### F. Per-Rule Difficulty Stratification

Stratify ablation results by rule complexity:

```
Rule Category    │ Naive BL  │ Full System  │ Δ (improvement)
─────────────────┼───────────┼──────────────┼─────────────────
Simple numeric   │ 0.85 F2   │ 0.92 F2      │ +0.07
Cross-document   │ 0.45 F2   │ 0.78 F2      │ +0.33
Missing evidence │ 0.00 F2   │ 0.65 F2      │ +0.65
```

Shows architecture's value is non-uniform — matters most for complex multi-source rules.

---

## Recommended Priority for 2-Week Sprint

| Priority | Idea | Effort | Research Value |
|----------|------|--------|---------------|
| 1 | A. Noisy Oracle | 2-3 hours | High — robustness curves |
| 2 | C. Threshold Sweep | 2 hours | High — operating curve |
| 3 | D. Error Propagation | 3-4 hours + $2 | Highest — safety argument |
| 4 | B. Pairwise Interaction | 1 hour | Medium — interaction effects |
| 5 | F. Rule Stratification | 1 hour | Medium — nuanced analysis |
| 6 | E. Information-Theoretic | 2 hours | Medium — novel framing |

---

## Key Finding Already Discovered

**Strong baseline (CoT) performs worse than naive baseline.**

Plain English: Adding more thinking to an LLM without the right framework makes things worse. The careful LLM reviewer confuses "I can't find evidence" with "it's wrong." The assessability engine solves this by explicitly separating "insufficient evidence" from "violation detected."

This finding alone is publishable and directly supports the dissertation thesis.
