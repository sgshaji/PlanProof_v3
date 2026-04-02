# Phase 8c: Extraction Evaluation & Error Attribution — Design Spec

> **Date:** 2026-04-02
> **Status:** Approved
> **Goal:** Measure extraction accuracy on synthetic and real data, improve prompts in one iteration, feed real extractions into reasoning for error attribution, and compare SABLE beliefs between oracle and real extraction.

---

## 1. Extraction Accuracy Metrics Module

**File:** `src/planproof/evaluation/extraction_metrics.py`

Two-level entity matching:

### Level 1: Entity Recall & Precision (attribute match)
- Match predicted `ExtractedEntity` to GT extractions by `attribute` field (case-insensitive, strip whitespace).
- **Recall** = matched GT entities / total GT entities (per-attribute and aggregated).
- **Precision** = matched predicted entities / total predicted entities.
- An extracted entity "matches" a GT entity if `predicted.attribute == gt.attribute` (after normalisation).

### Level 2: Value Accuracy (of matched entities)
- For matched entity pairs, check if the extracted value is correct:
  - **Numeric**: within ±10% of GT value (or ±0.5 absolute for small values < 5.0).
  - **String**: fuzzy match ratio ≥ 0.85 (using difflib.SequenceMatcher or rapidfuzz if available).
  - **Categorical**: exact case-insensitive match.
- **Value accuracy** = correct values / total matched entities.

### Aggregation
- Per-attribute metrics (e.g., building_height recall, building_height value accuracy).
- Per-document-type metrics (FORM vs DRAWING).
- Micro-averaged totals across all test sets.

### Data Structures

```
ExtractionMatch:
    gt_attribute: str
    gt_value: Any
    predicted_attribute: str | None  # None = missed (FN)
    predicted_value: Any | None
    matched: bool           # attribute found
    value_correct: bool     # value within tolerance
    doc_type: str
    set_id: str

ExtractionEvalResult:
    set_id: str
    matches: list[ExtractionMatch]
    recall: float
    precision: float
    value_accuracy: float
    per_attribute: dict[str, dict[str, float]]  # attribute -> {recall, precision, value_accuracy}
    per_doc_type: dict[str, dict[str, float]]   # doc_type -> {recall, precision, value_accuracy}
```

---

## 2. Extraction Runner Script

**File:** `scripts/run_extraction_eval.py`

### Test Set Selection
- 5 synthetic test sets: 2 compliant, 2 non-compliant, 1 edge-case.
- Deterministic selection: first 2 from each category by seed order, first 1 from edge_case.
- Source: `data/synthetic_diverse/`

### Execution Flow
1. For each test set, locate the generated PDF/PNG documents.
2. Run the classification step (RuleBasedClassifier) to get doc types.
3. For FORM documents: run PdfPlumber text extraction → LLM entity extraction (Groq).
4. For DRAWING documents: run VLM spatial extraction (GPT-4o zero-shot).
5. Collect all `ExtractedEntity` objects.
6. Load `ground_truth.json` and extract the GT entity list from `documents[].extractions[]`.
7. Run two-level matching (extraction_metrics module).
8. Save results to `data/results/extraction/{set_id}.json`.

### Output Format
```json
{
    "set_id": "SET_COMPLIANT_42000",
    "version": "v1",
    "predicted_entities": [...],
    "gt_entities": [...],
    "matches": [...],
    "metrics": {
        "recall": 0.75,
        "precision": 0.80,
        "value_accuracy": 0.60,
        "per_attribute": {...},
        "per_doc_type": {...}
    }
}
```

### CLI
```bash
python scripts/run_extraction_eval.py --version v1 --data-dir data/synthetic_diverse --output-dir data/results/extraction
python scripts/run_extraction_eval.py --version v2 --data-dir data/synthetic_diverse --output-dir data/results/extraction
```

---

## 3. Prompt Improvement Iteration (v1 → v2)

### Process (capped at one iteration)
1. Run v1 extraction, analyse results.
2. Categorise extraction failures:
   - **Missed attribute**: GT has it, extractor didn't return it.
   - **Wrong value**: Attribute matched but value outside tolerance.
   - **Hallucinated entity**: Extractor returned attribute not in GT.
   - **Wrong unit**: Value correct but unit incorrect (e.g., "feet" instead of "metres").
3. Identify top 2-3 prompt issues from failure patterns.
4. Update prompt templates in `configs/prompts/` with targeted fixes:
   - Add missing attributes to extraction target lists.
   - Clarify unit expectations.
   - Add examples for commonly missed patterns.
5. Re-run extraction as v2 on the same 5 sets.
6. Compute delta: v1 metrics vs v2 metrics.

### Deliverable
- Prompt diff (what changed between v1 and v2).
- Before/after metrics table.
- Dissertation figure: grouped bar chart showing v1 vs v2 recall and value accuracy per attribute.

---

## 4. BCC Annotation Helper

**File:** `scripts/annotate_bcc.py`

### Purpose
Guide the user through manually annotating 3 BCC application sets with ground truth extractions.

