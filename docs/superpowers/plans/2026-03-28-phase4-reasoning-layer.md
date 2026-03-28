# Phase 4: Reasoning Layer (M6-M9) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the reasoning layer — evidence reconciliation, confidence gating, assessability engine, and rule evaluation — producing per-rule PASS/FAIL/NOT_ASSESSABLE verdicts.

**Architecture:** Four modules implementing existing Protocols. Reconciler resolves cross-source conflicts, ConfidenceGate filters low-trust entities, AssessabilityEvaluator determines if rules can be evaluated, RuleEngine produces verdicts for assessable rules only.

**Tech Stack:** Python 3.11+, pydantic, pyyaml, rapidfuzz (for fuzzy string matching in C2)

**Spec:** `docs/superpowers/specs/2026-03-28-phase4-reasoning-layer-design.md`

---

## File Structure

### New Files
- `src/planproof/reasoning/reconciliation.py` — `PairwiseReconciler` implementing `Reconciler` Protocol
- `src/planproof/reasoning/confidence.py` — `ThresholdConfidenceGate` implementing `ConfidenceGate` Protocol
- `src/planproof/reasoning/assessability.py` — `DefaultAssessabilityEvaluator` implementing `AssessabilityEvaluator` Protocol
- `tests/unit/reasoning/__init__.py`
- `tests/unit/reasoning/test_reconciliation.py`
- `tests/unit/reasoning/test_confidence.py`
- `tests/unit/reasoning/test_assessability.py`
- `tests/unit/reasoning/test_evaluators.py`
- `tests/unit/reasoning/test_pipeline_steps.py`
- `tests/integration/test_reasoning_pipeline.py`

### Modified Files
- `src/planproof/reasoning/evaluators/numeric_threshold.py` — implement evaluate()
- `src/planproof/reasoning/evaluators/ratio_threshold.py` — implement evaluate()
- `src/planproof/reasoning/evaluators/fuzzy_match.py` — implement evaluate()
- `src/planproof/reasoning/evaluators/enum_check.py` — implement evaluate()
- `src/planproof/reasoning/evaluators/numeric_tolerance.py` — implement evaluate()
- `src/planproof/reasoning/evaluators/attribute_diff.py` — implement evaluate()
- `src/planproof/pipeline/steps/reconciliation.py` — implement execute()
- `src/planproof/pipeline/steps/confidence_gating.py` — implement execute()
- `src/planproof/pipeline/steps/assessability.py` — implement execute()
- `src/planproof/pipeline/steps/rule_evaluation.py` — implement execute()
- `src/planproof/bootstrap.py` — wire concrete reasoning components, remove stubs

---

## Task 1: PairwiseReconciler (M6)

**Files:**
- Create: `src/planproof/reasoning/reconciliation.py`
- Create: `tests/unit/reasoning/test_reconciliation.py`

**What:** Implement `PairwiseReconciler` satisfying the `Reconciler` Protocol from `interfaces/reasoning.py`.

`reconcile(entities, attribute) -> ReconciledEvidence`:
- If no entities: return MISSING status
- If one entity: return SINGLE_SOURCE with that value as best_value
- If multiple: pairwise compare values. If all within configurable tolerance → AGREED (best_value = mean). If any pair beyond tolerance → CONFLICTING with conflict details.
- Tolerance configurable per attribute type (default: 0.5 for measurements, exact match for strings)

**Tests (90% coverage target):**
- Empty entities → MISSING
- Single entity → SINGLE_SOURCE with correct best_value
- Two agreeing values (within tolerance) → AGREED, best_value is mean
- Two conflicting values → CONFLICTING with details
- Multiple sources all agreeing → AGREED
- String attribute exact match
- String attribute mismatch → CONFLICTING
- Custom tolerance overrides default

- [ ] Write tests, implement, lint, typecheck, commit

---

## Task 2: ThresholdConfidenceGate (M7)

**Files:**
- Create: `src/planproof/reasoning/confidence.py`
- Create: `tests/unit/reasoning/test_confidence.py`

**What:** Implement `ThresholdConfidenceGate` satisfying the `ConfidenceGate` Protocol.

- Constructor takes thresholds dict (nested: `{extraction_method: {entity_type: float}}`)
- `is_trustworthy(entity)`: looks up threshold for entity's extraction_method and entity_type. Returns True if entity.confidence >= threshold. If no threshold configured, default to trustworthy.
- `filter_trusted(entities)`: return list of entities where is_trustworthy is True

Load thresholds from `configs/confidence_thresholds.yaml` (already exists with per-method/per-type values).

**Tests:**
- Entity above threshold → trustworthy
- Entity below threshold → not trustworthy
- Missing method/type in config → defaults to trustworthy
- filter_trusted removes low-confidence entities
- filter_trusted preserves high-confidence entities
- Empty entities → empty result

- [ ] Write tests, implement, lint, typecheck, commit

---

## Task 3: Implement rule evaluators (M9 — evaluator stubs)

**Files:**
- Modify: All 6 evaluator files in `src/planproof/reasoning/evaluators/`
- Create: `tests/unit/reasoning/test_evaluators.py`

**What:** Implement the `evaluate(evidence, params)` method in each evaluator stub.

**NumericThresholdEvaluator** (R001 max height, R002 min garden):
- Extract best_value from ReconciledEvidence
- Compare against params["threshold"] using params["operator"] ("<=" or ">=")
- Return PASS or FAIL RuleVerdict

**RatioThresholdEvaluator** (R003 site coverage):
- Compute ratio from evidence values
- Compare against threshold

