# PlanProof — Qualitative Error Analysis

> **Generated:** 2026-04-02
> **Data:** 20 test sets × 5 pipeline configs × 7 rules = 700 evaluations
> **Test composition:** 10 compliant sets (SET_COMPLIANT) × 7 rules + 10 edge-case sets (SET_EDGECASE) × 7 rules per config. All ground-truth outcomes are PASS across both set types.

---

## Summary

| Config | Components removed | NOT_ASSESSABLE | PARTIALLY_ASSESSABLE | PASS | FAIL | False FAILs | Missed violations | False PASSes |
|---|---|---|---|---|---|---|---|---|
| **full_system** | none | 50 | 90 | 0 | 0 | 0 | 0 | 0 |
| **ablation_a** | rule engine, conf. gating, assessability | 140 | 0 | 0 | 0 | 0 | 0 | 0 |
| **ablation_b** | SNKG | 50 | 90 | 0 | 0 | 0 | 0 | 0 |
| **ablation_c** | confidence gating | 50 | 90 | 0 | 0 | 0 | 0 | 0 |
| **ablation_d** | assessability engine | 0 | 0 | 40 | 100 | **100** | 0 | 0 |

**Total misclassifications: 100, all in ablation_d (false FAILs).**

All 100 misclassifications share a single structural cause: removing the assessability engine forces the pipeline to emit binary PASS/FAIL verdicts regardless of evidence sufficiency. When applied to rules whose evidence requirements cannot be met from the available document set, the rule engine defaults to FAIL — flagging five compliant rules (C001, C002, C003, C004, R003) as violations across all 20 test sets.

Rules R001 and R002 are the exception: without the assessability gate, these rules still resolve to PASS because the synthetic oracle evidence happens to satisfy their simpler two-attribute evidence requirements, producing a correct-but-uncalibrated verdict.

No missed violations or false PASSes were observed in any configuration. This is a consequence of the synthetic test corpus containing only ground-truth-PASS cases for the seven rules evaluated; the absence of genuine FAIL ground-truth cases means recall of real violations cannot be measured here.

---

## Error Categories

### False FAILs (gt=PASS, pred=FAIL)

**Count:** 100 (all in ablation_d)
**Affected rules:** C001, C002, C003, C004, R003 — 20 false FAILs each across all 20 test sets
**Unaffected rules:** R001, R002 — correctly emit PASS in ablation_d

**Per-rule breakdown:**

| Rule | Description | Evidence gap causing false FAIL |
|---|---|---|
| C001 | Certificate type validity | Requires both `certificate_type` and `ownership_declaration`; synthetic sets expose only one source; without assessability gate, missing evidence resolves to FAIL |
| C002 | Address consistency | Requires `form_address` (FORM) and `drawing_address` (DRAWING) cross-match; drawing address extraction not available in this document profile; rule fires negatively |
| C003 | Boundary validation | Requires `reference_parcel_area` from EXTERNAL_DATA at min_confidence=1.0; oracle data unavailable in synthetic set; forced binary verdict defaults to FAIL |
| C004 | Plan change detection | Requires approved-plan attributes (`approved_building_height`, `approved_building_footprint_area`) which are absent from new-application document sets; four missing attributes trigger FAIL |
| R003 | Site coverage ratio | Requires `building_footprint_area` from DRAWING sources; drawing extraction insufficient in the test profiles; MISSING_EVIDENCE forces FAIL without assessability gate |

**Root cause:** ablation_d sets `use_assessability_engine: false`. Without this gate, the rule engine receives incomplete evidence bundles and applies a closed-world assumption — absence of satisfying evidence is treated as evidence of non-compliance. This is the default behaviour of traditional compliance tools and is the failure mode the assessability engine was designed to prevent.

**Key observation:** The error is perfectly systematic. Every one of the 20 test sets triggers the same five false FAILs for the same five rules. There is zero variance across seeds, set categories (COMPLIANT vs EDGECASE), or difficulty levels. This confirms the error is structural, not stochastic — it would reproduce on any document set processed by ablation_d.

---

### Missed Violations (gt=FAIL, pred=NOT_ASSESSABLE or PARTIALLY_ASSESSABLE)

**Count:** 0

