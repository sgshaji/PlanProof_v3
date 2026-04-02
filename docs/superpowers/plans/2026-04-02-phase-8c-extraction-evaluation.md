# Phase 8c: Extraction Evaluation & Error Attribution — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure extraction accuracy on synthetic PDFs, improve prompts in one iteration, run real extractions through reasoning for error attribution, annotate 3 BCC sets, and compare SABLE beliefs between oracle and real extraction.

**Architecture:** Seven tasks in dependency order — (1) extraction metrics module, (2) extraction runner script, (3) run v1 extraction + analyse failures, (4) prompt improvement + run v2, (5) BCC annotation helper + annotate, (6) real extraction ablation + error attribution, (7) notebook visualizations + documentation. Tasks 1-2 are pure code. Tasks 3-4 require LLM/VLM API calls. Task 5 requires user interaction. Tasks 6-7 depend on 3-4 completing.

**Tech Stack:** Python 3.12, pytest, pydantic, Groq (llama-3.3-70b), OpenAI GPT-4o, pdfplumber, difflib, matplotlib, seaborn, ruff, mypy --strict.

---

## Task 1: Extraction Accuracy Metrics Module

**Files:**
- Create: `src/planproof/evaluation/extraction_metrics.py`
- Test: `tests/unit/evaluation/test_extraction_metrics.py`

- [ ] **Step 1: Write failing test — entity matching by attribute**

Create `tests/unit/evaluation/test_extraction_metrics.py`:

