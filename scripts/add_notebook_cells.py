"""Add Phase 8c extraction evaluation cells to ablation_analysis.ipynb."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NB_PATH = ROOT / "notebooks" / "ablation_analysis.ipynb"

nb = json.loads(NB_PATH.read_text())

new_cells = [
    # ── Markdown section header ───────────────────────────────────────────────
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": (
            "## Extraction Evaluation\n"
            "\n"
            "Phase 8c measures extraction accuracy independently from reasoning accuracy, "
            "then feeds real (imperfect) extractions into the reasoning pipeline to attribute "
            "errors to their root cause: extraction failure vs reasoning failure.\n"
            "\n"
            "**Test corpus:** 5 synthetic test sets (2 compliant, 2 non-compliant, 1 edge-case), "
            "v1 and v2 prompts.  \n"
            "**Target attributes:** building_height, rear_garden_depth, site_coverage, "
            "site_address, site_area.  \n"
            "**Key finding:** Narrowing the prompt from broad entity types to 7 specific attributes "
            "eliminated 73% of hallucinations without losing any real entities "
            "(recall unchanged at 0.886).\n"
        ),
    },
    # ── Setup cell ───────────────────────────────────────────────────────────
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": (
            "# -- Extraction Evaluation setup --\n"
            "import json\n"
            "from pathlib import Path\n"
            "import numpy as np\n"
            "import matplotlib.pyplot as plt\n"
            "\n"
            "EXTRACTION_V1 = Path('../data/results/extraction/v1')\n"
            "EXTRACTION_V2 = Path('../data/results/extraction/v2')\n"
            "FULL_SYS      = Path('../data/results/full_system')\n"
            "EXTR_ABL      = Path('../data/results/extraction_ablation')\n"
            "FIGURES       = Path('../figures')\n"
            "\n"
            "def load_extraction(directory):\n"
            "    return [json.loads(f.read_text()) for f in sorted(directory.glob('*.json'))]\n"
            "\n"
            "def avg_per_attribute(results):\n"
            "    acc = {}\n"
            "    for d in results:\n"
            "        for attr, stats in d.get('per_attribute', {}).items():\n"
            "            if attr not in acc:\n"
            "                acc[attr] = {'recall': [], 'precision': [], 'value_accuracy': []}\n"
            "            for k in ['recall', 'precision', 'value_accuracy']:\n"
            "                acc[attr][k].append(stats[k])\n"
            "    return {a: {k: sum(v)/len(v) for k,v in m.items()} for a, m in acc.items()}\n"
            "\n"
            "def overall_avg(results):\n"
            "    keys = ['recall', 'precision', 'value_accuracy']\n"
            "    return {k: sum(d[k] for d in results)/len(results) for k in keys}\n"
            "\n"
            "def per_set_beliefs(directory):\n"
            "    beliefs = []\n"
            "    for f in sorted(directory.glob('*.json')):\n"
            "        d = json.loads(f.read_text())\n"
            "        for r in d.get('rule_results', []):\n"
            "            b = r.get('belief')\n"
            "            if b is not None:\n"
            "                beliefs.append(b)\n"
            "    return beliefs\n"
            "\n"
            "v1_results = load_extraction(EXTRACTION_V1)\n"
            "v2_results = load_extraction(EXTRACTION_V2)\n"
            "v1_avg = overall_avg(v1_results)\n"
            "v2_avg = overall_avg(v2_results)\n"
            "print('v1:', {k: round(v, 3) for k, v in v1_avg.items()})\n"
            "print('v2:', {k: round(v, 3) for k, v in v2_avg.items()})\n"
            "print(f'Precision delta: {v2_avg[\"precision\"] - v1_avg[\"precision\"]:.3f}')\n"
        ),
    },
    # ── Figure E1 markdown ────────────────────────────────────────────────────
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": "### Figure E1 — Per-Attribute Extraction Accuracy (v1 vs v2)",
    },
    # ── Figure E1 code ────────────────────────────────────────────────────────
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": (
            "# -- Figure E1: Per-attribute grouped bar --\n"
            "v1_attrs = avg_per_attribute(v1_results)\n"
            "v2_attrs = avg_per_attribute(v2_results)\n"
            "\n"
            "target_attrs = ['building_height', 'rear_garden_depth', 'site_coverage',\n"
            "                'site_address', 'site_area']\n"
            "labels = [a.replace('_', '\\n') for a in target_attrs]\n"
            "\n"
            "v1_recall = [v1_attrs.get(a, {}).get('recall', 0.0) for a in target_attrs]\n"
            "v2_recall = [v2_attrs.get(a, {}).get('recall', 0.0) for a in target_attrs]\n"
            "v1_va     = [v1_attrs.get(a, {}).get('value_accuracy', 0.0) for a in target_attrs]\n"
            "v2_va     = [v2_attrs.get(a, {}).get('value_accuracy', 0.0) for a in target_attrs]\n"
            "\n"
            "x = np.arange(len(target_attrs))\n"
            "width = 0.2\n"
            "\n"
            "fig, ax = plt.subplots(figsize=(13, 6))\n"
            "ax.bar(x - 1.5*width, v1_recall, width, label='v1 Recall',\n"
            "       color='#90CAF9', edgecolor='white')\n"
            "ax.bar(x - 0.5*width, v2_recall, width, label='v2 Recall',\n"
            "       color='#1565C0', edgecolor='white')\n"
            "ax.bar(x + 0.5*width, v1_va, width, label='v1 Value Accuracy',\n"
            "       color='#FFCC80', edgecolor='white')\n"
            "ax.bar(x + 1.5*width, v2_va, width, label='v2 Value Accuracy',\n"
            "       color='#E65100', edgecolor='white')\n"
            "\n"
            "ax.set_xticks(x)\n"
            "ax.set_xticklabels(labels, fontsize=9)\n"
            "ax.set_ylim(0, 1.15)\n"
            "ax.set_ylabel('Score')\n"
            "ax.set_xlabel('Attribute')\n"
            "ax.set_title('Figure E1 -- Per-Attribute Extraction Accuracy (v1 vs v2)')\n"
            "ax.legend(fontsize=9, ncol=2)\n"
            "ax.axhline(1.0, color='grey', linewidth=0.5, linestyle='--', alpha=0.5)\n"
            "\n"
            "fig.tight_layout()\n"
            "fig.savefig(FIGURES / 'extraction_accuracy.png', dpi=300)\n"
            "plt.show()\n"
            "print('Saved figures/extraction_accuracy.png')\n"
        ),
    },
    # ── Figure E2 markdown ────────────────────────────────────────────────────
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": "### Figure E2 — Extraction Improvement: v1 → v2 Delta",
    },
    # ── Figure E2 code ────────────────────────────────────────────────────────
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": (
            "# -- Figure E2: v1 to v2 delta bar chart --\n"
            "metrics = ['recall', 'precision', 'value_accuracy']\n"
            "metric_labels = ['Recall', 'Precision', 'Value Accuracy']\n"
            "deltas = [v2_avg[m] - v1_avg[m] for m in metrics]\n"
            "\n"
            "colors = ['#4CAF50' if d >= 0 else '#F44336' for d in deltas]\n"
            "colors[1] = '#1565C0'  # precision is the headline improvement\n"
            "\n"
            "fig, ax = plt.subplots(figsize=(8, 5))\n"
            "bars = ax.bar(metric_labels, deltas, color=colors, edgecolor='white', zorder=3)\n"
            "ax.axhline(0, color='black', linewidth=0.8)\n"
            "ax.set_ylabel('Delta Score (v2 minus v1)')\n"
            "ax.set_title('Figure E2 -- Extraction Improvement: v1 to v2')\n"
            "ax.set_ylim(-0.1, max(deltas) + 0.15)\n"
            "ax.grid(axis='y', alpha=0.3, zorder=0)\n"
            "\n"
            "for bar, delta in zip(bars, deltas):\n"
            "    sign = '+' if delta >= 0 else ''\n"
            "    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,\n"
            "            f'{sign}{delta:.3f}', ha='center', va='bottom',\n"
            "            fontsize=11, fontweight='bold')\n"
            "\n"
            "ax.annotate('Precision +0.416\\n(hallucination elimination)',\n"
            "            xy=(1, deltas[1]), xytext=(1.6, deltas[1] + 0.05),\n"
            "            arrowprops=dict(arrowstyle='->', color='#1565C0'),\n"
            "            fontsize=9, color='#1565C0')\n"
            "\n"
            "fig.tight_layout()\n"
            "fig.savefig(FIGURES / 'extraction_v1_v2_delta.png', dpi=300)\n"
            "plt.show()\n"
            "print('Saved figures/extraction_v1_v2_delta.png')\n"
        ),
    },
    # ── Figure E3 markdown ────────────────────────────────────────────────────
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": (
            "### Figure E3 — 2x2 False-FAIL Matrix\n"
            "\n"
            "Rows: extraction type (oracle / real). Columns: system config (full_system / ablation_d). "
            "Cells: false FAIL counts across 5 test sets.\n"
            "\n"
            "The full system column reads **0, 0** — SABLE eliminates false FAILs regardless of "
            "extraction quality."
        ),
    },
    # ── Figure E3 code ────────────────────────────────────────────────────────
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": (
            "# -- Figure E3: 2x2 False-FAIL Matrix heatmap --\n"
            "matrix = np.array([\n"
            "    [0, 100],   # oracle extraction: full_system=0, ablation_d=100\n"
            "    [0,  26],   # real extraction:   full_system=0, ablation_d=26\n"
            "])\n"
            "\n"
            "row_labels = ['Oracle Extraction\\n(SABLE enabled)', 'Real Extraction\\n(SABLE enabled)']\n"
            "col_labels = ['Full System\\n(SABLE on)', 'Ablation D\\n(SABLE off)']\n"
            "\n"
            "fig, ax = plt.subplots(figsize=(8, 5))\n"
            "im = ax.imshow(matrix, cmap=plt.cm.Reds, vmin=0, vmax=110, aspect='auto')\n"
            "\n"
            "ax.set_xticks([0, 1])\n"
            "ax.set_yticks([0, 1])\n"
            "ax.set_xticklabels(col_labels, fontsize=11)\n"
            "ax.set_yticklabels(row_labels, fontsize=11)\n"
            "ax.set_title('Figure E3 -- 2x2 False-FAIL Matrix\\n(compliant cases incorrectly rejected)')\n"
            "\n"
            "for i in range(2):\n"
            "    for j in range(2):\n"
            "        val = matrix[i, j]\n"
            "        tc = 'white' if val > 50 else 'black'\n"
            "        ax.text(j, i, str(val), ha='center', va='center',\n"
            "                fontsize=18, fontweight='bold', color=tc)\n"
            "\n"
            "fig.colorbar(im, ax=ax, label='False FAIL count')\n"
            "fig.tight_layout()\n"
            "fig.savefig(FIGURES / 'false_fail_matrix.png', dpi=300)\n"
            "plt.show()\n"
            "print('Saved figures/false_fail_matrix.png')\n"
        ),
    },
    # ── Figure E4 markdown ────────────────────────────────────────────────────
    {
        "cell_type": "markdown",
        "metadata": {},
        "source": (
            "### Figure E4 — SABLE Belief: Oracle vs Real Extraction\n"
            "\n"
            "Oracle extraction avg belief: **0.150** | Real extraction avg belief: **0.170**\n"
            "\n"
            "The delta is small (+0.020), confirming that extraction imperfection has only a "
            "bounded effect on SABLE's evidence aggregation."
        ),
    },
    # ── Figure E4 code ────────────────────────────────────────────────────────
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": (
            "# -- Figure E4: SABLE belief comparison oracle vs real --\n"
            "oracle_beliefs = per_set_beliefs(FULL_SYS)\n"
            "real_beliefs   = per_set_beliefs(EXTR_ABL)\n"
            "\n"
            "oracle_avg_b = sum(oracle_beliefs) / len(oracle_beliefs)\n"
            "real_avg_b   = sum(real_beliefs)   / len(real_beliefs)\n"
            "print(f'Oracle avg belief:          {oracle_avg_b:.3f}')\n"
            "print(f'Real extraction avg belief: {real_avg_b:.3f}')\n"
            "print(f'Delta:                      {real_avg_b - oracle_avg_b:+.3f}')\n"
            "\n"
            "fig, axes = plt.subplots(1, 2, figsize=(13, 6))\n"
            "\n"
            "# Left: box plots\n"
            "ax = axes[0]\n"
            "bp = ax.boxplot([oracle_beliefs, real_beliefs],\n"
            "                tick_labels=['Oracle\\nExtraction', 'Real\\nExtraction'],\n"
            "                patch_artist=True,\n"
            "                medianprops=dict(color='black', linewidth=2))\n"
            "bp['boxes'][0].set_facecolor('#BBDEFB')\n"
            "bp['boxes'][1].set_facecolor('#EF9A9A')\n"
            "ax.set_ylabel('SABLE Belief Score')\n"
            "ax.set_title('Belief Score Distribution')\n"
            "ax.set_ylim(-0.05, 1.05)\n"
            "ax.axhline(oracle_avg_b, color='#1565C0', linestyle='--', alpha=0.6,\n"
            "           linewidth=1.5, label=f'Oracle mean={oracle_avg_b:.3f}')\n"
            "ax.axhline(real_avg_b, color='#C62828', linestyle='--', alpha=0.6,\n"
            "           linewidth=1.5, label=f'Real mean={real_avg_b:.3f}')\n"
            "ax.legend(fontsize=9)\n"
            "\n"
            "# Right: mean bar comparison\n"
            "ax2 = axes[1]\n"
            "bars = ax2.bar(['Oracle Extraction', 'Real Extraction'],\n"
            "               [oracle_avg_b, real_avg_b],\n"
            "               color=['#BBDEFB', '#EF9A9A'], edgecolor='white', zorder=3)\n"
            "ax2.set_ylabel('Average SABLE Belief Score')\n"
            "ax2.set_title('Average Belief: Oracle vs Real Extraction')\n"
            "ax2.set_ylim(0, max(oracle_avg_b, real_avg_b) + 0.1)\n"
            "ax2.grid(axis='y', alpha=0.3, zorder=0)\n"
            "for bar, val in zip(bars, [oracle_avg_b, real_avg_b]):\n"
            "    ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.005,\n"
            "             f'{val:.3f}', ha='center', va='bottom',\n"
            "             fontsize=12, fontweight='bold')\n"
            "\n"
            "fig.suptitle('Figure E4 -- SABLE Belief Comparison: Oracle vs Real Extraction',\n"
            "             fontsize=13, y=1.02)\n"
            "fig.tight_layout()\n"
            "fig.savefig(FIGURES / 'sable_oracle_vs_real.png', dpi=300)\n"
            "plt.show()\n"
            "print('Saved figures/sable_oracle_vs_real.png')\n"
        ),
    },
]

nb["cells"].extend(new_cells)

NB_PATH.write_text(json.dumps(nb, indent=1))
print(f"Notebook updated: {len(nb['cells'])} cells (was 39)")
