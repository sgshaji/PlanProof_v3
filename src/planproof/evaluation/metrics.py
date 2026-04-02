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

        if pred in ("NOT_ASSESSABLE", "PARTIALLY_ASSESSABLE"):
            not_assessable += 1
            if gt == "FAIL":
                fn += 1
            # gt=PASS + NOT_ASSESSABLE/PARTIALLY_ASSESSABLE: no binary classification happened
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
    assessable = sum(
        1
        for r in rule_results
        if r.predicted_outcome not in ("NOT_ASSESSABLE", "PARTIALLY_ASSESSABLE")
    )
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


# ---------------------------------------------------------------------------
# SABLE metrics
# ---------------------------------------------------------------------------


def partially_assessable_rate(rule_results: list[RuleResult]) -> float:
    """Fraction of results with predicted_outcome == 'PARTIALLY_ASSESSABLE'.

    Returns 0.0 for an empty list.
    """
    if not rule_results:
        return 0.0
    count = sum(1 for r in rule_results if r.predicted_outcome == "PARTIALLY_ASSESSABLE")
    return count / len(rule_results)


def blocking_reason_distribution(rule_results: list[RuleResult]) -> dict[str, int]:
    """Count occurrences of each blocking_reason value.

    Results with blocking_reason=None are counted under the key ``"null"``.
    """
    dist: dict[str, int] = {}
    for r in rule_results:
        key = r.blocking_reason if r.blocking_reason is not None else "null"
        dist[key] = dist.get(key, 0) + 1
    return dist


def belief_statistics(rule_results: list[RuleResult]) -> dict[str, float]:
    """Compute descriptive statistics over belief scores, skipping None values.

    Returns a dict with keys: count, mean, std, min, max, median.
    When there are no belief values, count=0 and all others=0.0.
    """
    values = [r.belief for r in rule_results if r.belief is not None]
    n = len(values)
    if n == 0:
        return {"count": 0.0, "mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0, "median": 0.0}

    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    std = math.sqrt(variance)

    sorted_vals = sorted(values)
    if n % 2 == 1:
        median = sorted_vals[n // 2]
    else:
        median = (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2.0

    return {
        "count": float(n),
        "mean": mean,
        "std": std,
        "min": sorted_vals[0],
        "max": sorted_vals[-1],
        "median": median,
    }


_COMPONENT_MAP: list[tuple[str, str]] = [
    ("VLM", "ablation_a"),
    ("SNKG", "ablation_b"),
    ("Confidence Gating", "ablation_c"),
    ("Assessability (SABLE)", "ablation_d"),
]


def compute_component_contribution(
    results_by_config: dict[str, list[RuleResult]],
    baseline_config: str = "full_system",
) -> list[dict[str, object]]:
    """Compute per-component delta table: full_system vs each ablation config.

    For each ablation config present in *results_by_config* that appears in
    ``_COMPONENT_MAP``, compute confusion-matrix metrics for both the baseline
    and the ablation, then report the delta (baseline minus ablation for
    recall/precision/F2; ablation minus baseline for false_fail and
    not_assessable counts).  McNemar p-value and Cohen's h on recall are also
    included.

    Returns a list of dicts with keys:
        component_removed, config_name, recall_delta, precision_delta,
        f2_delta, false_fail_delta, not_assessable_delta, mcnemar_p, cohens_h.

    Float values are rounded to 4 decimal places.
    """
    baseline_results = results_by_config.get(baseline_config, [])
    baseline_cm = compute_confusion_matrix(baseline_results)
    baseline_recall = compute_recall(baseline_cm)
    baseline_precision = compute_precision(baseline_cm)
    baseline_f2 = compute_f2_score(baseline_cm)
    baseline_false_fail = baseline_cm["fp"]
    baseline_not_assessable = baseline_cm["not_assessable"]

    rows: list[dict[str, object]] = []

    for component_name, config_key in _COMPONENT_MAP:
        if config_key not in results_by_config:
            continue

        ablation_results = results_by_config[config_key]
        ablation_cm = compute_confusion_matrix(ablation_results)
        ablation_recall = compute_recall(ablation_cm)
        ablation_precision = compute_precision(ablation_cm)
        ablation_f2 = compute_f2_score(ablation_cm)
        ablation_false_fail = ablation_cm["fp"]
        ablation_not_assessable = ablation_cm["not_assessable"]

        _, p_value = mcnemar_test(baseline_results, ablation_results)
        h = cohens_h(
            max(0.0, min(1.0, baseline_recall)),
            max(0.0, min(1.0, ablation_recall)),
        )

        rows.append(
            {
                "component_removed": component_name,
                "config_name": config_key,
                "recall_delta": round(baseline_recall - ablation_recall, 4),
                "precision_delta": round(baseline_precision - ablation_precision, 4),
                "f2_delta": round(baseline_f2 - ablation_f2, 4),
                "false_fail_delta": round(ablation_false_fail - baseline_false_fail, 4),
                "not_assessable_delta": round(
                    ablation_not_assessable - baseline_not_assessable, 4
                ),
                "mcnemar_p": round(p_value, 4) if not math.isnan(p_value) else float("nan"),
                "cohens_h": round(h, 4),
            }
        )

    return rows