```python
"""Tests for extraction accuracy metrics."""
from __future__ import annotations

import pytest

from planproof.evaluation.extraction_metrics import (
    ExtractionMatch,
    ExtractionEvalResult,
    match_entities,
    compute_extraction_metrics,
)


class TestMatchEntities:
    def test_exact_attribute_match(self) -> None:
        """Predicted entity with same attribute matches GT."""
        gt = [{"attribute": "building_height", "value": 7.5, "entity_type": "MEASUREMENT"}]
        pred = [{"attribute": "building_height", "value": 7.5}]
        matches = match_entities(gt, pred)
        assert len(matches) == 1
        assert matches[0].matched is True
        assert matches[0].value_correct is True

    def test_case_insensitive_match(self) -> None:
        """Attribute matching is case-insensitive."""
        gt = [{"attribute": "Building_Height", "value": 7.5, "entity_type": "MEASUREMENT"}]
        pred = [{"attribute": "building_height", "value": 7.5}]
        matches = match_entities(gt, pred)
        assert matches[0].matched is True

    def test_missed_entity(self) -> None:
        """GT entity with no predicted match is a miss (FN)."""
        gt = [{"attribute": "building_height", "value": 7.5, "entity_type": "MEASUREMENT"}]
        pred = []
        matches = match_entities(gt, pred)
        assert len(matches) == 1
        assert matches[0].matched is False
        assert matches[0].predicted_value is None

    def test_hallucinated_entity(self) -> None:
        """Predicted entity with no GT match is a hallucination (FP)."""
        gt = []
        pred = [{"attribute": "roof_type", "value": "gable"}]
        matches = match_entities(gt, pred)
        assert len(matches) == 1
        assert matches[0].gt_attribute is None
        assert matches[0].matched is False

    def test_numeric_value_within_tolerance(self) -> None:
        """Value within ±10% is correct."""
        gt = [{"attribute": "building_height", "value": 10.0, "entity_type": "MEASUREMENT"}]
        pred = [{"attribute": "building_height", "value": 10.8}]  # 8% off
        matches = match_entities(gt, pred)
        assert matches[0].value_correct is True

    def test_numeric_value_outside_tolerance(self) -> None:
        """Value outside ±10% is incorrect."""
        gt = [{"attribute": "building_height", "value": 10.0, "entity_type": "MEASUREMENT"}]
        pred = [{"attribute": "building_height", "value": 12.0}]  # 20% off
        matches = match_entities(gt, pred)
        assert matches[0].matched is True
        assert matches[0].value_correct is False

    def test_small_value_absolute_tolerance(self) -> None:
        """For values < 5.0, use ±0.5 absolute tolerance."""
        gt = [{"attribute": "storeys", "value": 2.0, "entity_type": "MEASUREMENT"}]
        pred = [{"attribute": "storeys", "value": 2.4}]  # 0.4 off, within 0.5
        matches = match_entities(gt, pred)
        assert matches[0].value_correct is True

    def test_string_fuzzy_match(self) -> None:
        """String values match with ≥0.85 similarity."""
        gt = [{"attribute": "site_address", "value": "123 Example Street, B1 1AA", "entity_type": "ADDRESS"}]
        pred = [{"attribute": "site_address", "value": "123 Example St, B1 1AA"}]
        matches = match_entities(gt, pred)
        assert matches[0].value_correct is True

    def test_string_mismatch(self) -> None:
        """Completely different strings don't match."""
        gt = [{"attribute": "site_address", "value": "123 Example Street, B1 1AA", "entity_type": "ADDRESS"}]
        pred = [{"attribute": "site_address", "value": "456 Other Road, E1 2BB"}]
        matches = match_entities(gt, pred)
        assert matches[0].matched is True
        assert matches[0].value_correct is False


class TestComputeExtractionMetrics:
    def test_perfect_extraction(self) -> None:
        """All GT entities found with correct values."""
        gt = [
            {"attribute": "building_height", "value": 7.5, "entity_type": "MEASUREMENT"},
            {"attribute": "site_address", "value": "123 Street", "entity_type": "ADDRESS"},
        ]
        pred = [
            {"attribute": "building_height", "value": 7.5},
            {"attribute": "site_address", "value": "123 Street"},
        ]
        result = compute_extraction_metrics(gt, pred, set_id="test", doc_type="FORM")
        assert result.recall == pytest.approx(1.0)
        assert result.precision == pytest.approx(1.0)
        assert result.value_accuracy == pytest.approx(1.0)

    def test_partial_extraction(self) -> None:
        """Some GT entities missed."""
        gt = [
            {"attribute": "building_height", "value": 7.5, "entity_type": "MEASUREMENT"},
            {"attribute": "site_coverage", "value": 40.0, "entity_type": "MEASUREMENT"},
        ]
        pred = [
            {"attribute": "building_height", "value": 7.5},
        ]
        result = compute_extraction_metrics(gt, pred, set_id="test", doc_type="FORM")
        assert result.recall == pytest.approx(0.5)
        assert result.precision == pytest.approx(1.0)

    def test_empty_gt_and_pred(self) -> None:
        """Empty inputs produce zero metrics."""
        result = compute_extraction_metrics([], [], set_id="test", doc_type="FORM")
        assert result.recall == pytest.approx(0.0)
        assert result.precision == pytest.approx(0.0)

    def test_per_attribute_breakdown(self) -> None:
        """Per-attribute metrics are populated."""
        gt = [{"attribute": "building_height", "value": 7.5, "entity_type": "MEASUREMENT"}]
        pred = [{"attribute": "building_height", "value": 7.5}]
        result = compute_extraction_metrics(gt, pred, set_id="test", doc_type="FORM")
        assert "building_height" in result.per_attribute
        assert result.per_attribute["building_height"]["recall"] == pytest.approx(1.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/evaluation/test_extraction_metrics.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement extraction_metrics.py**

Create `src/planproof/evaluation/extraction_metrics.py`:

```python
"""Extraction accuracy metrics — entity matching and accuracy computation.

Two-level matching: (1) attribute name match (recall/precision), (2) value
correctness within tolerance (value accuracy). Supports numeric (±10% or ±0.5
for small values) and string (≥0.85 fuzzy ratio) comparisons.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any


@dataclass
class ExtractionMatch:
    """Result of matching one GT or predicted entity."""

    gt_attribute: str | None
    gt_value: Any
    predicted_attribute: str | None
    predicted_value: Any
    matched: bool
    value_correct: bool
    doc_type: str
    set_id: str


@dataclass
class ExtractionEvalResult:
    """Aggregated extraction metrics for one evaluation unit."""

    set_id: str
    doc_type: str
    matches: list[ExtractionMatch]
    recall: float
    precision: float
    value_accuracy: float
    per_attribute: dict[str, dict[str, float]] = field(default_factory=dict)


def _normalise_attr(attr: str) -> str:
    """Lowercase and strip whitespace for matching."""
    return attr.strip().lower()


def _is_numeric(value: Any) -> bool:
    """Check if a value can be treated as numeric."""
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        try:
            float(value)
            return True
        except ValueError:
            return False
    return False


def _numeric_match(gt_val: float, pred_val: float) -> bool:
    """Check if predicted numeric value is within tolerance of GT.

    ±10% relative tolerance, or ±0.5 absolute for values < 5.0.
    """
    if abs(gt_val) < 5.0:
        return abs(gt_val - pred_val) <= 0.5
    return abs(gt_val - pred_val) / abs(gt_val) <= 0.10


def _string_match(gt_val: str, pred_val: str) -> bool:
    """Check if predicted string is ≥0.85 similar to GT."""
    ratio = SequenceMatcher(None, gt_val.lower(), pred_val.lower()).ratio()
    return ratio >= 0.85


def _values_match(gt_value: Any, pred_value: Any) -> bool:
    """Check if a predicted value matches the GT value within tolerance."""
    if gt_value is None or pred_value is None:
        return gt_value is None and pred_value is None

    if _is_numeric(gt_value) and _is_numeric(pred_value):
        return _numeric_match(float(gt_value), float(pred_value))

    return _string_match(str(gt_value), str(pred_value))


def match_entities(
    gt_entities: list[dict[str, Any]],
    predicted_entities: list[dict[str, Any]],
    doc_type: str = "",
    set_id: str = "",
) -> list[ExtractionMatch]:
    """Match predicted entities against GT entities by attribute name.

    Returns one ExtractionMatch per GT entity (with matched/unmatched status)
    plus one per unmatched predicted entity (hallucinations).
    """
    matches: list[ExtractionMatch] = []

    # Index predicted by normalised attribute
    pred_by_attr: dict[str, dict[str, Any]] = {}
    pred_used: set[int] = set()
    for i, p in enumerate(predicted_entities):
        attr = _normalise_attr(p.get("attribute", ""))
        if attr and attr not in pred_by_attr:
            pred_by_attr[attr] = (i, p)  # type: ignore[assignment]

    # Match GT entities
    for gt in gt_entities:
        gt_attr = _normalise_attr(gt.get("attribute", ""))
        gt_val = gt.get("value")

        if gt_attr in pred_by_attr:
            idx, pred = pred_by_attr[gt_attr]  # type: ignore[misc]
            pred_used.add(idx)
            pred_val = pred.get("value")
            val_correct = _values_match(gt_val, pred_val)
            matches.append(ExtractionMatch(
                gt_attribute=gt_attr,
                gt_value=gt_val,
                predicted_attribute=gt_attr,
                predicted_value=pred_val,
                matched=True,
                value_correct=val_correct,
                doc_type=doc_type,
                set_id=set_id,
            ))
        else:
            matches.append(ExtractionMatch(
                gt_attribute=gt_attr,
                gt_value=gt_val,
                predicted_attribute=None,
                predicted_value=None,
                matched=False,
                value_correct=False,
                doc_type=doc_type,
                set_id=set_id,
            ))

    # Hallucinated entities (predicted but not in GT)
    for i, pred in enumerate(predicted_entities):
        if i not in pred_used:
            matches.append(ExtractionMatch(
                gt_attribute=None,
                gt_value=None,
                predicted_attribute=_normalise_attr(pred.get("attribute", "")),
                predicted_value=pred.get("value"),
                matched=False,
                value_correct=False,
                doc_type=doc_type,
                set_id=set_id,
            ))

    return matches


def compute_extraction_metrics(
    gt_entities: list[dict[str, Any]],
    predicted_entities: list[dict[str, Any]],
    set_id: str = "",
    doc_type: str = "",
) -> ExtractionEvalResult:
    """Compute recall, precision, and value accuracy from entity matching."""
    matches = match_entities(gt_entities, predicted_entities, doc_type, set_id)

    gt_count = sum(1 for m in matches if m.gt_attribute is not None)
    matched_count = sum(1 for m in matches if m.matched and m.gt_attribute is not None)
    pred_count = len(predicted_entities)
    value_correct_count = sum(1 for m in matches if m.value_correct)

    recall = matched_count / gt_count if gt_count > 0 else 0.0
    precision = matched_count / pred_count if pred_count > 0 else 0.0
    value_accuracy = value_correct_count / matched_count if matched_count > 0 else 0.0

    # Per-attribute breakdown
    per_attribute: dict[str, dict[str, float]] = {}
    attr_gt: dict[str, int] = {}
    attr_matched: dict[str, int] = {}
    attr_correct: dict[str, int] = {}

    for m in matches:
        if m.gt_attribute is not None:
            attr_gt[m.gt_attribute] = attr_gt.get(m.gt_attribute, 0) + 1
            if m.matched:
                attr_matched[m.gt_attribute] = attr_matched.get(m.gt_attribute, 0) + 1
                if m.value_correct:
                    attr_correct[m.gt_attribute] = attr_correct.get(m.gt_attribute, 0) + 1

    for attr in attr_gt:
        g = attr_gt[attr]
        m = attr_matched.get(attr, 0)
        c = attr_correct.get(attr, 0)
        per_attribute[attr] = {
            "recall": m / g if g > 0 else 0.0,
            "precision": 1.0 if m > 0 else 0.0,  # simplified: one pred per attr
            "value_accuracy": c / m if m > 0 else 0.0,
        }

    return ExtractionEvalResult(
        set_id=set_id,
        doc_type=doc_type,
        matches=matches,
        recall=recall,
        precision=precision,
        value_accuracy=value_accuracy,
        per_attribute=per_attribute,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/evaluation/test_extraction_metrics.py -v`
Expected: All pass.

- [ ] **Step 5: Run full test suite**

Run: `pytest -x -q`
Expected: All pass, no regressions.

- [ ] **Step 6: Commit**

```bash
git add src/planproof/evaluation/extraction_metrics.py tests/unit/evaluation/test_extraction_metrics.py
git commit -m "feat(eval): add extraction accuracy metrics — entity matching, recall, precision, value accuracy"
```

---

## Task 2: Extraction Runner Script

**Files:**
- Create: `scripts/run_extraction_eval.py`

- [ ] **Step 1: Create the extraction runner script**

Create `scripts/run_extraction_eval.py`:

```python
"""Extraction evaluation runner.