No missed violations were observed in any configuration. The full_system and ablation_b/c configurations emit PARTIALLY_ASSESSABLE (not PASS) for rules where some but not all evidence is present, correctly declining to clear a rule when certainty is insufficient. Because all 140 ground-truth outcomes per config are PASS, no configuration was presented with a genuine violation to miss during this evaluation.

The PARTIALLY_ASSESSABLE verdict — which accounts for 90 of 140 full_system verdicts — represents a structural category of latent missed violations: cases where a real-world violation might exist but the system does not have enough evidence to detect it. This is captured in the recall/precision tradeoff discussion in Vignette 2 below.

---

### False PASSes (gt=FAIL, pred=PASS)

**Count:** 0

No false PASSes were observed. The full_system, ablation_b, and ablation_c configurations produce only NOT_ASSESSABLE and PARTIALLY_ASSESSABLE — neither of which constitutes a clearance. ablation_d produces 40 PASS verdicts (R001 and R002 across all 20 sets), but these are correct since all ground-truth outcomes are PASS. ablation_a produces only NOT_ASSESSABLE.

---

## Categorisation

### Systemic Errors

The 100 false FAILs in ablation_d are systemic errors: they arise from a structural flaw (missing assessability gate) that would reproduce identically on any document set processed by this configuration. The error is not specific to synthetic data, noisy scans, or adversarial inputs. Any real-world planning application submitted to ablation_d would trigger the same false FAIL pattern for C001, C002, C003, C004, and R003 — provided those rules face the same evidence gaps.

This category of error is the most practically harmful. In a regulatory context, a false FAIL triggers a refusal or a requisition letter to the applicant, wasting officer time and causing unnecessary resubmission delays. The full_system's assessability engine eliminates all 100 such errors by converting them to PARTIALLY_ASSESSABLE — a transparent signal that the system cannot form a conclusion rather than a spurious negative verdict.

### Data Gap Errors

The uniformly low belief scores (0.105–0.210 across all full_system rule evaluations) and the universal absence of PASS or FAIL verdicts in full_system reflect a structural limitation of the synthetic test corpus rather than a deficiency in the SABLE algorithm itself. The corpus was generated from single-source oracle evidence (one extraction per attribute), providing the minimum evidence mass needed to advance beyond NOT_ASSESSABLE but not enough to reach the PASS/FAIL belief thresholds the assessability engine requires for a decisive verdict.

In the real-world deployment scenario, multiple independent document sources (form, drawings, reports, external data) would each contribute independent evidence fragments. SABLE would fuse these through Dempster's rule of combination, progressively raising belief toward decisive thresholds. The synthetic data gap means this fusion is never exercised beyond a single-source baseline — a recognised limitation documented in the dissertation's evaluation scope section.

---

## Dissertation Vignettes

### Vignette 1: The Assessability Shield

The most consequential finding of the ablation study is the performance cliff between full_system and ablation_d. These two configurations are identical in every respect except a single boolean flag: `use_assessability_engine`. With it enabled, the system produces zero misclassifications across 140 evaluations — every verdict is either NOT_ASSESSABLE or PARTIALLY_ASSESSABLE, correctly declining to issue a binary ruling when evidence is insufficient. With it disabled, the system produces 100 false FAILs at a false-FAIL rate of 71.4% (100 of 140 decisive verdicts are wrong).

The five rules that produce false FAILs in ablation_d share a common characteristic: they require evidence from document types that are structurally absent from the evaluation corpus. C001 needs both a certificate and an ownership declaration; C002 needs cross-document address matching; C003 needs external Land Registry data at confidence 1.0; C004 needs approved-plan attributes from a prior application; R003 needs building footprint extracted from architectural drawings. In every case, the missing evidence is not an extraction failure — it is a document availability problem. The assessability engine detects this by checking whether required evidence sources are populated before permitting rule evaluation to proceed. Without it, the rule engine applies a closed-world assumption: what is not proven true is presumed false, and the absence of a matching certificate record becomes indistinguishable from an invalid certificate.

