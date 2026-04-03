"""Extraction accuracy metrics — entity matching, recall, precision, value accuracy.

Matches predicted entities against ground-truth entities by attribute name and
computes recall, precision, and value accuracy at both the aggregate and
per-attribute level.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ExtractionMatch:
    gt_attribute: str | None       # None for hallucinated (FP) entities
    gt_value: Any
    predicted_attribute: str | None  # None for missed (FN) entities
    predicted_value: Any
    matched: bool
    value_correct: bool
    doc_type: str
    set_id: str


@dataclass
class ExtractionEvalResult:
    set_id: str
    doc_type: str
    matches: list[ExtractionMatch]
    recall: float
    precision: float
    value_accuracy: float
    per_attribute: dict[str, dict[str, float]]  # attr -> {recall, precision, value_accuracy}


# ---------------------------------------------------------------------------
# Value comparison helpers
# ---------------------------------------------------------------------------


def _is_numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _numeric_correct(gt: float, pred: float) -> bool:
    """±10% relative tolerance, or ±0.5 absolute for values < 5.0."""
    diff = abs(gt - pred)
    if abs(gt) < 5.0:
        return diff <= 0.5
    return diff <= abs(gt) * 0.10


def _string_correct(gt: str, pred: str) -> bool:
    """Fuzzy match ratio ≥ 0.85 using SequenceMatcher."""
    ratio = difflib.SequenceMatcher(None, gt, pred).ratio()
    return ratio >= 0.85


def _values_correct(gt_value: Any, pred_value: Any) -> bool:
    """Dispatch to the appropriate value comparison strategy."""
    if _is_numeric(gt_value) and _is_numeric(pred_value):
        return _numeric_correct(float(gt_value), float(pred_value))
    if isinstance(gt_value, str) and isinstance(pred_value, str):
        # Exact case-insensitive match first (categorical fast-path),
        # then fall through to fuzzy for longer strings.
        if gt_value.strip().lower() == pred_value.strip().lower():
            return True
        return _string_correct(gt_value, pred_value)
    # Mixed types or unsupported — fall back to equality
    return gt_value == pred_value


# ---------------------------------------------------------------------------
# Normalisation helper
# ---------------------------------------------------------------------------


def _normalise(attribute: str) -> str:
    return attribute.strip().lower()


# ---------------------------------------------------------------------------
# Core matching
# ---------------------------------------------------------------------------


def match_entities(
    gt_entities: list[dict[str, Any]],
    predicted_entities: list[dict[str, Any]],
    doc_type: str = "",
    set_id: str = "",
) -> list[ExtractionMatch]:
    """Match predicted entities against ground-truth entities by attribute name.

    Returns one ExtractionMatch per GT entity (matched or missed as FN) and one
    ExtractionMatch per unmatched predicted entity (hallucination / FP).

    Matching is case-insensitive with whitespace stripped on the attribute key.
    """
    # Build a mutable index of predicted entities keyed by normalised attribute.
    # Preserve insertion order; first match wins for duplicate attribute names.
    pred_index: dict[str, list[dict[str, Any]]] = {}
    for p in predicted_entities:
        key = _normalise(p.get("attribute", ""))
        pred_index.setdefault(key, []).append(p)

    matched_pred_keys: set[int] = set()  # ids of consumed predicted entities
    results: list[ExtractionMatch] = []

    # -- Pass 1: process every GT entity
    for gt in gt_entities:
        gt_attr = gt.get("attribute", "")
        gt_val = gt.get("value")
        key = _normalise(gt_attr)

        candidates = pred_index.get(key, [])
        # Find the first unconsumed candidate
        chosen = None
        chosen_id = None
        for p in candidates:
            pid = id(p)
            if pid not in matched_pred_keys:
                chosen = p
                chosen_id = pid
                break

        if chosen is not None:
            matched_pred_keys.add(chosen_id)
            pred_val = chosen.get("value")
            correct = _values_correct(gt_val, pred_val)
            results.append(
                ExtractionMatch(
                    gt_attribute=gt_attr,
                    gt_value=gt_val,
                    predicted_attribute=chosen.get("attribute", ""),
                    predicted_value=pred_val,
                    matched=True,
                    value_correct=correct,
                    doc_type=doc_type,
                    set_id=set_id,
                )
            )
        else:
            # FN — missed entity
            results.append(
                ExtractionMatch(
                    gt_attribute=gt_attr,
                    gt_value=gt_val,
                    predicted_attribute=None,
                    predicted_value=None,
                    matched=False,
                    value_correct=False,
                    doc_type=doc_type,
                    set_id=set_id,
                )
            )

    # -- Pass 2: any predicted entity not consumed is a hallucination (FP)
    for p in predicted_entities:
        if id(p) not in matched_pred_keys:
            results.append(
                ExtractionMatch(
                    gt_attribute=None,
                    gt_value=None,
                    predicted_attribute=p.get("attribute", ""),
                    predicted_value=p.get("value"),
                    matched=False,
                    value_correct=False,
                    doc_type=doc_type,
                    set_id=set_id,
                )
            )

    return results


# ---------------------------------------------------------------------------
# Aggregate metric computation
# ---------------------------------------------------------------------------


def _safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator > 0 else 0.0


def compute_extraction_metrics(
    gt_entities: list[dict[str, Any]],
    predicted_entities: list[dict[str, Any]],
    set_id: str = "",
    doc_type: str = "",
) -> ExtractionEvalResult:
    """Compute recall, precision, value accuracy and per-attribute breakdown.

    - recall       = TP / (TP + FN)   where TP = matched GT entities
    - precision    = TP / (TP + FP)   where FP = hallucinated predicted entities
    - value_accuracy = value-correct matched / TP  (0.0 when TP=0)
    """
    matches = match_entities(gt_entities, predicted_entities, doc_type=doc_type, set_id=set_id)

    tp = sum(1 for m in matches if m.matched)
    fp = sum(1 for m in matches if not m.matched and m.gt_attribute is None)
    fn = sum(1 for m in matches if not m.matched and m.gt_attribute is not None)
    value_correct_count = sum(1 for m in matches if m.value_correct)

    recall = _safe_div(tp, tp + fn)
    precision = _safe_div(tp, tp + fp)
    value_accuracy = _safe_div(value_correct_count, tp)

    per_attribute = _build_per_attribute(matches)

    return ExtractionEvalResult(
        set_id=set_id,
        doc_type=doc_type,
        matches=matches,
        recall=recall,
        precision=precision,
        value_accuracy=value_accuracy,
        per_attribute=per_attribute,
    )


def _build_per_attribute(matches: list[ExtractionMatch]) -> dict[str, dict[str, float]]:
    """Build per-attribute recall / precision / value_accuracy breakdown.

    Each attribute that appears in either GT or predictions gets its own entry.
    """
    # Collect attribute keys from both sides
    attr_keys: set[str] = set()
    for m in matches:
        if m.gt_attribute is not None:
            attr_keys.add(_normalise(m.gt_attribute))
        if m.predicted_attribute is not None:
            attr_keys.add(_normalise(m.predicted_attribute))

    # Index matches by the canonical attribute key (normalised GT attr preferred)
    attr_matches: dict[str, list[ExtractionMatch]] = {k: [] for k in attr_keys}
    for m in matches:
        if m.gt_attribute is not None:
            attr_matches[_normalise(m.gt_attribute)].append(m)
        elif m.predicted_attribute is not None:
            attr_matches[_normalise(m.predicted_attribute)].append(m)

    result: dict[str, dict[str, float]] = {}
    for key, ms in attr_matches.items():
        tp = sum(1 for m in ms if m.matched)
        fp = sum(1 for m in ms if not m.matched and m.gt_attribute is None)
        fn = sum(1 for m in ms if not m.matched and m.gt_attribute is not None)
        vc = sum(1 for m in ms if m.value_correct)

        # Use the original-cased attribute name from the first match
        display_key = next(
            (m.gt_attribute or m.predicted_attribute for m in ms),
            key,
        )

        result[display_key] = {
            "recall": _safe_div(tp, tp + fn),
            "precision": _safe_div(tp, tp + fp),
            "value_accuracy": _safe_div(vc, tp),
        }

    return result