Runs real LLM/VLM extraction on synthetic PDFs and compares against
ground truth to measure extraction accuracy.

Usage::
    python scripts/run_extraction_eval.py --version v1
    python scripts/run_extraction_eval.py --version v2
    python scripts/run_extraction_eval.py --version v1 --data-dir data/annotated --output-dir data/results/extraction_bcc
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.WARNING, format="%(levelname)s  %(name)s  %(message)s", stream=sys.stderr)
_log = logging.getLogger("run_extraction_eval")

# Deterministic test set selection: first 2 compliant, 2 non-compliant, 1 edge-case
DEFAULT_SELECTION = {
    "compliant": 2,
    "non_compliant": 2,
    "edge_case": 1,
}

CATEGORY_SUBDIRS = ["compliant", "non_compliant", "edge_case", "noncompliant"]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run extraction evaluation on synthetic or annotated data.")
    parser.add_argument("--version", type=str, default="v1", help="Version tag for results (v1 or v2).")
    parser.add_argument("--data-dir", type=Path, default=Path("data/synthetic_diverse"), help="Root data directory.")
    parser.add_argument("--output-dir", type=Path, default=Path("data/results/extraction"), help="Output directory for results.")
    parser.add_argument("--configs-dir", type=Path, default=Path("configs"), help="Configs directory.")
    parser.add_argument("--all-sets", action="store_true", help="Run on all sets, not just the 5 selected.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging.")
    return parser.parse_args()


def select_test_sets(data_dir: Path, selection: dict[str, int] | None = None) -> list[Path]:
    """Select a deterministic subset of test sets."""
    sel = selection or DEFAULT_SELECTION
    selected: list[Path] = []

    for subdir_name in CATEGORY_SUBDIRS:
        subdir = data_dir / subdir_name
        if not subdir.is_dir():
            continue
        sets = sorted(d for d in subdir.iterdir() if d.is_dir() and (d / "ground_truth.json").exists())
        # Map noncompliant -> non_compliant for selection count
        key = "non_compliant" if subdir_name == "noncompliant" else subdir_name
        count = sel.get(key, 0)
        selected.extend(sets[:count])

    return selected


def discover_all_sets(data_dir: Path) -> list[Path]:
    """Discover all test sets with ground_truth.json."""
    found: list[Path] = []
    for subdir_name in CATEGORY_SUBDIRS:
        subdir = data_dir / subdir_name
        if not subdir.is_dir():
            continue
        for gt_path in sorted(subdir.rglob("ground_truth.json")):
            found.append(gt_path.parent)
    return found


def load_ground_truth_extractions(test_set_dir: Path) -> list[dict[str, Any]]:
    """Load GT extractions from ground_truth.json documents[].extractions[]."""
    gt_path = test_set_dir / "ground_truth.json"
    data = json.loads(gt_path.read_text(encoding="utf-8"))
    gt_entities: list[dict[str, Any]] = []
    for doc in data.get("documents", []):
        doc_type = doc.get("doc_type", "")
        for ext in doc.get("extractions", []):
            gt_entities.append({
                "attribute": ext.get("attribute"),
                "value": ext.get("value"),
                "entity_type": ext.get("entity_type"),
                "doc_type": doc_type,
                "source_document": doc.get("filename", ""),
            })
    return gt_entities