### BCC Set Selection
- Select 3 sets from `data/anonymised/` with the most/clearest drawings.
- The script lists available sets and their document counts, then lets the user pick 3.

### Annotation Flow (per document)
1. Script opens/displays the document path.
2. For each rule attribute (building_height, rear_garden_depth, site_coverage, etc.), prompt:
   - "Is [attribute] visible in this document? (y/n/skip)"
   - If yes: "What is the value?" → "What unit?" → "Which page?"
3. Save annotations to `data/annotated/{bcc_set_id}/ground_truth.json` in the same format as synthetic GT.
4. Print summary of what was annotated.

### Output Format
Same as synthetic `ground_truth.json` but with:
- `source: "manual_annotation"` in metadata
- Only `documents[].extractions[]` populated (no `values[]` or `rule_verdicts[]` — those require domain knowledge about compliance thresholds)

### CLI
```bash
python scripts/annotate_bcc.py --data-dir data/anonymised --output-dir data/annotated
```

---

## 5. Real Extraction Ablation & Error Attribution

### Real Extraction Ablation
- Take the v2 extracted entities from the 5 synthetic sets.
- Feed them into the reasoning pipeline (same as ablation runner but with real entities instead of GT).
- Run full_system config: normalisation → reconciliation → confidence gating → assessability (SABLE) → rule evaluation.
- Save results to `data/results/extraction_ablation/`.

### Error Attribution
Compare oracle results (Phase 8a `data/results/full_system/`) against real extraction results (`data/results/extraction_ablation/`) for the same 5 test sets:

| Oracle Verdict | Real Verdict | Category |
|---|---|---|
| Correct | Correct | End-to-end success |
| Correct | Wrong | **Extraction failure** — correct reasoning on wrong input |
| Wrong | Wrong | **Reasoning failure** — extraction doesn't matter |
| Wrong | Correct | Serendipitous — noisy extraction accidentally helped |

Count and categorise all cases.

### SABLE Belief Comparison
For each (rule, set) pair present in both oracle and real results:
- Extract oracle belief and real-extraction belief.
- Compute mean belief drop: `oracle_belief - real_belief`.
- Show that SABLE responds to degraded evidence quality (beliefs should drop when extraction is imperfect).

---

## 6. BCC Extraction Evaluation (Qualitative)

- Run extraction on the 3 annotated BCC sets.
- Compare against manual GT annotations.
- **Qualitative analysis only** — small N (3 sets), no statistical claims.
- Report: which attributes were extractable from real architectural drawings, what the dominant failure modes are, how real-world extraction differs from synthetic.

---

## 7. Notebook Visualizations (4 figures)

Added to `notebooks/ablation_analysis.ipynb` under "## Extraction Evaluation":

1. **Extraction accuracy grouped bar** — per-attribute recall and value accuracy, grouped by v1/v2. `figures/extraction_accuracy.png`
2. **v1 vs v2 delta chart** — improvement per attribute after prompt tuning. `figures/extraction_v1_v2_delta.png`
3. **Error attribution bar** — stacked bar: extraction failures vs reasoning failures vs end-to-end success. `figures/error_attribution.png`
4. **SABLE belief comparison** — paired box plot: oracle beliefs vs real-extraction beliefs per rule. `figures/sable_oracle_vs_real.png`

All at 300 DPI, dissertation-quality styling consistent with Phase 8a figures.

---

## 8. Documentation

- `docs/EXTRACTION_ERROR_ATTRIBUTION.md` — Full error attribution analysis with categorisation, SABLE comparison, and dissertation narratives.
- Update `docs/EXECUTION_STATUS.md` — Mark Phase 8c complete.
- Update `docs/PROJECT_LOG.md` — Add Phase 8c entry.

---

## Dependencies

- Groq API key (for LLM extraction on FORMs — rate limited ~10-15 sets/day)
- OpenAI API key (for GPT-4o VLM extraction on DRAWINGs — ~$1-2 for 5 sets)
- pdfplumber (already installed)
- sentence-transformers (already installed, for SABLE)
- difflib or rapidfuzz (for fuzzy string matching in value accuracy)

---

## Out of Scope

- Multiple prompt improvement iterations (capped at one: v1 → v2)
- Bounding box IoU metrics (extractors don't reliably return bboxes)
- Confidence calibration (hardcoded confidence scores)
- Full annotation of all 10 BCC sets (3 only)
- Extraction on real BCC forms (not available — drawings only)

---

## Success Criteria

1. Extraction metrics module produces recall, precision, value accuracy per attribute and per doc type
2. v1 extraction results saved for at least 5 synthetic test sets
3. At least one measurable improvement in v2 vs v1 (recall or value accuracy)
4. Error attribution categorises all verdict discrepancies between oracle and real extraction
5. SABLE belief comparison shows beliefs decrease with real (imperfect) extraction vs oracle
6. 3 BCC sets annotated and extraction evaluated qualitatively
7. 4 new figures in notebook at 300 DPI
8. All tests pass, ruff clean, mypy --strict clean
