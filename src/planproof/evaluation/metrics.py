"""Pure functions for computing evaluation metrics.

All functions are stateless and depend only on their inputs.  The confusion
matrix (CM) is the shared currency between functions: compute it once with
``compute_confusion_matrix`` then pass it to the metric functions.

McNemar's test uses ``scipy.stats.chi2`` when available; falls back to NaN if
scipy is not installed (it is an optional dependency).
"""

from __future__ import annotations

import math
import random

from planproof.evaluation.results import RuleResult


# ---------------------------------------------------------------------------
# Confusion matrix
# ---------------------------------------------------------------------------


def compute_confusion_matrix(rule_results: list[RuleResult]) -> dict[str, int]:
    """Count TP, FP, FN, TN and NOT_ASSESSABLE predictions.

    Counting rules:
    - TP: gt=FAIL, pred=FAIL
    - FP: gt=PASS, pred=FAIL
    - FN: gt=FAIL, pred=PASS *or* NOT_ASSESSABLE  (conservative — missed violations)
    - TN: gt=PASS, pred=PASS
    - not_assessable: any row where pred=NOT_ASSESSABLE (regardless of gt)

    NOT_ASSESSABLE with gt=PASS is counted only in ``not_assessable``; it does
    not contribute to TP/FP/FN/TN because neither a correct nor incorrect
    binary decision was made.
    """
    tp = fp = fn = tn = not_assessable = 0

    for r in rule_results:
        gt = r.ground_truth_outcome
        pred = r.predicted_outcome

        if pred == "NOT_ASSESSABLE":
            not_assessable += 1
            if gt == "FAIL":
                fn += 1
            # gt=PASS + NOT_ASSESSABLE: no binary classification happened
            continue

        if gt == "FAIL" and pred == "FAIL":
            tp += 1
        elif gt == "PASS" and pred == "FAIL":
            fp += 1
        elif gt == "FAIL" and pred == "PASS":
            fn += 1
        elif gt == "PASS" and pred == "PASS":
            tn += 1

    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "not_assessable": not_assessable}


# ---------------------------------------------------------------------------
# Scalar metrics from confusion matrix
# ---------------------------------------------------------------------------


def compute_recall(cm: dict[str, int]) -> float:
    """TP / (TP + FN).  Returns 0.0 when the denominator is zero."""
    denominator = cm["tp"] + cm["fn"]
    if denominator == 0:
        return 0.0
    return cm["tp"] / denominator


def compute_precision(cm: dict[str, int]) -> float:
    """TP / (TP + FP).  Returns 0.0 when the denominator is zero."""
    denominator = cm["tp"] + cm["fp"]
    if denominator == 0:
        return 0.0
    return cm["tp"] / denominator


def compute_f2_score(cm: dict[str, int]) -> float:
    """F-beta score with beta=2: (5 * P * R) / (4P + R).

    F2 weights recall twice as heavily as precision, making it more sensitive
    to missed violations (FN) than false alarms (FP).

    Returns 0.0 when the denominator is zero.
    """
    precision = compute_precision(cm)
    recall = compute_recall(cm)
    denominator = 4 * precision + recall
    if denominator == 0.0:
        return 0.0
    return (5 * precision * recall) / denominator


# ---------------------------------------------------------------------------
# Automation rate
# ---------------------------------------------------------------------------


def compute_automation_rate(rule_results: list[RuleResult]) -> float:
    """Fraction of results where the system produced a binary verdict.

    ``NOT_ASSESSABLE`` predictions are counted as non-automated.  Returns 0.0
    for an empty list.
    """
    if not rule_results:
        return 0.0
    assessable = sum(1 for r in rule_results if r.predicted_outcome != "NOT_ASSESSABLE")
    return assessable / len(rule_results)


# ---------------------------------------------------------------------------
# Bootstrap confidence interval
# ---------------------------------------------------------------------------


def bootstrap_ci(
    values: list[float],
    n_resamples: int = 1000,
    ci: float = 0.95,
) -> tuple[float, float]:
    """Percentile bootstrap CI for the mean of *values*.

    Uses ``random.Random(42)`` for reproducibility.  The *ci* parameter sets
    the confidence level (default 95 %).

    Returns (lower_bound, upper_bound).
    """
    rng = random.Random(42)
    n = len(values)
    means: list[float] = []
    for _ in range(n_resamples):
        sample = [rng.choice(values) for _ in range(n)]
        means.append(sum(sample) / n)

    means.sort()
    alpha = 1.0 - ci
    lower_idx = int(math.floor(alpha / 2 * n_resamples))
    upper_idx = int(math.ceil((1.0 - alpha / 2) * n_resamples)) - 1
    # Clamp indices to valid range
    lower_idx = max(0, min(lower_idx, n_resamples - 1))
    upper_idx = max(0, min(upper_idx, n_resamples - 1))
    return float(means[lower_idx]), float(means[upper_idx])


# ---------------------------------------------------------------------------
# McNemar's test
# ---------------------------------------------------------------------------


def _is_correct(result: RuleResult) -> bool:
    """True when the predicted outcome matches the ground truth."""
    # NOT_ASSESSABLE is never correct for a binary ground truth
    return result.predicted_outcome == result.ground_truth_outcome


def mcnemar_test(
    results_a: list[RuleResult],
    results_b: list[RuleResult],
) -> tuple[float, float]:
    """Paired McNemar's test comparing two systems on the same cases.

    Counts:
    - b: cases where A is correct and B is wrong
    - c: cases where B is correct and A is wrong

    chi-squared = (b - c)^2 / (b + c), df=1

    P-value is computed via ``scipy.stats.chi2`` when scipy is available;
    falls back to ``float('nan')`` otherwise.

    Returns (statistic, p_value).
    """
    b = 0  # A correct, B wrong
    c = 0  # B correct, A wrong

    for ra, rb in zip(results_a, results_b):
        a_correct = _is_correct(ra)
        b_correct = _is_correct(rb)
        if a_correct and not b_correct:
            b += 1
        elif b_correct and not a_correct:
            c += 1

    discordant = b + c
    if discordant == 0:
        return 0.0, float("nan")

    statistic = (b - c) ** 2 / discordant

    try:
        from scipy.stats import chi2  # type: ignore[import-untyped]

        p_value = float(chi2.sf(statistic, df=1))
    except ImportError:
        p_value = float("nan")

    return float(statistic), p_value


# ---------------------------------------------------------------------------
# Cohen's h
# ---------------------------------------------------------------------------


def cohens_h(p1: float, p2: float) -> float:
    """Effect size for the difference between two proportions.

    h = 2 * arcsin(sqrt(p1)) - 2 * arcsin(sqrt(p2))

    Positive when p1 > p2.  Sign is preserved so the direction of difference
    is interpretable.
    """
    return 2 * math.asin(math.sqrt(p1)) - 2 * math.asin(math.sqrt(p2))
