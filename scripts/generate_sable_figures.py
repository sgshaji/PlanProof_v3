"""
Generate all 7 SABLE dissertation figures from updated ablation results.

Figures saved to figures/ at 300 DPI with dissertation-quality styling.
Run from the project root:
    python scripts/generate_sable_figures.py

Results reflect the corrected ablation study (2026-04-03):
- full_system: 0 false FAILs, 43 PASS, 2 true FAILs, 60 PA, 15 NA
- ablation_d: 43 false FAILs prevented by SABLE
- ablation_b == full_system (SNKG adds no value on current 7-rule corpus)
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
FIGURES = ROOT / "figures"
FIGURES.mkdir(exist_ok=True)
DATA = ROOT / "data" / "results"

ABLATION_CONFIGS = ["full_system", "ablation_a", "ablation_b", "ablation_c", "ablation_d"]

CONFIG_LABELS = {
    "full_system": "Full System",
    "ablation_a": "A: No VLM",
    "ablation_b": "B: No SNKG",
    "ablation_c": "C: No Gating",
    "ablation_d": "D: No SABLE",
}

CONFIG_COLORS = {
    "full_system": "#2196F3",
    "ablation_a": "#FF9800",
    "ablation_b": "#4CAF50",
    "ablation_c": "#9C27B0",
    "ablation_d": "#F44336",
}

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


# ── Data loading helpers ──────────────────────────────────────────────────────

def load_all_rule_results(config: str) -> list[dict]:
    """Load all rule-level result dicts for a given config."""
    config_dir = DATA / config
    if not config_dir.exists():
        return []
    results = []
    for f in sorted(config_dir.glob("*.json")):
        d = json.loads(f.read_text())
        for r in d.get("rule_results", []):
            r["set_id"] = d["set_id"]
            r["config_name"] = config
            results.append(r)
    return results


def load_data() -> dict[str, list[dict]]:
    return {cfg: load_all_rule_results(cfg) for cfg in ABLATION_CONFIGS}


def verdict_counts(results: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {"PASS": 0, "FAIL_true": 0, "FAIL_false": 0,
                               "PARTIALLY_ASSESSABLE": 0, "NOT_ASSESSABLE": 0}
    for r in results:
        pred = r["predicted_outcome"]
        gt = r["ground_truth_outcome"]
        if pred == "PASS":
            counts["PASS"] += 1
        elif pred == "FAIL":
            if gt == "FAIL":
                counts["FAIL_true"] += 1
            else:
                counts["FAIL_false"] += 1
        elif pred == "PARTIALLY_ASSESSABLE":
            counts["PARTIALLY_ASSESSABLE"] += 1
        elif pred == "NOT_ASSESSABLE":
            counts["NOT_ASSESSABLE"] += 1
    return counts


def beliefs_for(results: list[dict]) -> list[float]:
    return [r["belief"] for r in results if r.get("belief") is not None]


def plausibilities_for(results: list[dict]) -> list[float]:
    return [r["plausibility"] for r in results if r.get("plausibility") is not None]


# ── Figure 1: Belief distribution violin ─────────────────────────────────────

def figure_belief_violin(data: dict[str, list[dict]]) -> None:
    """Violin plot of SABLE belief distribution per config.

    Configs with no beliefs (ablation_a, ablation_d) are shown as NA strip.
    """
    fig, ax = plt.subplots(figsize=(12, 6))

    positions = []
    belief_sets = []
    colors_list = []
    x_labels = []

    pos = 1
    for cfg in ABLATION_CONFIGS:
        beliefs = beliefs_for(data[cfg])
        positions.append(pos)
        x_labels.append(CONFIG_LABELS[cfg])
        colors_list.append(CONFIG_COLORS[cfg])
        if beliefs:
            belief_sets.append(beliefs)
        else:
            belief_sets.append([0.0])  # placeholder so violin renders
        pos += 1

    parts = ax.violinplot(
        belief_sets,
        positions=positions,
        showmeans=True,
        showmedians=True,
        widths=0.7,
    )

    for pc, color in zip(parts["bodies"], colors_list):
        pc.set_facecolor(color)
        pc.set_alpha(0.65)

    parts["cmeans"].set_color("black")
    parts["cmedians"].set_color("darkred")

    # Mark configs with no actual beliefs
    no_belief_configs = [cfg for cfg in ABLATION_CONFIGS if not beliefs_for(data[cfg])]
    for i, cfg in enumerate(ABLATION_CONFIGS):
        if cfg in no_belief_configs:
            ax.text(i + 1, 0.05, "No SABLE\n(all NA)", ha="center", va="bottom",
                    fontsize=8, color="grey", style="italic")

    ax.set_xticks(positions)
    ax.set_xticklabels(x_labels)
    ax.set_ylabel("SABLE Belief Score")
    ax.set_ylim(-0.05, 1.1)
    ax.set_title("Figure S1 — SABLE Belief Distribution by Ablation Config\n"
                 "(full_system / ablation_b / c: two-cluster at 0.56 and 0.96; "
                 "ablation_a / d: no SABLE beliefs)")
    ax.axhline(0.75, color="grey", linewidth=0.8, linestyle="--", alpha=0.5,
               label="PASS threshold (0.75)")
    ax.axhline(0.25, color="orange", linewidth=0.8, linestyle=":", alpha=0.5,
               label="PA threshold (0.25)")
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.25)

    out = FIGURES / "sable_belief_violin.png"
    fig.savefig(out, dpi=300)
    plt.close(fig)
    print(f"  Saved {out}")


# ── Figure 2: Three-state stacked bar ────────────────────────────────────────

def figure_three_state_bar(data: dict[str, list[dict]]) -> None:
    """Stacked bar: ASSESSABLE(PASS+trueF)/PA/NA per config."""
    configs = ABLATION_CONFIGS
    labels = [CONFIG_LABELS[c] for c in configs]

    pass_counts = []
    true_fail_counts = []
    false_fail_counts = []
    pa_counts = []
    na_counts = []

    for cfg in configs:
        vc = verdict_counts(data[cfg])
        pass_counts.append(vc["PASS"])
        true_fail_counts.append(vc["FAIL_true"])
        false_fail_counts.append(vc["FAIL_false"])
        pa_counts.append(vc["PARTIALLY_ASSESSABLE"])
        na_counts.append(vc["NOT_ASSESSABLE"])

    x = np.arange(len(configs))
    width = 0.55

    fig, ax = plt.subplots(figsize=(13, 6))

    bottoms = np.zeros(len(configs))

    b1 = ax.bar(x, pass_counts, width, label="PASS (correct)", color="#4CAF50",
                bottom=bottoms)
    bottoms += np.array(pass_counts)

    b2 = ax.bar(x, true_fail_counts, width, label="FAIL (true violation)", color="#FF9800",
                bottom=bottoms)
    bottoms += np.array(true_fail_counts)

    b3 = ax.bar(x, false_fail_counts, width, label="FAIL (false — compliant case rejected)",
                color="#F44336", bottom=bottoms)
    bottoms += np.array(false_fail_counts)

    b4 = ax.bar(x, pa_counts, width, label="PARTIALLY_ASSESSABLE", color="#90CAF9",
                bottom=bottoms)
    bottoms += np.array(pa_counts)

    b5 = ax.bar(x, na_counts, width, label="NOT_ASSESSABLE", color="#BDBDBD",
                bottom=bottoms)

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Rule evaluations (n=120 per config)")
    ax.set_ylim(0, 135)
    ax.set_title("Figure S2 — Verdict Distribution by Ablation Configuration\n"
                 "(120 evaluations per config: 15 sets × 8 rules)")
    ax.legend(fontsize=9, loc="upper right")
    ax.grid(axis="y", alpha=0.25)

    # Annotate false FAILs in ablation_d
    d_idx = configs.index("ablation_d")
    ff = false_fail_counts[d_idx]
    if ff > 0:
        ax.annotate(
            f"{ff} false FAILs\n(SABLE prevents all)",
            xy=(d_idx, true_fail_counts[d_idx] + ff / 2 + true_fail_counts[d_idx]),
            xytext=(d_idx - 1.3, 80),
            arrowprops=dict(arrowstyle="->", color="#F44336"),
            fontsize=9, color="#F44336",
        )

    out = FIGURES / "sable_three_state_bar.png"
    fig.savefig(out, dpi=300)
    plt.close(fig)
    print(f"  Saved {out}")


# ── Figure 3: Belief vs plausibility scatter ─────────────────────────────────

def figure_belief_vs_plausibility(data: dict[str, list[dict]]) -> None:
    """Scatter: belief (x) vs plausibility (y) for configs that have SABLE scores."""
    configs_with_beliefs = [
        c for c in ABLATION_CONFIGS if beliefs_for(data[c])
    ]

    fig, ax = plt.subplots(figsize=(10, 7))

    for cfg in configs_with_beliefs:
        results_with_belief = [r for r in data[cfg] if r.get("belief") is not None
                               and r.get("plausibility") is not None]
        bs = [r["belief"] for r in results_with_belief]
        ps = [r["plausibility"] for r in results_with_belief]
        # Add small jitter to reveal overlapping points
        jitter = np.random.default_rng(42).normal(0, 0.008, len(bs))
        ax.scatter(
            np.array(bs) + jitter,
            np.array(ps) + jitter,
            label=CONFIG_LABELS[cfg],
            color=CONFIG_COLORS[cfg],
            alpha=0.6,
            s=35,
        )

    # Threshold lines
    ax.axvline(0.75, color="green", linewidth=1, linestyle="--", alpha=0.7,
               label="PASS belief threshold (0.75)")
    ax.axvline(0.25, color="orange", linewidth=1, linestyle=":", alpha=0.7,
               label="PA belief lower bound (0.25)")
    ax.axhline(0.75, color="green", linewidth=1, linestyle="--", alpha=0.4)

    # Quadrant labels
    ax.text(0.8, 0.05, "PASS\nzone", ha="center", color="green", fontsize=9)
    ax.text(0.5, 0.05, "PARTIALLY\nASSESSABLE", ha="center", color="#1565C0", fontsize=9)
    ax.text(0.1, 0.05, "NOT\nASSESSABLE", ha="center", color="grey", fontsize=9)

    ax.set_xlabel("Belief (m(PASS))")
    ax.set_ylabel("Plausibility (1 − m(FAIL))")
    ax.set_xlim(-0.05, 1.1)
    ax.set_ylim(-0.05, 1.1)
    ax.set_title("Figure S3 — Belief vs Plausibility Scatter\n"
                 "(two-cluster structure: C/R003 at 0.56, R001/R002/C004 at 0.96)")
    ax.legend(fontsize=9, loc="upper left")
    ax.grid(alpha=0.2)

    out = FIGURES / "sable_belief_vs_plausibility.png"
    fig.savefig(out, dpi=300)
    plt.close(fig)
    print(f"  Saved {out}")


# ── Figure 4: Blocking reason distribution ───────────────────────────────────

def figure_blocking_reasons(data: dict[str, list[dict]]) -> None:
    """Stacked bar of blocking reason counts per config."""
    configs = ABLATION_CONFIGS
    labels = [CONFIG_LABELS[c] for c in configs]

    reason_colors = {
        "NONE": "#4CAF50",
        "MISSING_EVIDENCE": "#FF9800",
        "LOW_CONFIDENCE": "#F44336",
        "HIGH_CONFLICT": "#9C27B0",
        "NO_VLM": "#607D8B",
    }

    # Collect all reasons
    all_reasons: set[str] = set()
    reason_data: dict[str, dict[str, int]] = {}

    for cfg in configs:
        reason_data[cfg] = {}
        for r in data[cfg]:
            reason = r.get("blocking_reason") or "NONE"
            reason_data[cfg][reason] = reason_data[cfg].get(reason, 0) + 1
            all_reasons.add(reason)

    reasons = sorted(all_reasons)
    x = np.arange(len(configs))
    width = 0.55

    fig, ax = plt.subplots(figsize=(13, 6))
    bottoms = np.zeros(len(configs))

    for reason in reasons:
        counts = [reason_data[cfg].get(reason, 0) for cfg in configs]
        color = reason_colors.get(reason, "#9E9E9E")
        ax.bar(x, counts, width, label=reason, color=color, bottom=bottoms, alpha=0.85)
        bottoms += np.array(counts, dtype=float)

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Count (n=120 per config)")
    ax.set_title("Figure S4 — Blocking Reason Distribution by Configuration\n"
                 "(full_system: 15 MISSING_EVIDENCE for C005, 105 NONE)")
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.25)

    out = FIGURES / "sable_blocking_reasons.png"
    fig.savefig(out, dpi=300)
    plt.close(fig)
    print(f"  Saved {out}")


# ── Figure 5: False-FAIL prevention ──────────────────────────────────────────

def figure_false_fail_prevention(data: dict[str, list[dict]]) -> None:
    """Bar chart: false FAILs in full_system (0) vs ablation_d (43)."""
    configs = ["full_system", "ablation_d"]
    labels = ["Full System\n(SABLE enabled)", "Ablation D\n(SABLE disabled)"]
    false_fails = [
        sum(1 for r in data[cfg] if r["predicted_outcome"] == "FAIL"
            and r["ground_truth_outcome"] == "PASS")
        for cfg in configs
    ]
    colors = [CONFIG_COLORS[c] for c in configs]

    fig, ax = plt.subplots(figsize=(8, 6))
    bars = ax.bar(labels, false_fails, color=colors, edgecolor="white", width=0.5, zorder=3)
    ax.set_ylabel("False FAIL count\n(compliant cases incorrectly rejected)")
    ax.set_title("Figure S5 — SABLE False-FAIL Prevention\n"
                 "(SABLE converts 43 false violations to PARTIALLY_ASSESSABLE)")
    ax.set_ylim(0, max(false_fails) + 15)
    ax.grid(axis="y", alpha=0.3, zorder=0)

    for bar, val in zip(bars, false_fails):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.8,
            str(val),
            ha="center", va="bottom",
            fontsize=18, fontweight="bold",
        )

    # Annotation
    ax.annotate(
        "SABLE prevents all 43\nfalse violations →\nconverted to PARTIALLY_ASSESSABLE",
        xy=(0, 1), xytext=(0.35, 28),
        arrowprops=dict(arrowstyle="->", color="#2196F3"),
        fontsize=9, color="#2196F3", ha="center",
    )

    out = FIGURES / "sable_false_fail_prevention.png"
    fig.savefig(out, dpi=300)
    plt.close(fig)
    print(f"  Saved {out}")


# ── Figure 6: Component contribution delta table ──────────────────────────────

def figure_component_contribution(data: dict[str, list[dict]]) -> None:
    """Visual table: delta metrics per ablation vs full_system."""
    configs = ["ablation_a", "ablation_b", "ablation_c", "ablation_d"]
    config_labels = [CONFIG_LABELS[c] for c in configs]
    components_removed = [
        "VLM extraction\n(no visual data)",
        "SNKG graph\n(flat matching fallback)",
        "Confidence gating\n(all evidence passes)",
        "Assessability engine\n(SABLE disabled)",
    ]

    # Compute delta false_FAILs vs full_system
    fs_ff = sum(1 for r in data["full_system"] if r["predicted_outcome"] == "FAIL"
                and r["ground_truth_outcome"] == "PASS")

    rows = []
    for cfg in configs:
        vc = verdict_counts(data[cfg])
        ff = vc["FAIL_false"]
        delta_ff = ff - fs_ff
        pass_ct = vc["PASS"]
        na_ct = vc["NOT_ASSESSABLE"]
        rows.append({
            "config": CONFIG_LABELS[cfg],
            "removed": components_removed[configs.index(cfg)],
            "false_fails": ff,
            "delta_ff": delta_ff,
            "pass": pass_ct,
            "na": na_ct,
            "effect": _effect_label(cfg, ff, pass_ct, na_ct),
        })

    fig, ax = plt.subplots(figsize=(14, 5))
    ax.axis("off")

    col_labels = [
        "Config", "Component Removed", "False FAILs\n(Δ vs full)", "PASS", "NA", "Key Effect"
    ]
    table_data = [
        [
            r["config"],
            r["removed"],
            f"{r['false_fails']} ({'+' if r['delta_ff'] >= 0 else ''}{r['delta_ff']})",
            str(r["pass"]),
            str(r["na"]),
            r["effect"],
        ]
        for r in rows
    ]

    # Add full_system as first row
    fs_vc = verdict_counts(data["full_system"])
    table_data.insert(0, [
        "Full System", "None (baseline)", "0 (baseline)",
        str(fs_vc["PASS"]), str(fs_vc["NOT_ASSESSABLE"]),
        "Baseline — 0 false FAILs, 43 PASS, 2 true FAILs"
    ])

    tbl = ax.table(
        cellText=table_data,
        colLabels=col_labels,
        cellLoc="center",
        loc="center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9)
    tbl.scale(1, 2.2)

    # Colour header and ablation_d false-FAIL cell
    for j in range(len(col_labels)):
        tbl[0, j].set_facecolor("#1565C0")
        tbl[0, j].set_text_props(color="white", fontweight="bold")

    # Highlight ablation_d row (index 4 in table = row 5 = ablation_d)
    for j in range(len(col_labels)):
        tbl[5, j].set_facecolor("#FFEBEE")

    ax.set_title(
        "Figure S6 — Ablation Component Contribution\n"
        "(ablation_d is the only config where SABLE removal causes false violations)",
        fontsize=12, pad=12,
    )

    out = FIGURES / "sable_component_contribution.png"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {out}")


def _effect_label(cfg: str, ff: int, pass_ct: int, na_ct: int) -> str:
    if cfg == "ablation_a":
        return "All 120 NOT_ASSESSABLE — no VLM means no evidence"
    if cfg == "ablation_b":
        return "Identical to full system — SNKG not exercised by 7-rule corpus"
    if cfg == "ablation_c":
        return "Identical to full system — confidence gating has no effect with oracle evidence"
    if cfg == "ablation_d":
        return f"+{ff} false FAILs — forced binary on insufficient evidence"
    return "—"


# ── Figure 7: Concordance heatmap (rule × config) ────────────────────────────

def figure_concordance_heatmap(data: dict[str, list[dict]]) -> None:
    """Heatmap: mean belief per (rule, config). Configs with no beliefs shown as grey."""
    rules = ["R001", "R002", "R003", "C001", "C002", "C003", "C004", "C005"]
    configs = ABLATION_CONFIGS
    config_labels_short = [CONFIG_LABELS[c] for c in configs]

    matrix = np.full((len(rules), len(configs)), np.nan)

    for j, cfg in enumerate(configs):
        rule_belief_map: dict[str, list[float]] = {}
        for r in data[cfg]:
            rule = r["rule_id"]
            b = r.get("belief")
            if b is not None:
                rule_belief_map.setdefault(rule, []).append(b)
        for i, rule in enumerate(rules):
            if rule in rule_belief_map:
                matrix[i, j] = np.mean(rule_belief_map[rule])

    fig, ax = plt.subplots(figsize=(13, 7))

    # Use masked array so NaN shows as grey
    masked = np.ma.masked_invalid(matrix)
    cmap = plt.cm.RdYlGn  # type: ignore[attr-defined]
    cmap.set_bad(color="#BDBDBD")

    im = ax.imshow(masked, cmap=cmap, vmin=0.0, vmax=1.0, aspect="auto")

    ax.set_xticks(range(len(configs)))
    ax.set_xticklabels(config_labels_short, fontsize=10)
    ax.set_yticks(range(len(rules)))
    ax.set_yticklabels(rules, fontsize=10)
    ax.set_title("Figure S7 — Concordance Heatmap: Mean SABLE Belief (Rule × Config)\n"
                 "(grey = no SABLE beliefs for that config; "
                 "green = high belief; red = low; ablation_a/d show no SABLE output)")

    # Annotate each cell
    for i in range(len(rules)):
        for j in range(len(configs)):
            val = matrix[i, j]
            if not np.isnan(val):
                text_color = "white" if val < 0.35 or val > 0.8 else "black"
                ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                        fontsize=9, color=text_color, fontweight="bold")
            else:
                ax.text(j, i, "—", ha="center", va="center",
                        fontsize=11, color="white")

    plt.colorbar(im, ax=ax, label="Mean Belief Score", fraction=0.03, pad=0.02)

    out = FIGURES / "sable_concordance_heatmap.png"
    fig.savefig(out, dpi=300)
    plt.close(fig)
    print(f"  Saved {out}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Loading ablation results...")
    data = load_data()
    for cfg, results in data.items():
        print(f"  {cfg}: {len(results)} rule evaluations loaded")

    print("\nGenerating SABLE figures...")
    figure_belief_violin(data)
    figure_three_state_bar(data)
    figure_belief_vs_plausibility(data)
    figure_blocking_reasons(data)
    figure_false_fail_prevention(data)
    figure_component_contribution(data)
    figure_concordance_heatmap(data)

    print(f"\nDone. All 7 figures saved to {FIGURES}/")


if __name__ == "__main__":
    main()