**FuzzyMatchEvaluator** (C2 address consistency):
- Compare two string values using Levenshtein ratio
- PASS if ratio >= params["min_ratio"] (default 0.85)
- Add `rapidfuzz` as dependency in pyproject.toml

**EnumCheckEvaluator** (C1 certificate type):
- Check if value is in allowed enum set from params

**NumericToleranceEvaluator** (C3 boundary validation):
- Compare two numeric values, PASS if within ±tolerance%

**AttributeDiffEvaluator** (C4 plan change detection):
- Compare attributes between two document sets, flag differences beyond tolerance

**Tests:** At least 2 tests per evaluator (PASS case + FAIL case). Use realistic rule parameters from configs/rules/*.yaml.

- [ ] Write tests, implement all evaluators, lint, typecheck, commit

---

## Task 4: DefaultAssessabilityEvaluator (M8 — core novelty)

**Files:**
- Create: `src/planproof/reasoning/assessability.py`
- Create: `tests/unit/reasoning/test_assessability.py`

**What:** Implement `DefaultAssessabilityEvaluator` satisfying the `AssessabilityEvaluator` Protocol.

Dependencies (injected):
- `EvidenceProvider` — to query available evidence
- `ConfidenceGate` — to check if evidence is trustworthy
- `Reconciler` — to check for conflicts
- Rules loaded from YAML configs

`evaluate(rule_id) -> AssessabilityResult`:
1. Load the RuleConfig for this rule_id
2. For each required_evidence item in the rule:
   a. Query evidence provider for entities
   b. Filter by acceptable_sources (doc_type)
   c. Check confidence gating
   d. Check spatial_grounding if required
3. Run reconciliation on gathered evidence
4. Decision:
   - All requirements met + no conflicts → ASSESSABLE
   - Any requirement unmet → NOT_ASSESSABLE (blocking_reason=MISSING_EVIDENCE)
   - Low confidence entities → NOT_ASSESSABLE (blocking_reason=LOW_CONFIDENCE)
   - Conflicts detected → NOT_ASSESSABLE (blocking_reason=CONFLICTING_EVIDENCE)

**Tests (exhaustive — this is the research contribution):**
- All evidence present and trustworthy → ASSESSABLE
- Missing evidence for one requirement → NOT_ASSESSABLE with MISSING_EVIDENCE
- Evidence below confidence threshold → NOT_ASSESSABLE with LOW_CONFIDENCE
- Conflicting evidence → NOT_ASSESSABLE with CONFLICTING_EVIDENCE
- Multiple requirements, one missing → NOT_ASSESSABLE lists what's missing
- Rule with no required_evidence → ASSESSABLE (vacuously true)

- [ ] Write tests, implement, lint, typecheck, commit

---

## Task 5: Implement pipeline step stubs

**Files:**
- Modify: `src/planproof/pipeline/steps/reconciliation.py`
- Modify: `src/planproof/pipeline/steps/confidence_gating.py`
- Modify: `src/planproof/pipeline/steps/assessability.py`
- Modify: `src/planproof/pipeline/steps/rule_evaluation.py`
- Create: `tests/unit/reasoning/test_pipeline_steps.py`

**What:** Implement execute() for all four reasoning pipeline steps.

**ReconciliationStep.execute():**
- Get entities from context, get unique attributes (entity_type values)
- For each attribute, call reconciler.reconcile(entities_of_that_type, attribute)
- Store reconciled results in context (add "reconciled_evidence" key to PipelineContext if needed)

**ConfidenceGatingStep.execute():**
- Get entities from context
- Call gate.filter_trusted(entities)
- Replace context["entities"] with filtered list
- Log how many were removed

**AssessabilityStep.execute():**
- Get rule configs from context or load from rules dir
- For each rule, call evaluator.evaluate(rule_id)
- Store results in context["assessability_results"]
- Separate rules into assessable vs not_assessable lists

**RuleEvaluationStep.execute():**
- Load rules from YAML via RuleFactory
- Only evaluate rules that are ASSESSABLE (check context["assessability_results"])
- For each assessable rule: get reconciled evidence, call evaluator.evaluate(evidence, params)
- Store verdicts in context["verdicts"]

**Tests:** 2-3 tests per step covering happy path, empty input, and the key filtering logic.

- [ ] Write tests, implement all 4 steps, lint, typecheck, commit

---

## Task 6: Wire into bootstrap + update PipelineContext

**Files:**
- Modify: `src/planproof/bootstrap.py`
- Modify: `src/planproof/interfaces/pipeline.py` (add reconciled_evidence key if needed)
- Modify: `docs/EXECUTION_STATUS.md`

**What:**
- Import and wire `PairwiseReconciler`, `ThresholdConfidenceGate`, `DefaultAssessabilityEvaluator`
- Load confidence thresholds from YAML
- Replace remaining stubs (_StubReconciler, _StubGate, _StubAssessability) with concrete implementations
- Register steps conditionally based on ablation config
- Update EXECUTION_STATUS: Phase 4 → Complete
- Add `rapidfuzz` to pyproject.toml dependencies

- [ ] Wire, run full test suite, lint, typecheck, commit

---

## Task 7: Integration test — full reasoning pipeline

**Files:**
- Create: `tests/integration/test_reasoning_pipeline.py`

**What:** End-to-end test using synthetic data:
- Compliant set → all rules should be ASSESSABLE and PASS
- Non-compliant set → at least one FAIL
- Edge case set (missing evidence) → NOT_ASSESSABLE with correct blocking reasons

Use mocked SNKG (or FlatEvidenceProvider) to avoid Neo4j dependency. Feed ground truth entities directly.

- [ ] Write tests, run, commit

---

## Task 8: Final docs commit and push

- [ ] Commit spec + plan docs
- [ ] Push to GitHub
