"""Compute statistical analysis of ablation results with confidence intervals."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from planproof.evaluation.results import load_all_results, RuleResult
from planproof.evaluation.metrics import (
    bootstrap_ci,
    cohens_h,
    compute_automation_rate,
    compute_confusion_matrix,
    compute_f2_score,
    compute_precision,
    compute_recall,
    mcnemar_test,
)


ABLATION_CONFIGS = ["full_system", "ablation_a", "ablation_b", "ablation_c", "ablation_d"]


def load_results_by_config(results_dir: Path) -> dict[str, list[RuleResult]]:
    """Load results grouped by config name."""
    by_config: dict[str, list[RuleResult]] = {}
    for config in ABLATION_CONFIGS:
        config_dir = results_dir / config
        if config_dir.exists():
            experiments = load_all_results(config_dir)
            by_config[config] = [rr for exp in experiments for rr in exp.rule_results]
    return by_config


def compute_per_set_metrics(
    results_dir: Path,
) -> dict[str, dict[str, list[float]]]:
    """Compute per-set F2 and false-FAIL-rate values for each config.

    Returns a dict keyed by config name, each containing:
      - "f2": list of per-set F2 scores
      - "false_fail": list of per-set false-FAIL rates
      - "automation": list of per-set automation rates
    """
    per_set_data: dict[str, dict[str, list[float]]] = {}

    for config in ABLATION_CONFIGS:
        config_dir = results_dir / config
        if not config_dir.exists():
            continue

        f2_values: list[float] = []
        ff_values: list[float] = []
        auto_values: list[float] = []

        for exp in load_all_results(config_dir):
            rrs = exp.rule_results
            if not rrs:
                continue
            cm = compute_confusion_matrix(rrs)
            f2_values.append(compute_f2_score(cm))
            ff_values.append(cm["fp"] / len(rrs))
            auto_values.append(compute_automation_rate(rrs))

        per_set_data[config] = {
            "f2": f2_values,
            "false_fail": ff_values,
            "automation": auto_values,
        }

    return per_set_data


def benjamini_hochberg(p_values: list[float], alpha: float = 0.05) -> list[bool]:
    """Apply Benjamini-Hochberg FDR correction.

    Finds the largest rank k such that p_(k) <= k/n * alpha, then marks
    all hypotheses at ranks 1..k as significant.

    Returns a boolean list aligned with the input p_values.
    """
    n = len(p_values)
    if n == 0:
        return []

    indexed = sorted(enumerate(p_values), key=lambda x: x[1])

    largest_k = 0
    for rank, (_orig_idx, p) in enumerate(indexed, 1):
        if p <= alpha * rank / n:
            largest_k = rank

    significant = [False] * n
    for rank, (orig_idx, _p) in enumerate(indexed, 1):
        if rank <= largest_k:
            significant[orig_idx] = True

    return significant


def main() -> None:
    results_dir = Path("data/results")

    by_config = load_results_by_config(results_dir)
    per_set_data = compute_per_set_metrics(results_dir)

    # -------------------------------------------------------------------------
    # Per-config metrics with bootstrap CIs
    # -------------------------------------------------------------------------
    print("=" * 96)
    print(
        f"{'Config':<16} {'Recall':>8} {'Precision':>10} {'F2':>18} {'Auto':>8} {'FalseFAIL':>18}"
    )
    print("=" * 96)

    stats_output: dict[str, dict] = {}

    for config in ABLATION_CONFIGS:
        if config not in by_config:
            continue

        rrs = by_config[config]
        cm = compute_confusion_matrix(rrs)
        recall = compute_recall(cm)
        precision = compute_precision(cm)
        f2 = compute_f2_score(cm)
        auto = compute_automation_rate(rrs)
        false_fail_rate = cm["fp"] / len(rrs) if rrs else 0.0

        ps = per_set_data.get(config, {})

        f2_values = ps.get("f2", [])
        if len(f2_values) > 1:
            f2_lo, f2_hi = bootstrap_ci(f2_values)
        else:
            f2_lo = f2_hi = f2

        ff_values = ps.get("false_fail", [])
        if len(ff_values) > 1:
            ff_lo, ff_hi = bootstrap_ci(ff_values)
        else:
            ff_lo = ff_hi = false_fail_rate

        auto_values = ps.get("automation", [])
        if len(auto_values) > 1:
            auto_lo, auto_hi = bootstrap_ci(auto_values)
        else:
            auto_lo = auto_hi = auto

        # Point-estimate row
        print(
            f"{config:<16} {recall:>8.3f} {precision:>10.3f}"
            f" {f2:>8.3f}            "
            f" {auto:>8.3f}"
            f" {false_fail_rate:>8.3f}          "
        )
        # CI row (aligned under F2 and FalseFAIL columns)
        print(
            f"{'':>16} {'':>8} {'':>10}"
            f" [{f2_lo:.3f}, {f2_hi:.3f}]"
            f" {'':>8}"
            f" [{ff_lo:.3f}, {ff_hi:.3f}]"
        )

        stats_output[config] = {
            "recall": round(recall, 4),
            "precision": round(precision, 4),
            "f2": round(f2, 4),
            "f2_ci_lower": round(f2_lo, 4),
            "f2_ci_upper": round(f2_hi, 4),
            "automation_rate": round(auto, 4),
            "automation_ci_lower": round(auto_lo, 4),
            "automation_ci_upper": round(auto_hi, 4),
            "false_fail_rate": round(false_fail_rate, 4),
            "false_fail_ci_lower": round(ff_lo, 4),
            "false_fail_ci_upper": round(ff_hi, 4),
            "n_evaluations": len(rrs),
            "confusion_matrix": cm,
        }

    # -------------------------------------------------------------------------
    # Pairwise comparisons: full_system vs each ablation
    # -------------------------------------------------------------------------
    print("\n" + "=" * 72)
    print("Pairwise: full_system vs each ablation (McNemar, Cohen's h, BH correction)")
    print("=" * 72)

    baseline = by_config.get("full_system", [])
    comparisons = ["ablation_a", "ablation_b", "ablation_c", "ablation_d"]

    # Collect p-values first so BH correction covers all four simultaneously
    raw_results: list[tuple[float, float]] = []  # (statistic, p_value)
    for config in comparisons:
        if config not in by_config:
            raw_results.append((0.0, 1.0))
            continue
        stat, p = mcnemar_test(baseline, by_config[config])
        raw_results.append((stat, p if not math.isnan(p) else 1.0))

    p_values = [p for _stat, p in raw_results]
    significant = benjamini_hochberg(p_values)

    print(
        f"{'Comparison':<32} {'McNemar p':>12} {'Cohen h':>10} {'BH sig':>8}"
    )
    print("-" * 66)

    pairwise_output: list[dict] = []
    for i, config in enumerate(comparisons):
        stat, p = raw_results[i]
        if config not in by_config:
            continue
        h = cohens_h(
            max(0.0, min(1.0, compute_recall(compute_confusion_matrix(baseline)))),
            max(0.0, min(1.0, compute_recall(compute_confusion_matrix(by_config[config])))),
        )
        # Recover the original (possibly NaN) p for the table display
        stat_raw, p_raw = mcnemar_test(baseline, by_config[config])
        p_str = f"{p_raw:.4f}" if not math.isnan(p_raw) else "N/A   "
        sig_str = "***" if significant[i] else "n.s."

        print(f"full_system vs {config:<17} {p_str:>12} {h:>+10.4f} {sig_str:>8}")

        pairwise_output.append(
            {
                "comparison": f"full_system vs {config}",
                "mcnemar_statistic": round(stat_raw, 4),
                "mcnemar_p": round(p_raw, 6) if not math.isnan(p_raw) else None,
                "cohens_h": round(h, 4),
                "bh_significant": significant[i],
            }
        )

    # -------------------------------------------------------------------------
    # Persist results
    # -------------------------------------------------------------------------
    output = {
        "per_config": stats_output,
        "pairwise_comparisons": pairwise_output,
        "n_test_sets": 33,
        "n_rules": 8,
        "n_configs": len(ABLATION_CONFIGS),
        "bootstrap_n_resamples": 1000,
        "bootstrap_ci_level": 0.95,
        "bh_alpha": 0.05,
    }

    dest = results_dir / "statistics.json"
    dest.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(f"\nSaved to {dest}")


if __name__ == "__main__":
    main()
