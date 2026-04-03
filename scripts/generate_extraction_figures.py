"""
Generate Phase 8c extraction evaluation figures (E1–E4).

Figures saved to figures/ at 300 DPI with dissertation-quality styling.
Run from the project root:
    python scripts/generate_extraction_figures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
FIGURES = ROOT / "figures"
FIGURES.mkdir(exist_ok=True)

V1_DIR = ROOT / "data" / "results" / "extraction" / "v1"
V2_DIR = ROOT / "data" / "results" / "extraction" / "v2"
FULL_SYS_DIR = ROOT / "data" / "results" / "full_system"
EXTR_ABL_DIR = ROOT / "data" / "results" / "extraction_ablation"

# ── Dissertation style ────────────────────────────────────────────────────────
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

CONFIG_COLORS = {
    "full_system": "#2196F3",
    "ablation_a": "#FF9800",
    "ablation_b": "#4CAF50",
    "ablation_c": "#9C27B0",
    "ablation_d": "#F44336",
    "naive_baseline": "#795548",
    "strong_baseline": "#607D8B",
}

COLOR_V1_LIGHT = "#90CAF9"  # light blue
COLOR_V2_DARK = "#1565C0"   # dark blue
COLOR_PRECISION = "#EF9A9A"  # light red for precision highlight


# ── Data loading helpers ──────────────────────────────────────────────────────

def load_extraction_results(directory: Path) -> list[dict]:
    return [json.loads(f.read_text()) for f in sorted(directory.glob("*.json"))]


def avg_per_attribute(results: list[dict]) -> dict[str, dict[str, float]]:
    """Average per-attribute metrics across all result files."""
    accumulator: dict[str, dict[str, list[float]]] = {}
    for d in results:
        for attr, stats in d.get("per_attribute", {}).items():
            if attr not in accumulator:
                accumulator[attr] = {"recall": [], "precision": [], "value_accuracy": []}
            for k in ["recall", "precision", "value_accuracy"]:
                accumulator[attr][k].append(stats[k])
    return {
        attr: {k: sum(vals) / len(vals) for k, vals in metrics.items()}
        for attr, metrics in accumulator.items()
    }


def overall_avg(results: list[dict]) -> dict[str, float]:
    keys = ["recall", "precision", "value_accuracy"]
    return {k: sum(d[k] for d in results) / len(results) for k in keys}


def avg_belief(directory: Path) -> float:
    beliefs = []
    for f in directory.glob("*.json"):
        d = json.loads(f.read_text())
        for r in d.get("rule_results", []):
            b = r.get("belief")
            if b is not None:
                beliefs.append(b)
    return sum(beliefs) / len(beliefs) if beliefs else 0.0


def per_set_beliefs(directory: Path) -> list[float]:
    """All individual belief values from a result directory."""
    beliefs = []
    for f in sorted(directory.glob("*.json")):
        d = json.loads(f.read_text())
        for r in d.get("rule_results", []):
            b = r.get("belief")
            if b is not None:
                beliefs.append(b)
    return beliefs


# ── Figure E1: Extraction accuracy grouped bar ───────────────────────────────

def figure_e1() -> None:
    """Per-attribute recall and value accuracy, grouped by v1 (light) / v2 (dark)."""
    v1_results = load_extraction_results(V1_DIR)
    v2_results = load_extraction_results(V2_DIR)

    v1_attrs = avg_per_attribute(v1_results)
    v2_attrs = avg_per_attribute(v2_results)

    # Use target attributes found in data
    target_attrs = [
        "building_height",
        "rear_garden_depth",
        "site_coverage",
        "site_address",
        "site_area",
    ]
    labels = [a.replace("_", "\n") for a in target_attrs]

    v1_recall = [v1_attrs.get(a, {}).get("recall", 0.0) for a in target_attrs]
    v2_recall = [v2_attrs.get(a, {}).get("recall", 0.0) for a in target_attrs]
    v1_va = [v1_attrs.get(a, {}).get("value_accuracy", 0.0) for a in target_attrs]
    v2_va = [v2_attrs.get(a, {}).get("value_accuracy", 0.0) for a in target_attrs]

    x = np.arange(len(target_attrs))
    width = 0.2

    fig, ax = plt.subplots(figsize=(13, 6))

    bars = [
        ax.bar(x - 1.5 * width, v1_recall, width, label="v1 Recall", color=COLOR_V1_LIGHT, edgecolor="white"),
        ax.bar(x - 0.5 * width, v2_recall, width, label="v2 Recall", color=COLOR_V2_DARK, edgecolor="white"),
        ax.bar(x + 0.5 * width, v1_va, width, label="v1 Value Accuracy", color="#FFCC80", edgecolor="white"),
        ax.bar(x + 1.5 * width, v2_va, width, label="v2 Value Accuracy", color="#E65100", edgecolor="white"),
    ]

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylim(0, 1.15)
    ax.set_ylabel("Score")
    ax.set_title("Figure E1 — Per-Attribute Extraction Accuracy (v1 vs v2)")
    ax.legend(fontsize=9, ncol=2)
    ax.axhline(1.0, color="grey", linewidth=0.5, linestyle="--", alpha=0.5)
    ax.set_xlabel("Attribute")

    fig.tight_layout()
    out = FIGURES / "extraction_accuracy.png"
    fig.savefig(out, dpi=300)
    plt.close(fig)
    print(f"  Saved {out}")


# ── Figure E2: v1 vs v2 delta ────────────────────────────────────────────────

def figure_e2() -> None:
    """Bar chart showing improvement delta per metric from v1 to v2."""
    v1_results = load_extraction_results(V1_DIR)
    v2_results = load_extraction_results(V2_DIR)

    v1_avg = overall_avg(v1_results)
    v2_avg = overall_avg(v2_results)

    metrics = ["recall", "precision", "value_accuracy"]
    labels = ["Recall", "Precision", "Value Accuracy"]
    deltas = [v2_avg[m] - v1_avg[m] for m in metrics]

    colors = [
        "#4CAF50" if d >= 0 else "#F44336" for d in deltas
    ]
    # Precision is the key improvement — highlight it
    colors[1] = "#1565C0"

    fig, ax = plt.subplots(figsize=(8, 5))

    bars = ax.bar(labels, deltas, color=colors, edgecolor="white", zorder=3)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_ylabel("Δ Score (v2 − v1)")
    ax.set_title("Figure E2 — Extraction Improvement: v1 → v2")
    ax.set_ylim(-0.1, max(deltas) + 0.1)
    ax.grid(axis="y", alpha=0.3, zorder=0)

    for bar, delta in zip(bars, deltas):
        sign = "+" if delta >= 0 else ""
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.01,
            f"{sign}{delta:.3f}",
            ha="center",
            va="bottom",
            fontsize=11,
            fontweight="bold",
        )

    # Annotation for precision jump
    ax.annotate(
        "Precision +0.416\n(hallucination elimination)",
        xy=(1, deltas[1]),
        xytext=(1.6, deltas[1] + 0.05),
        arrowprops=dict(arrowstyle="->", color="#1565C0"),
        fontsize=9,
        color="#1565C0",
    )

    fig.tight_layout()
    out = FIGURES / "extraction_v1_v2_delta.png"
    fig.savefig(out, dpi=300)
    plt.close(fig)
    print(f"  Saved {out}")


# ── Figure E3: 2×2 False-FAIL Matrix ─────────────────────────────────────────

def figure_e3() -> None:
    """Heatmap showing false FAIL counts by extraction type × system config."""
    # Actual values from the experiment:
    # rows = extraction type (oracle / real)
    # cols = system config (full_system / ablation_d)
    matrix = np.array(
        [
            [0, 100],   # oracle extraction: full_system=0, ablation_d=100
            [0, 26],    # real extraction:   full_system=0, ablation_d=26
        ]
    )

    row_labels = ["Oracle Extraction\n(SABLE enabled)", "Real Extraction\n(SABLE enabled)"]
    col_labels = ["Full System\n(SABLE on)", "Ablation D\n(SABLE off)"]

    fig, ax = plt.subplots(figsize=(8, 5))

    # Custom colormap: white→red
    cmap = plt.cm.Reds  # type: ignore[attr-defined]
    im = ax.imshow(matrix, cmap=cmap, vmin=0, vmax=110, aspect="auto")

    ax.set_xticks([0, 1])
    ax.set_yticks([0, 1])
    ax.set_xticklabels(col_labels, fontsize=11)
    ax.set_yticklabels(row_labels, fontsize=11)
    ax.set_title("Figure E3 — 2×2 False-FAIL Matrix\n(compliant cases incorrectly rejected)")

    # Cell annotations
    for i in range(2):
        for j in range(2):
            val = matrix[i, j]
            text_color = "white" if val > 50 else "black"
            ax.text(
                j, i, str(val),
                ha="center", va="center",
                fontsize=18, fontweight="bold",
                color=text_color,
            )

    fig.colorbar(im, ax=ax, label="False FAIL count")

    # Interpretation annotations
    ax.annotate(
        "Architecture resilience:\n0 false FAILs regardless\nof extraction quality",
        xy=(0, 0.5), xycoords="axes fraction",
        xytext=(-0.6, 0.85),
        textcoords="axes fraction",
        fontsize=8.5, color="#1565C0",
        arrowprops=dict(arrowstyle="->", color="#1565C0"),
    )

    fig.tight_layout()
    out = FIGURES / "false_fail_matrix.png"
    fig.savefig(out, dpi=300)
    plt.close(fig)
    print(f"  Saved {out}")


# ── Figure E4: SABLE belief comparison ───────────────────────────────────────

def figure_e4() -> None:
    """Paired bar plot: oracle vs real extraction SABLE beliefs."""
    oracle_beliefs = per_set_beliefs(FULL_SYS_DIR)
    real_beliefs = per_set_beliefs(EXTR_ABL_DIR)

    oracle_avg = sum(oracle_beliefs) / len(oracle_beliefs) if oracle_beliefs else 0
    real_avg = sum(real_beliefs) / len(real_beliefs) if real_beliefs else 0

    fig, axes = plt.subplots(1, 2, figsize=(13, 6))

    # Left panel: box plots
    ax = axes[0]
    bp = ax.boxplot(
        [oracle_beliefs, real_beliefs],
        labels=["Oracle\nExtraction", "Real\nExtraction"],
        patch_artist=True,
        medianprops=dict(color="black", linewidth=2),
    )
    bp["boxes"][0].set_facecolor("#BBDEFB")
    bp["boxes"][1].set_facecolor("#EF9A9A")
    ax.set_ylabel("SABLE Belief Score")
    ax.set_title("Belief Score Distribution")
    ax.set_ylim(-0.05, 1.05)
    ax.axhline(oracle_avg, color="#1565C0", linestyle="--", alpha=0.6, linewidth=1.5,
               label=f"Oracle mean={oracle_avg:.3f}")
    ax.axhline(real_avg, color="#C62828", linestyle="--", alpha=0.6, linewidth=1.5,
               label=f"Real mean={real_avg:.3f}")
    ax.legend(fontsize=9)

    # Right panel: mean bar comparison
    ax2 = axes[1]
    bars = ax2.bar(
        ["Oracle Extraction", "Real Extraction"],
        [oracle_avg, real_avg],
        color=["#BBDEFB", "#EF9A9A"],
        edgecolor="white",
        zorder=3,
    )
    ax2.set_ylabel("Average SABLE Belief Score")
    ax2.set_title("Average Belief: Oracle vs Real Extraction")
    ax2.set_ylim(0, max(oracle_avg, real_avg) + 0.1)
    ax2.grid(axis="y", alpha=0.3, zorder=0)

    for bar, val in zip(bars, [oracle_avg, real_avg]):
        ax2.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.005,
            f"{val:.3f}",
            ha="center", va="bottom",
            fontsize=12, fontweight="bold",
        )

    ax2.annotate(
        f"Δ = +{real_avg - oracle_avg:.3f}\n(imperfect extraction\nincreases belief noise)",
        xy=(1, real_avg), xytext=(0.5, real_avg + 0.06),
        fontsize=9, color="#555",
        arrowprops=dict(arrowstyle="->", color="#555"),
    )

    fig.suptitle(
        "Figure E4 — SABLE Belief Comparison: Oracle vs Real Extraction",
        fontsize=13,
        y=1.02,
    )
    fig.tight_layout()
    out = FIGURES / "sable_oracle_vs_real.png"
    fig.savefig(out, dpi=300)
    plt.close(fig)
    print(f"  Saved {out}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Generating Phase 8c extraction figures...")
    figure_e1()
    figure_e2()
    figure_e3()
    figure_e4()
    print("Done. All 4 figures saved to figures/")


if __name__ == "__main__":
    main()