def run_extraction_on_set(
    test_set_dir: Path,
    configs_dir: Path,
) -> list[dict[str, Any]]:
    """Run real extraction pipeline on a test set's documents.

    Returns a list of dicts with attribute, value, doc_type, source_document.
    """
    from planproof.ingestion.classifier import RuleBasedClassifier
    from planproof.ingestion.text_extractor import PdfPlumberExtractor
    from planproof.ingestion.entity_extractor import LLMEntityExtractor
    from planproof.ingestion.vlm_spatial_extractor import VLMSpatialExtractor

    # Classifier
    patterns_path = configs_dir / "classifier_patterns.yaml"
    classifier = RuleBasedClassifier(patterns_path)

    # Text extractor
    text_extractor = PdfPlumberExtractor()

    # LLM client (Groq or OpenAI)
    llm_client = _build_llm_client()
    llm_extractor = LLMEntityExtractor(
        llm=llm_client,
        prompts_dir=configs_dir / "prompts",
    )

    # VLM client (OpenAI GPT-4o)
    vlm_client = _build_vlm_client()
    vlm_extractor = VLMSpatialExtractor(
        openai_client=vlm_client,
        prompts_dir=configs_dir / "prompts",
    ) if vlm_client else None

    predicted: list[dict[str, Any]] = []

    # Find all documents in the test set
    doc_files = sorted(
        f for f in test_set_dir.iterdir()
        if f.suffix.lower() in (".pdf", ".png", ".jpg", ".jpeg")
    )

    for doc_file in doc_files:
        try:
            classified = classifier.classify(doc_file)
            doc_type = classified.document_type.value

            if classified.has_text_layer and doc_type in ("FORM", "REPORT", "CERTIFICATE"):
                # Text extraction path
                raw_text = text_extractor.extract_text(doc_file)
                entities = llm_extractor.extract_entities(raw_text, doc_type=doc_type)
                for e in entities:
                    predicted.append({
                        "attribute": e.attribute,
                        "value": e.value,
                        "doc_type": doc_type,
                        "source_document": doc_file.name,
                        "extraction_method": "OCR_LLM",
                    })

            elif doc_type == "DRAWING" and vlm_extractor:
                # VLM extraction path
                entities = vlm_extractor.extract_spatial_attributes(doc_file)
                for e in entities:
                    predicted.append({
                        "attribute": e.attribute,
                        "value": e.value,
                        "doc_type": doc_type,
                        "source_document": doc_file.name,
                        "extraction_method": "VLM_ZEROSHOT",
                    })

        except Exception as exc:  # noqa: BLE001
            _log.warning("Extraction failed for %s: %s", doc_file.name, exc)

    return predicted


def _build_llm_client() -> Any:
    """Build LLM client from environment variables."""
    api_key = os.environ.get("GROQ_API_KEY") or os.environ.get("PLANPROOF_LLM_API_KEY") or ""
    if not api_key:
        _log.warning("No LLM API key configured. Set GROQ_API_KEY or PLANPROOF_LLM_API_KEY.")
        return None

    from planproof.infrastructure.groq_client import GroqClient
    return GroqClient(api_key=api_key)


def _build_vlm_client() -> Any | None:
    """Build VLM client (OpenAI GPT-4o) from environment variables."""
    api_key = os.environ.get("OPENAI_API_KEY") or ""
    if not api_key:
        _log.warning("No OpenAI API key configured. VLM extraction will be skipped.")
        return None

    from planproof.infrastructure.openai_client import OpenAIClient
    return OpenAIClient(api_key=api_key)


