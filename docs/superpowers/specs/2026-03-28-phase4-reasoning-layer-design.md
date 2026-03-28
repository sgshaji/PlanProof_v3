# Phase 4: Reasoning Layer (M6-M9) — Design Spec

**Date:** 2026-03-28 | **Depends on:** Phase 3 (M5 SNKG)

## Goal

The intellectual core of PlanProof. Given normalised entities and a populated knowledge graph, produce per-rule verdicts (PASS / FAIL / NOT_ASSESSABLE) with full provenance.

## Four Modules

### M6: Evidence Reconciliation
- `PairwiseReconciler` implementing `Reconciler` Protocol
- For each attribute: gather all entities, pairwise compare values within configurable tolerance
- Outputs: AGREED (within tolerance), CONFLICTING (beyond tolerance), SINGLE_SOURCE, MISSING
- Output: `ReconciledEvidence` per attribute

### M7: Confidence Gating
- `ThresholdConfidenceGate` implementing `ConfidenceGate` Protocol
- Loads thresholds from `configs/confidence_thresholds.yaml` (per extraction_method × entity_type)
- `is_trustworthy(entity)`: entity.confidence >= threshold
- `filter_trusted(entities)`: return only trustworthy entities

### M8: Assessability Engine (core novelty)
- `DefaultAssessabilityEvaluator` implementing `AssessabilityEvaluator` Protocol
- For each rule: check required_evidence from rule YAML against available entities
  - Has acceptable source? Has sufficient confidence? Spatial grounding verified?
  - Run reconciliation on gathered evidence
- Decision: all met + no conflicts → ASSESSABLE, else NOT_ASSESSABLE with blocking reason
- Output: `AssessabilityResult` per rule

### M9: Rule Engine
- Implement existing evaluator stubs (NumericThresholdEvaluator, RatioThresholdEvaluator, FuzzyMatchEvaluator, EnumCheckEvaluator, etc.)
- `RuleEvaluationStep` loads rules from YAML, only evaluates ASSESSABLE rules
- Deterministic: no LLM in evaluation path
- Output: `RuleVerdict` per rule

## Files

**New:** `reasoning/reconciliation.py`, `reasoning/confidence.py`, `reasoning/assessability.py`
**Modify:** All evaluator stubs in `reasoning/evaluators/`, all 4 pipeline step stubs, `bootstrap.py`
**Test target:** 90% coverage (research contribution)

## Key decisions
- Pairwise comparison only for reconciliation (proposal scoping decision)
- Confidence thresholds from YAML config, empirically calibratable
- Rule evaluation only for ASSESSABLE rules — NOT_ASSESSABLE skips evaluation
- Tier 1 rules first: R001 (max height), R002 (min rear garden), R003 (max site coverage)
