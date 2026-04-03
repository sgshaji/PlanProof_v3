"""SABLE threshold sensitivity analysis.

Sweeps theta_high from 0.30 to 0.95 (theta_low fixed at 0.30) and measures
how precision, recall, false FAILs and automation rate change.

The full_system results already contain belief/plausibility for every rule.
We re-classify each rule at each theta_high value without re-running the
pipeline:

  belief >= theta_high          → ASSESSABLE (rule evaluated)
  theta_low < belief < theta_high → PARTIALLY_ASSESSABLE
  belief <= theta_low OR None   → NOT_ASSESSABLE

For rules that were ASSESSABLE in the original run (belief=0.96) we use the
actual predicted verdict.  For rules that were PARTIALLY_ASSESSABLE in the
original run (belief=0.56) but would become ASSESSABLE at a lower theta_high,
we assume oracle correctness — the evaluator runs on perfect evidence and
produces the correct verdict (PASS → PASS, FAIL → FAIL).

Run from the project root:
    python scripts/run_threshold_sensitivity.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

THETA_HIGH_VALUES: list[float] = [
    0.30, 0.35, 0.40, 0.45, 0.50, 0.55,
    0.60, 0.65, 0.70, 0.75, 0.80, 0.85,
    0.90, 0.95,
]
THETA_LOW: float = 0.30  # fixed throughout the sweep

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "data" / "results" / "full_system"
OUTPUT_JSON = ROOT / "data" / "results" / "threshold_sensitivity.json"
FIGURES_DIR = ROOT / "figures"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_all_rule_results() -> list[dict]:
    """Return every rule-level dict from the full_system results."""
    rrs: list[dict] = []
    for f in sorted(RESULTS_DIR.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        rrs.extend(d.get("rule_results", []))
    return rrs


# ---------------------------------------------------------------------------
# Re-classification logic
# ---------------------------------------------------------------------------


def reclassify(rr: dict, theta_high: float, theta_low: float) -> str:
    """Return the predicted assessability class under the given thresholds."""
    belief = rr.get("belief")
    if belief is None or belief <= theta_low:
        return "NOT_ASSESSABLE"
    if belief >= theta_high:
        return "ASSESSABLE"
    return "PARTIALLY_ASSESSABLE"


def effective_verdict(rr: dict, new_class: str) -> str | None:
    """
    Return the verdict that would be produced given *new_class*.

    - ASSESSABLE: use the stored predicted_outcome when it is PASS/FAIL
      (the rule was already evaluated in the original run).  If the rule
      was PA/NA in the original run but is now ASSESSABLE at a lower
      theta_high, assume the oracle evaluator produces the correct verdict.
    - PA/NA: no verdict (returns None).
    """
    if new_class != "ASSESSABLE":
        return None

    orig = rr.get("predicted_outcome", "")
    if orig in ("PASS", "FAIL"):
        # Already evaluated in the original run — trust the actual result.
        return orig

    # Rule was PA or NA in the original run (belief=0.56 in practice).
    # With perfect oracle evidence the evaluator returns the correct verdict.
    return rr.get("ground_truth_outcome", "PASS")


# ---------------------------------------------------------------------------
# Sweep
# ---------------------------------------------------------------------------


def run_sweep(all_rrs: list[dict]) -> list[dict]:
    total_gt_fails = sum(1 for r in all_rrs if r.get("ground_truth_outcome") == "FAIL")
    total = len(all_rrs)

    rows: list[dict] = []

    for theta_high in THETA_HIGH_VALUES:
        pass_count = 0
        true_fail = 0
        false_fail = 0
        pa_count = 0
        na_count = 0

        for rr in all_rrs:
            new_class = reclassify(rr, theta_high, THETA_LOW)
            verdict = effective_verdict(rr, new_class)
            gt = rr.get("ground_truth_outcome", "PASS")

            if new_class == "NOT_ASSESSABLE":
                na_count += 1
            elif new_class == "PARTIALLY_ASSESSABLE":
                pa_count += 1
            else:  # ASSESSABLE
                if verdict == "PASS":
                    pass_count += 1
                elif verdict == "FAIL":
                    if gt == "FAIL":
                        true_fail += 1
                    else:
                        false_fail += 1

        total_evaluated = pass_count + true_fail + false_fail
        automation_rate = total_evaluated / total if total else 0.0
        precision = (
            true_fail / (true_fail + false_fail)
            if (true_fail + false_fail) > 0
            else 1.0
        )
        recall = true_fail / total_gt_fails if total_gt_fails > 0 else 0.0

        row = {
            "theta_high": theta_high,
            "pass": pass_count,
            "true_fail": true_fail,
            "false_fail": false_fail,
            "pa": pa_count,
            "na": na_count,
            "automation_rate": round(automation_rate, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
        }
        rows.append(row)

        print(
            f"theta_high={theta_high:.2f}: "
            f"PASS={pass_count:3d}  true_FAIL={true_fail:2d}  false_FAIL={false_fail:2d}  "
            f"PA={pa_count:3d}  NA={na_count:3d}  "
            f"auto={automation_rate:.3f}  prec={precision:.3f}  recall={recall:.3f}"
        )

    return rows


# ---------------------------------------------------------------------------
# Figure generation
# ---------------------------------------------------------------------------


def generate_figure(rows: list[dict]) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available — skipping figure generation")
        return

    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.size": 11,
            "axes.titlesize": 13,
            "axes.labelsize": 11,
            "figure.dpi": 300,
            "savefig.dpi": 300,
            "savefig.bbox": "tight",
        }
    )

    thetas = [r["theta_high"] for r in rows]
    false_fails = [r["false_fail"] for r in rows]
    auto_rates = [r["automation_rate"] for r in rows]
    recalls = [r["recall"] for r in rows]
    precisions = [r["precision"] for r in rows]

    fig, ax1 = plt.subplots(figsize=(10, 6))

    # Left axis: counts & recall
    (line_ff,) = ax1.plot(
        thetas, false_fails, "o-", color="#F44336",
        label="False FAILs", linewidth=2, markersize=7,
    )
    (line_rec,) = ax1.plot(
        thetas, recalls, "s--", color="#4CAF50",
        label="Recall", linewidth=2, markersize=7,
    )
    (line_prec,) = ax1.plot(
        thetas, precisions, "D--", color="#FF9800",
        label="Precision", linewidth=2, markersize=7,
    )

    ax1.set_xlabel(r"SABLE Assessable Threshold ($\theta_{high}$)", fontsize=12)
    ax1.set_ylabel("False FAILs / Precision / Recall", fontsize=11)
    ax1.set_ylim(-0.05, 1.15)

    # Mark current default threshold
    ax1.axvline(
        x=0.70, color="#555555", linestyle=":", linewidth=1.5,
        label=r"Current default ($\theta_{high}=0.70$)",
    )

    # Right axis: automation rate
    ax2 = ax1.twinx()
    (line_auto,) = ax2.plot(
        thetas, auto_rates, "^-", color="#2196F3",
        label="Automation Rate", linewidth=2, markersize=7,
    )
    ax2.set_ylabel("Automation Rate", color="#2196F3", fontsize=11)
    ax2.tick_params(axis="y", labelcolor="#2196F3")
    ax2.set_ylim(-0.05, 1.15)

    # Combined legend
    handles = [line_ff, line_rec, line_prec, line_auto]
    labels = [h.get_label() for h in handles]
    # Add the vline handle manually
    import matplotlib.lines as mlines
    vline_handle = mlines.Line2D(
        [], [], color="#555555", linestyle=":", linewidth=1.5,
        label=r"Current default ($\theta_{high}=0.70$)",
    )
    handles.append(vline_handle)
    labels.append(vline_handle.get_label())

    ax1.legend(handles, labels, loc="center right", fontsize=10, framealpha=0.9)

    ax1.set_title(
        "SABLE Threshold Sensitivity Analysis\n"
        r"Trade-off: Automation Rate vs False Violation Risk ($\theta_{low}=0.30$ fixed)",
        fontsize=13,
    )
    ax1.grid(True, alpha=0.3)
    ax1.set_xticks(thetas)
    ax1.set_xticklabels([f"{t:.2f}" for t in thetas], rotation=45, ha="right")

    FIGURES_DIR.mkdir(exist_ok=True)
    out = FIGURES_DIR / "threshold_sensitivity.png"
    fig.savefig(out, bbox_inches="tight")
    print(f"Saved {out}")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    if not RESULTS_DIR.exists():
        print(f"ERROR: results directory not found: {RESULTS_DIR}", file=sys.stderr)
        sys.exit(1)

    all_rrs = load_all_rule_results()
    if not all_rrs:
        print("ERROR: no rule results found", file=sys.stderr)
        sys.exit(1)

    print(f"Loaded {len(all_rrs)} rule evaluations from {RESULTS_DIR}")
    total_gt_fails = sum(1 for r in all_rrs if r.get("ground_truth_outcome") == "FAIL")
    print(f"Ground-truth FAILs: {total_gt_fails}  PASSes: {len(all_rrs) - total_gt_fails}")
    print(f"theta_low fixed at {THETA_LOW}\n")

    rows = run_sweep(all_rrs)

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"\nSaved {OUTPUT_JSON}")

    generate_figure(rows)


if __name__ == "__main__":
    main()