def main() -> int:
    args = _parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)
        _log.setLevel(logging.INFO)

    data_dir: Path = args.data_dir
    output_dir: Path = args.output_dir
    configs_dir: Path = args.configs_dir
    version: str = args.version

    if not data_dir.exists():
        print(f"ERROR: data directory does not exist: {data_dir}", file=sys.stderr)
        return 1

    # Select test sets
    if args.all_sets:
        test_sets = discover_all_sets(data_dir)
    else:
        test_sets = select_test_sets(data_dir)

    if not test_sets:
        print(f"WARNING: no test sets found under {data_dir}", file=sys.stderr)
        return 0

    print(f"Extraction evaluation {version}")
    print(f"  Test sets: {len(test_sets)}")
    print(f"  Output: {output_dir}")

    from planproof.evaluation.extraction_metrics import compute_extraction_metrics

    all_results: list[dict[str, Any]] = []

    for i, test_set_dir in enumerate(test_sets):
        set_id = test_set_dir.name
        print(f"  [{i+1}/{len(test_sets)}] {set_id} ...", end="", flush=True)

        try:
            gt_entities = load_ground_truth_extractions(test_set_dir)
            pred_entities = run_extraction_on_set(test_set_dir, configs_dir)

            result = compute_extraction_metrics(gt_entities, pred_entities, set_id=set_id, doc_type="ALL")

            result_dict = {
                "set_id": set_id,
                "version": version,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "gt_entity_count": len(gt_entities),
                "predicted_entity_count": len(pred_entities),
                "recall": round(result.recall, 4),
                "precision": round(result.precision, 4),
                "value_accuracy": round(result.value_accuracy, 4),
                "per_attribute": result.per_attribute,
                "gt_entities": gt_entities,
                "predicted_entities": pred_entities,
                "matches": [
                    {
                        "gt_attribute": m.gt_attribute,
                        "gt_value": m.gt_value,
                        "predicted_attribute": m.predicted_attribute,
                        "predicted_value": m.predicted_value,
                        "matched": m.matched,
                        "value_correct": m.value_correct,
                    }
                    for m in result.matches
                ],
            }

            # Save result
            dest = output_dir / version / f"{set_id}.json"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(result_dict, indent=2, default=str), encoding="utf-8")

            all_results.append(result_dict)
            print(f" OK  recall={result.recall:.2f} prec={result.precision:.2f} val_acc={result.value_accuracy:.2f}")

        except Exception as exc:  # noqa: BLE001
            print(f" ERROR: {exc}")
            _log.exception("Error processing %s", set_id)

    # Print summary
    if all_results:
        avg_recall = sum(r["recall"] for r in all_results) / len(all_results)
        avg_precision = sum(r["precision"] for r in all_results) / len(all_results)
        avg_val_acc = sum(r["value_accuracy"] for r in all_results) / len(all_results)
        print(f"\nSummary ({version}): recall={avg_recall:.3f} precision={avg_precision:.3f} value_accuracy={avg_val_acc:.3f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run full test suite to check no import issues**

Run: `pytest -x -q`
Expected: All pass.

- [ ] **Step 3: Commit**

```bash
git add scripts/run_extraction_eval.py
git commit -m "feat(eval): add extraction evaluation runner script"
```

---

## Task 3: Run v1 Extraction and Analyse Failures

This task requires LLM/VLM API keys configured in the environment.

**Files:**
- Output: `data/results/extraction/v1/` (result JSONs)

- [ ] **Step 1: Run v1 extraction on 5 synthetic test sets**

```bash
python scripts/run_extraction_eval.py --version v1 --data-dir data/synthetic_diverse --output-dir data/results/extraction -v
```

Expected: 5 test sets processed, results saved to `data/results/extraction/v1/`.

- [ ] **Step 2: Analyse extraction failures**

```bash
python -c "
import json
from pathlib import Path
from collections import Counter

results_dir = Path('data/results/extraction/v1')
missed = Counter()
wrong_value = Counter()
hallucinated = Counter()
correct = Counter()

for f in sorted(results_dir.glob('*.json')):
    data = json.loads(f.read_text())
    for m in data['matches']:
        if m['gt_attribute'] and not m['matched']:
            missed[m['gt_attribute']] += 1
        elif m['matched'] and not m['value_correct']:
            wrong_value[m['gt_attribute']] += 1
        elif m['matched'] and m['value_correct']:
            correct[m['gt_attribute']] += 1
        elif not m['gt_attribute'] and m['predicted_attribute']:
            hallucinated[m['predicted_attribute']] += 1

print('=== Correct ===')
for attr, count in correct.most_common(): print(f'  {attr}: {count}')
print('=== Missed (FN) ===')
for attr, count in missed.most_common(): print(f'  {attr}: {count}')
print('=== Wrong Value ===')
for attr, count in wrong_value.most_common(): print(f'  {attr}: {count}')
print('=== Hallucinated (FP) ===')
for attr, count in hallucinated.most_common(): print(f'  {attr}: {count}')
"
```

- [ ] **Step 3: Document v1 failure patterns**

Record which attributes are consistently missed, which get wrong values, and what the common failure patterns are. This informs the prompt improvements in Task 4.

- [ ] **Step 4: Commit v1 results**

```bash
git add -f data/results/extraction/
git commit -m "data: v1 extraction results on 5 synthetic test sets"
```

---

## Task 4: Prompt Improvement and v2 Extraction

**Files:**
- Modify: `configs/prompts/form_extraction.yaml` (and other templates as needed)
- Output: `data/results/extraction/v2/`

- [ ] **Step 1: Update prompt templates based on v1 failure analysis**

Based on the failure patterns from Task 3, make targeted improvements to the prompt templates. Common fixes:

- Add missing attribute names to the extraction target lists
- Clarify unit expectations (e.g., "return values in metres, not feet")
- Add examples for commonly missed patterns
- Improve output format instructions

The specific changes depend on v1 results — read the failure analysis and fix the top 2-3 issues.

- [ ] **Step 2: Run v2 extraction on the same 5 sets**

```bash
python scripts/run_extraction_eval.py --version v2 --data-dir data/synthetic_diverse --output-dir data/results/extraction -v
```

- [ ] **Step 3: Compare v1 vs v2**

```bash
python -c "
import json
from pathlib import Path

for version in ['v1', 'v2']:
    results_dir = Path(f'data/results/extraction/{version}')
    recalls, precisions, val_accs = [], [], []
    for f in sorted(results_dir.glob('*.json')):
        data = json.loads(f.read_text())
        recalls.append(data['recall'])
        precisions.append(data['precision'])
        val_accs.append(data['value_accuracy'])
    n = len(recalls)
    print(f'{version}: recall={sum(recalls)/n:.3f} precision={sum(precisions)/n:.3f} value_accuracy={sum(val_accs)/n:.3f} (n={n})')
"
```

- [ ] **Step 4: Commit v2 results and prompt changes**

```bash
git add -f data/results/extraction/ configs/prompts/
git commit -m "feat(eval): v2 extraction with improved prompts — before/after comparison"
```

---

## Task 5: BCC Annotation Helper and Annotation

**Files:**
- Create: `scripts/annotate_bcc.py`
- Output: `data/annotated/` (3 annotated BCC sets)

- [ ] **Step 1: Create annotation helper script**

Create `scripts/annotate_bcc.py`:

```python
"""BCC data annotation helper.

Guides the user through annotating ground truth extractions for real BCC
architectural drawing sets. Generates ground_truth.json in the same format
as synthetic data.

Usage::
    python scripts/annotate_bcc.py --data-dir data/anonymised --output-dir data/annotated
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Attributes to annotate per document type
DRAWING_ATTRIBUTES = [
    ("building_height", "metres", "MEASUREMENT"),
    ("rear_garden_depth", "metres", "MEASUREMENT"),
    ("site_coverage", "percent", "MEASUREMENT"),
    ("building_footprint_area", "m²", "MEASUREMENT"),
    ("ridge_height", "metres", "MEASUREMENT"),
    ("eaves_height", "metres", "MEASUREMENT"),
    ("number_of_storeys", "count", "MEASUREMENT"),
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Annotate BCC application sets with ground truth.")
    parser.add_argument("--data-dir", type=Path, default=Path("data/anonymised"), help="BCC data directory.")
    parser.add_argument("--output-dir", type=Path, default=Path("data/annotated"), help="Output directory for annotations.")
    return parser.parse_args()


def list_available_sets(data_dir: Path) -> list[Path]:
    """List all BCC sets with their document counts."""
    sets: list[Path] = []
    for d in sorted(data_dir.iterdir()):
        if d.is_dir():
            docs = list(d.glob("*.pdf")) + list(d.glob("*.png")) + list(d.glob("*.jpg"))
            print(f"  [{len(sets)}] {d.name} ({len(docs)} documents)")
            sets.append(d)
    return sets


def annotate_document(doc_path: Path) -> list[dict]:
    """Interactively annotate one document."""
    print(f"\n  Document: {doc_path.name}")
    print(f"  Path: {doc_path}")
    print(f"  (Open this file to inspect it)")
    print()

    extractions: list[dict] = []

    for attr_name, unit, entity_type in DRAWING_ATTRIBUTES:
        response = input(f"    Is '{attr_name}' visible? (y/n/skip/done): ").strip().lower()

        if response == "done":
            break
        if response != "y":
            continue

        value_str = input(f"    Value of '{attr_name}' (in {unit}): ").strip()
        page_str = input(f"    Page number (default 1): ").strip() or "1"

        try:
            value: str | float = float(value_str)
        except ValueError:
            value = value_str

        extractions.append({
            "attribute": attr_name,
            "value": value,
            "unit": unit,
            "entity_type": entity_type,
            "page": int(page_str),
            "text_rendered": value_str,
            "bounding_box": None,
        })

    return extractions


def annotate_set(bcc_dir: Path, output_dir: Path) -> None:
    """Annotate all documents in one BCC set."""
    set_id = bcc_dir.name
    print(f"\n=== Annotating: {set_id} ===")

    docs = sorted(list(bcc_dir.glob("*.pdf")) + list(bcc_dir.glob("*.png")) + list(bcc_dir.glob("*.jpg")))
    print(f"  Found {len(docs)} documents")

    documents: list[dict] = []

    for doc_path in docs:
        suffix = doc_path.suffix.lower()
        # Guess doc_type from filename
        name_lower = doc_path.name.lower()
        if "elevation" in name_lower:
            doc_type = "DRAWING"
        elif "floor" in name_lower:
            doc_type = "DRAWING"
        elif "site" in name_lower:
            doc_type = "DRAWING"
        elif "plan" in name_lower:
            doc_type = "DRAWING"
        else:
            doc_type = "DRAWING"  # BCC sets are drawings-only

        extractions = annotate_document(doc_path)

        documents.append({
            "filename": doc_path.name,
            "doc_type": doc_type,
            "file_format": suffix.lstrip("."),
            "extractions": extractions,
        })

    # Build ground_truth.json
    ground_truth = {
        "set_id": set_id,
        "category": "real_bcc",
        "source": "manual_annotation",
        "annotated_at": datetime.now(timezone.utc).isoformat(),
        "documents": documents,
        "values": [],
        "rule_verdicts": [],
    }

    dest = output_dir / set_id / "ground_truth.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(ground_truth, indent=2), encoding="utf-8")
    print(f"\n  Saved: {dest}")

    # Summary
    total_extractions = sum(len(d["extractions"]) for d in documents)
    print(f"  Total annotations: {total_extractions}")


def main() -> int:
    args = _parse_args()
    data_dir: Path = args.data_dir
    output_dir: Path = args.output_dir

    if not data_dir.exists():
        print(f"ERROR: data directory does not exist: {data_dir}", file=sys.stderr)
        return 1

    print("Available BCC application sets:")
    available = list_available_sets(data_dir)

    if not available:
        print("No sets found.", file=sys.stderr)
        return 1

    # Select 3 sets
    print("\nSelect 3 sets to annotate (enter indices separated by spaces):")
    indices_str = input("> ").strip()
    try:
        indices = [int(x) for x in indices_str.split()][:3]
    except ValueError:
        print("Invalid input. Using first 3 sets.")
        indices = [0, 1, 2]

    selected = [available[i] for i in indices if i < len(available)]
    print(f"\nAnnotating {len(selected)} sets: {[s.name for s in selected]}")

    for bcc_dir in selected:
        annotate_set(bcc_dir, output_dir)

    print("\nDone! Annotated sets saved to:", output_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Commit annotation script**

```bash
git add scripts/annotate_bcc.py
git commit -m "feat(eval): add BCC annotation helper script for manual ground truth creation"
```

- [ ] **Step 3: Run annotation (interactive — requires user)**

```bash
python scripts/annotate_bcc.py --data-dir data/anonymised --output-dir data/annotated
```

Select 3 BCC sets with the clearest drawings. Annotate visible attributes.

- [ ] **Step 4: Run extraction on annotated BCC sets**

```bash
python scripts/run_extraction_eval.py --version v1 --data-dir data/annotated --output-dir data/results/extraction_bcc --all-sets -v
```

- [ ] **Step 5: Commit annotated data and BCC results**

```bash
git add data/annotated/ data/results/extraction_bcc/
git commit -m "data: annotate 3 BCC sets and run extraction evaluation"
```

---

## Task 6: Real Extraction Ablation and Error Attribution

**Files:**
- Create: `scripts/run_extraction_ablation.py`
- Create: `docs/EXTRACTION_ERROR_ATTRIBUTION.md`

- [ ] **Step 1: Create extraction ablation script**

Create `scripts/run_extraction_ablation.py`:

```python
"""Feed real (imperfect) extractions into the reasoning pipeline.

Reads v2 extraction results and runs full_system reasoning on them,
then compares against oracle (Phase 8a) results for error attribution.

Usage::
    python scripts/run_extraction_ablation.py
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.WARNING, format="%(levelname)s  %(name)s  %(message)s", stream=sys.stderr)
_log = logging.getLogger("extraction_ablation")


def _build_entities_from_extraction_results(
    extraction_result: dict[str, Any],
) -> list[Any]:
    """Convert extraction result JSON into ExtractedEntity objects."""
    from planproof.schemas.entities import EntityType, ExtractedEntity, ExtractionMethod

    entities: list[ExtractedEntity] = []
    ts = datetime.now(timezone.utc)

    for pred in extraction_result.get("predicted_entities", []):
        attr = pred.get("attribute")
        value = pred.get("value")
        doc_type = pred.get("doc_type", "FORM")
        source_doc = f"{doc_type}_{pred.get('source_document', 'unknown')}"
        method_str = pred.get("extraction_method", "OCR_LLM")

        try:
            method = ExtractionMethod(method_str)
        except ValueError:
            method = ExtractionMethod.OCR_LLM

        entities.append(ExtractedEntity(
            entity_type=EntityType.MEASUREMENT,
            attribute=attr,
            value=value,
            unit=None,
            confidence=0.80,  # realistic confidence for LLM extraction
            source_document=source_doc,
            source_page=None,
            source_region=None,
            extraction_method=method,
            timestamp=ts,
        ))

    return entities


def run_reasoning_with_real_entities(
    entities: list[Any],
    configs_dir: Path,
) -> tuple[list[Any], list[Any]]:
    """Run the reasoning pipeline on real extracted entities.

    Returns (verdicts, assessability_results).
    """
    from planproof.reasoning.assessability import DefaultAssessabilityEvaluator
    from planproof.reasoning.confidence import ThresholdConfidenceGate
    from planproof.reasoning.evaluators.factory import RuleFactory
    from planproof.reasoning.reconciliation import PairwiseReconciler
    from planproof.representation.flat_evidence import FlatEvidenceProvider
    from planproof.representation.normalisation import Normaliser
    from planproof.schemas.reconciliation import ReconciledEvidence, ReconciliationStatus

    from planproof.reasoning.evaluators.attribute_diff import AttributeDiffEvaluator
    from planproof.reasoning.evaluators.enum_check import EnumCheckEvaluator
    from planproof.reasoning.evaluators.fuzzy_match import FuzzyMatchEvaluator
    from planproof.reasoning.evaluators.numeric_threshold import NumericThresholdEvaluator
    from planproof.reasoning.evaluators.numeric_tolerance import NumericToleranceEvaluator
    from planproof.reasoning.evaluators.ratio_threshold import RatioThresholdEvaluator

    factory = RuleFactory()
    RuleFactory.register_evaluator("numeric_threshold", NumericThresholdEvaluator)
    RuleFactory.register_evaluator("ratio_threshold", RatioThresholdEvaluator)
    RuleFactory.register_evaluator("enum_check", EnumCheckEvaluator)
    RuleFactory.register_evaluator("fuzzy_string_match", FuzzyMatchEvaluator)
    RuleFactory.register_evaluator("numeric_tolerance", NumericToleranceEvaluator)
    RuleFactory.register_evaluator("attribute_diff", AttributeDiffEvaluator)

    # Normalise
    normaliser = Normaliser()
    entities = normaliser.normalise_all(entities)

    # Evidence provider
    evidence_provider = FlatEvidenceProvider(entities)

    # Reconciler
    reconciler = PairwiseReconciler()

    # Confidence gate
    conf_path = configs_dir / "confidence_thresholds.yaml"
    confidence_gate = ThresholdConfidenceGate.from_yaml(conf_path) if conf_path.exists() else ThresholdConfidenceGate(thresholds={})

    # Confidence gating
    entities = confidence_gate.filter_trusted(entities)
    evidence_provider.update_entities(entities)

    # Reconciliation
    from planproof.schemas.entities import ExtractedEntity
    reconciled_evidence: dict[str, ReconciledEvidence] = {}
    groups: dict[str, list[ExtractedEntity]] = {}
    for entity in entities:
        key = entity.attribute if entity.attribute is not None else entity.entity_type.value
        groups.setdefault(key, []).append(entity)
    for attr, group in groups.items():
        reconciled_evidence[attr] = reconciler.reconcile(group, attr)

    # Load rules
    rules_dir = configs_dir / "rules"
    loaded_rule_pairs = factory.load_rules(rules_dir)
    rules_dict = {cfg.rule_id: cfg for cfg, _ in loaded_rule_pairs}
    all_rule_ids = list(rules_dict.keys())

    # Assessability
    assessability_evaluator = DefaultAssessabilityEvaluator(
        evidence_provider=evidence_provider,
        confidence_gate=confidence_gate,
        reconciler=reconciler,
        rules=rules_dict,
    )
    assessability_results: list[Any] = []
    for rule_id in all_rule_ids:
        result = assessability_evaluator.evaluate(rule_id)
        assessability_results.append(result)

    assessable_ids = {r.rule_id for r in assessability_results if r.status == "ASSESSABLE"}

    # Rule evaluation
    fallback_missing = ReconciledEvidence(attribute="__fallback__", status=ReconciliationStatus.MISSING, sources=[])
    verdicts: list[Any] = []
    for config, evaluator in loaded_rule_pairs:
        if config.rule_id not in assessable_ids:
            continue
        primary_attr = config.parameters.get("attribute") or config.parameters.get("numerator_attribute") or config.rule_id
        evidence = reconciled_evidence.get(primary_attr, fallback_missing)
        params_with_id = {**config.parameters, "rule_id": config.rule_id}
        verdict = evaluator.evaluate(evidence, params_with_id)
        verdicts.append(verdict)

    return verdicts, assessability_results


def main() -> int:
    extraction_dir = Path("data/results/extraction/v2")
    oracle_dir = Path("data/results/full_system")
    output_dir = Path("data/results/extraction_ablation")
    configs_dir = Path("configs")

    if not extraction_dir.exists():
        print(f"ERROR: extraction results not found: {extraction_dir}", file=sys.stderr)
        print("Run: python scripts/run_extraction_eval.py --version v2 first", file=sys.stderr)
        return 1

    from planproof.evaluation.results import RuleResult

    print("Extraction ablation — feeding real extractions into reasoning pipeline")

    for extraction_file in sorted(extraction_dir.glob("*.json")):
        set_id = extraction_file.stem
        print(f"  {set_id} ...", end="", flush=True)

        try:
            extraction_data = json.loads(extraction_file.read_text(encoding="utf-8"))
            entities = _build_entities_from_extraction_results(extraction_data)

            verdicts, assessability_results = run_reasoning_with_real_entities(entities, configs_dir)

            # Build RuleResult list
            from planproof.reasoning.evaluators.factory import RuleFactory
            from planproof.reasoning.evaluators.numeric_threshold import NumericThresholdEvaluator
            from planproof.reasoning.evaluators.ratio_threshold import RatioThresholdEvaluator
            from planproof.reasoning.evaluators.enum_check import EnumCheckEvaluator
            from planproof.reasoning.evaluators.fuzzy_match import FuzzyMatchEvaluator
            from planproof.reasoning.evaluators.numeric_tolerance import NumericToleranceEvaluator
            from planproof.reasoning.evaluators.attribute_diff import AttributeDiffEvaluator

            factory = RuleFactory()
            RuleFactory.register_evaluator("numeric_threshold", NumericThresholdEvaluator)
            RuleFactory.register_evaluator("ratio_threshold", RatioThresholdEvaluator)
            RuleFactory.register_evaluator("enum_check", EnumCheckEvaluator)
            RuleFactory.register_evaluator("fuzzy_string_match", FuzzyMatchEvaluator)
            RuleFactory.register_evaluator("numeric_tolerance", NumericToleranceEvaluator)
            RuleFactory.register_evaluator("attribute_diff", AttributeDiffEvaluator)

            all_rule_ids = [cfg.rule_id for cfg, _ in factory.load_rules(configs_dir / "rules")]
            evaluated_ids = {v.rule_id for v in verdicts}
            assessability_map = {ar.rule_id: ar for ar in assessability_results}

            # Load GT verdicts
            gt_path = None
            for subdir in ["compliant", "non_compliant", "edge_case", "noncompliant"]:
                candidate = Path("data/synthetic_diverse") / subdir / set_id / "ground_truth.json"
                if candidate.exists():
                    gt_path = candidate
                    break

            gt_verdicts: dict[str, str] = {}
            if gt_path:
                gt_data = json.loads(gt_path.read_text(encoding="utf-8"))
                gt_verdicts = {v["rule_id"]: v["outcome"] for v in gt_data.get("rule_verdicts", [])}

            rule_results: list[dict[str, Any]] = []
            for rule_id in all_rule_ids:
                gt_outcome = gt_verdicts.get(rule_id, "PASS")
                if rule_id in evaluated_ids:
                    predicted = str(next(v for v in verdicts if v.rule_id == rule_id).outcome)
                else:
                    predicted = "NOT_ASSESSABLE"

                ar = assessability_map.get(rule_id)
                if ar and ar.status == "PARTIALLY_ASSESSABLE" and predicted == "NOT_ASSESSABLE":
                    predicted = "PARTIALLY_ASSESSABLE"

                rule_results.append({
                    "rule_id": rule_id,
                    "ground_truth_outcome": gt_outcome,
                    "predicted_outcome": predicted,
                    "belief": ar.belief if ar else None,
                    "plausibility": ar.plausibility if ar else None,
                    "conflict_mass": ar.conflict_mass if ar else None,
                    "blocking_reason": str(ar.blocking_reason) if ar else None,
                })

            result = {
                "set_id": set_id,
                "config_name": "real_extraction",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "rule_results": rule_results,
            }

            dest = output_dir / f"{set_id}.json"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(result, indent=2), encoding="utf-8")

            n_pass = sum(1 for r in rule_results if r["predicted_outcome"] == "PASS")
            n_fail = sum(1 for r in rule_results if r["predicted_outcome"] == "FAIL")
            n_na = sum(1 for r in rule_results if r["predicted_outcome"] in ("NOT_ASSESSABLE", "PARTIALLY_ASSESSABLE"))
            print(f" OK  pass={n_pass} fail={n_fail} na={n_na}")

        except Exception as exc:  # noqa: BLE001
            print(f" ERROR: {exc}")
            _log.exception("Error for %s", set_id)

    # Error attribution
    print("\n=== Error Attribution ===")
    _run_error_attribution(output_dir, oracle_dir)

    return 0


def _run_error_attribution(real_dir: Path, oracle_dir: Path) -> None:
    """Compare real extraction verdicts against oracle verdicts."""
    categories = {"end_to_end_success": 0, "extraction_failure": 0, "reasoning_failure": 0, "serendipitous": 0}
    belief_pairs: list[tuple[float, float]] = []  # (oracle, real)

    for real_file in sorted(real_dir.glob("*.json")):
        set_id = real_file.stem
        oracle_file = oracle_dir / f"{set_id}.json"
        if not oracle_file.exists():
            continue

        real_data = json.loads(real_file.read_text(encoding="utf-8"))
        oracle_data = json.loads(oracle_file.read_text(encoding="utf-8"))

        oracle_map = {r["rule_id"]: r for r in oracle_data.get("rule_results", [])}

        for rr in real_data["rule_results"]:
            rule_id = rr["rule_id"]
            oracle_rr = oracle_map.get(rule_id)
            if not oracle_rr:
                continue

            gt = rr["ground_truth_outcome"]
            real_pred = rr["predicted_outcome"]
            oracle_pred = oracle_rr.get("predicted_outcome", "NOT_ASSESSABLE")

            # Correctness: PASS/FAIL match GT, or NOT_ASSESSABLE/PARTIALLY_ASSESSABLE when GT=PASS (acceptable)
            real_correct = (real_pred == gt) or (real_pred in ("NOT_ASSESSABLE", "PARTIALLY_ASSESSABLE") and gt == "PASS")
            oracle_correct = (oracle_pred == gt) or (oracle_pred in ("NOT_ASSESSABLE", "PARTIALLY_ASSESSABLE") and gt == "PASS")

            if oracle_correct and real_correct:
                categories["end_to_end_success"] += 1
            elif oracle_correct and not real_correct:
                categories["extraction_failure"] += 1
            elif not oracle_correct and not real_correct:
                categories["reasoning_failure"] += 1
            else:
                categories["serendipitous"] += 1

            # Belief comparison
            oracle_belief = oracle_rr.get("belief")
            real_belief = rr.get("belief")
            if oracle_belief is not None and real_belief is not None:
                belief_pairs.append((oracle_belief, real_belief))

    print(f"  End-to-end success: {categories['end_to_end_success']}")
    print(f"  Extraction failures: {categories['extraction_failure']}")
    print(f"  Reasoning failures: {categories['reasoning_failure']}")
    print(f"  Serendipitous: {categories['serendipitous']}")

    if belief_pairs:
        oracle_avg = sum(b[0] for b in belief_pairs) / len(belief_pairs)
        real_avg = sum(b[1] for b in belief_pairs) / len(belief_pairs)
        print(f"  Oracle avg belief: {oracle_avg:.3f}")
        print(f"  Real avg belief: {real_avg:.3f}")
        print(f"  Belief drop: {oracle_avg - real_avg:.3f}")


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run extraction ablation**

```bash
python scripts/run_extraction_ablation.py
```

- [ ] **Step 3: Commit**

```bash
git add scripts/run_extraction_ablation.py data/results/extraction_ablation/
git commit -m "feat(eval): real extraction ablation with error attribution analysis"
```

---

## Task 7: Error Attribution Documentation, Notebook Visualizations, and Project Docs

**Files:**
- Create: `docs/EXTRACTION_ERROR_ATTRIBUTION.md`
- Modify: `notebooks/ablation_analysis.ipynb`
- Modify: `docs/EXECUTION_STATUS.md`
- Modify: `docs/PROJECT_LOG.md`

- [ ] **Step 1: Write EXTRACTION_ERROR_ATTRIBUTION.md**

Based on the output from Task 6, create `docs/EXTRACTION_ERROR_ATTRIBUTION.md` with:

```markdown
# PlanProof — Extraction Error Attribution

> **Generated:** 2026-04-02
> **Data:** 5 synthetic test sets, v2 extraction vs oracle (Phase 8a)

## Summary
[Error attribution counts from Task 6]

## Error Categories
### Extraction Failures
[Cases where oracle was correct but real extraction caused wrong verdict]

### Reasoning Failures
[Cases where both oracle and real got it wrong]

## SABLE Belief Comparison
[Oracle avg belief vs real avg belief, belief drop]

## Dissertation Narrative
[2-3 paragraphs interpreting the findings]
```

- [ ] **Step 2: Add 4 extraction visualizations to notebook**

Add cells to `notebooks/ablation_analysis.ipynb` under "## Extraction Evaluation":

1. **Extraction accuracy grouped bar** — per-attribute recall and value accuracy
2. **v1 vs v2 delta chart** — improvement after prompt tuning
3. **Error attribution bar** — extraction vs reasoning failures
4. **SABLE belief comparison** — oracle vs real extraction

Each saved to `figures/` at 300 DPI.

- [ ] **Step 3: Update EXECUTION_STATUS.md**

Mark Phase 8c as Complete.

- [ ] **Step 4: Update PROJECT_LOG.md**

Add Phase 8c entry with findings.

- [ ] **Step 5: Commit all**

```bash
git add docs/ notebooks/ figures/
git commit -m "docs: extraction error attribution analysis, 4 new visualizations, Phase 8c complete"
```

- [ ] **Step 6: Push to GitHub**

```bash
git push origin master
```