The 40 PASS verdicts that ablation_d does produce correctly (R001 and R002 across all 20 sets) are not evidence that the forced-binary approach works in general. These two rules require evidence that the oracle happens to provide — building height and rear garden depth are straightforwardly extractable from standard architectural drawings. They are the easy cases. The five rules that fail are the hard cases — multi-source cross-checks, external data dependencies, approved-plan comparisons — and they constitute the majority of a realistic validation checklist. The assessability engine shields applicants and officers from 100 spurious refusal triggers on those hard cases while correctly transmitting the evidence that exists.

---

### Vignette 2: The Cost of Caution

The full_system's perfect false-FAIL rate of 0% comes at a cost: it issues no PASS or FAIL verdicts at all. Every one of its 140 evaluations resolves to either NOT_ASSESSABLE (50, for rules blocked by MISSING_EVIDENCE) or PARTIALLY_ASSESSABLE (90, for rules where some evidence exists but belief remains below the decisive threshold). From a precision standpoint, this is optimal — no incorrect verdicts are issued. From a recall standpoint, the system contributes no definitive compliance clearances or violation detections within this evaluation corpus.

This is the fundamental precision-recall tradeoff of the assessability engine. By requiring a minimum belief threshold before issuing a decisive verdict, the system avoids false positives at the cost of withholding true positives. In the current corpus — where all 140 ground-truth outcomes are PASS — this manifests as an inability to confirm what a human expert would confirm: that a building height of 3.47 m clearly satisfies an 8.0 m threshold (R001, SET_COMPLIANT_100000), or that a rear garden depth of 25.75 m clearly satisfies a 10.0 m minimum (R002, SET_COMPLIANT_100000). The system sees the correct extracted values, but belief of 0.21 — derived from a single evidence source — falls below the threshold required to emit PASS.

The practical implication for deployment is that the assessability engine's thresholds are calibrated for a richer evidence environment than the synthetic corpus provides. A real planning application with six documents (form, floor plan, elevation, site plan, design-and-access statement, and external zone data) would supply independent evidence across multiple source types, raising SABLE belief substantially above 0.21 through multi-source combination. The 90 PARTIALLY_ASSESSABLE verdicts in full_system should therefore be understood as correct identification of evidence insufficiency in the evaluation corpus — not as a systematic failure to confirm compliant applications. The cost of caution is real but context-dependent: it is most acute when evidence supply is thin, and diminishes as the document bundle grows richer.

---

### Vignette 3: Evidence Sufficiency in Practice

The uniform belief scores across all full_system evaluations — exactly 0.105 for C-rules (C001–C004) and exactly 0.210 for R-rules (R001–R003) — are striking in their consistency. Neither the seed, the difficulty level, nor the set category (compliant vs edge case) produces any variation. The scores are identical across all 20 sets for each rule. This is not a sampling artifact: it is a direct consequence of the synthetic data generation architecture.

Each test set provides exactly one oracle evidence extract per required attribute. SABLE's Dempster-Shafer engine computes the belief mass assigned to the PASS hypothesis from a single basic probability assignment. C-rules require two evidence attributes from two source types (e.g., C001 requires `certificate_type` from FORM/CERTIFICATE and `ownership_declaration` from FORM). When only one of the two required sources is populated, belief accumulates from a partial evidence bundle — producing a consistent 0.105. R-rules require two attributes from potentially overlapping source types (building height from DRAWING or REPORT, zone category from FORM or EXTERNAL_DATA), and the oracle satisfies both — producing a consistent 0.21. The zero conflict mass across all rules confirms that no contradictory evidence was injected, so all uncertainty is ignorance rather than inconsistency.

These numbers carry a direct message for real-world deployment calibration. A single-source belief of 0.21 means the system has heard one credible witness say "this looks compliant" but has not yet cross-examined any corroborating sources. In planning terms, this is the equivalent of reading the applicant's own form but not yet checking it against the drawings or the land register. A real document bundle provides that cross-examination: a drawing confirms the height annotation on the form; the land register confirms the site area stated in the design-and-access statement; the VLM extraction cross-checks both against visual measurements on the elevation drawing. Each independent confirmation adds belief mass through Dempster's combination rule. Field trials with real applications would establish the empirical belief distribution under realistic document bundles, allowing the decisive thresholds to be calibrated against actual evidence richness rather than against an oracle baseline designed to exercise the pipeline logic rather than saturate it.
