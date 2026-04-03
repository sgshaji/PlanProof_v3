"""Extraction-quality robustness curve runner.

Runs the ablation pipeline at 5 degradation levels for two configs
(full_system and ablation_d) to show how the system degrades under
increasingly noisy extraction.

Usage::

    python scripts/run_robustness.py
    python scripts/run_robustness.py --data-dir data/synthetic_diverse --output-dir data/results/robustness
    python scripts/run_robustness.py --configs-dir configs

After running, call ``python scripts/generate_robustness_figures.py`` to
produce the robustness curve plots, or pass ``--figures`` to generate them
inline.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s  %(name)s  %(message)s",
    stream=sys.stderr,
)
_log = logging.getLogger("run_robustness")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Degradation levels
# ---------------------------------------------------------------------------

# Import here so the module is importable even if planproof isn't on sys.path yet.
# The actual import is deferred to _run_level() so the script fails gracefully.

DEGRADATION_LEVELS_RAW = [
    # (value_noise_pct, entity_dropout_pct, confidence_noise_std, attribute_swap_pct)
    (0.00, 0.00, 0.00, 0.00),  # Level 0: Oracle
    (0.05, 0.05, 0.05, 0.00),  # Level 1: Mild
    (0.10, 0.10, 0.10, 0.00),  # Level 2: Moderate
    (0.20, 0.15, 0.15, 0.00),  # Level 3: Heavy
    (0.30, 0.25, 0.20, 0.00),  # Level 4: Severe
]

LEVEL_LABELS = ["Oracle", "Mild", "Moderate", "Heavy", "Severe"]

# Configs to evaluate for the robustness study
ROBUSTNESS_CONFIGS = ["full_system", "ablation_d"]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run extraction-quality robustness curves for PlanProof.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=ROOT / "data" / "synthetic_diverse",
        help="Root directory containing test set sub-directories.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data" / "results" / "robustness",
        help="Directory for robustness result JSON files.",
    )
    parser.add_argument(
        "--configs-dir",
        type=Path,
        default=ROOT / "configs",
        help="Directory containing ablation YAML configs and rules sub-directory.",
    )
    parser.add_argument(
        "--figures",
        action="store_true",
        help="Generate robustness curve figures after running experiments.",
    )
    parser.add_argument(
        "--figures-dir",
        type=Path,
        default=ROOT / "figures",
        help="Directory to save figures.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for the NoisyEntityTransformer.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable INFO-level logging.",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Reuse ablation runner helpers via import
# ---------------------------------------------------------------------------


def _import_ablation_helpers():
    """Import helpers from run_ablation.py by adding scripts/ to sys.path."""
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

    import run_ablation  # type: ignore[import]

    return run_ablation


# ---------------------------------------------------------------------------
# Pipeline runner with noisy entities
# ---------------------------------------------------------------------------


def _run_pipeline_with_noise(
    config_name: str,
    ground_truth: dict[str, Any],
    ablation_yaml: dict[str, Any],
    configs_dir: Path,
    test_set_dir: Path,
    transformer: Any,  # NoisyEntityTransformer
) -> tuple[list[Any], list[Any]]:
    """Run the reasoning pipeline with noise applied to ground-truth entities.

    Mirrors _run_pipeline_config from run_ablation.py but applies the noisy
    transformer after entity construction and before normalisation.

    Returns (verdicts, assessability_results).
    """
    from planproof.reasoning.assessability import DefaultAssessabilityEvaluator
    from planproof.reasoning.confidence import ThresholdConfidenceGate
    from planproof.reasoning.evaluators.attribute_diff import AttributeDiffEvaluator
    from planproof.reasoning.evaluators.boundary_verification import BoundaryVerificationEvaluator
    from planproof.reasoning.evaluators.enum_check import EnumCheckEvaluator
    from planproof.reasoning.evaluators.factory import RuleFactory
    from planproof.reasoning.evaluators.fuzzy_match import FuzzyMatchEvaluator
    from planproof.reasoning.evaluators.numeric_threshold import NumericThresholdEvaluator
    from planproof.reasoning.evaluators.numeric_tolerance import NumericToleranceEvaluator
    from planproof.reasoning.evaluators.ratio_threshold import RatioThresholdEvaluator
    from planproof.representation.flat_evidence import FlatEvidenceProvider
    from planproof.representation.normalisation import Normaliser
    from planproof.schemas.entities import ExtractedEntity
    from planproof.schemas.reconciliation import ReconciledEvidence, ReconciliationStatus
    from planproof.reasoning.reconciliation import PairwiseReconciler

    ablation_helpers = _import_ablation_helpers()

    # Register all evaluator types
    factory = RuleFactory()
    RuleFactory.register_evaluator("numeric_threshold", NumericThresholdEvaluator)
    RuleFactory.register_evaluator("ratio_threshold", RatioThresholdEvaluator)
    RuleFactory.register_evaluator("enum_check", EnumCheckEvaluator)
    RuleFactory.register_evaluator("fuzzy_string_match", FuzzyMatchEvaluator)
    RuleFactory.register_evaluator("numeric_tolerance", NumericToleranceEvaluator)
    RuleFactory.register_evaluator("attribute_diff", AttributeDiffEvaluator)
    RuleFactory.register_evaluator("boundary_verification", BoundaryVerificationEvaluator)

    # --- Build oracle entities ---
    entities = ablation_helpers._build_entities_from_ground_truth(
        ground_truth, test_set_dir=test_set_dir
    )

    # --- Apply noise ---
    entities = transformer.transform(entities)

    # --- Normalisation ---
    normaliser = Normaliser()
    entities = normaliser.normalise_all(entities)

    # --- Evidence provider ---
    evidence_provider = FlatEvidenceProvider(entities)

    # --- Reconciler ---
    reconciler = PairwiseReconciler()

    # --- Confidence gate ---
    confidence_thresholds_path = configs_dir / "confidence_thresholds.yaml"
    if confidence_thresholds_path.exists():
        confidence_gate = ThresholdConfidenceGate.from_yaml(confidence_thresholds_path)
    else:
        confidence_gate = ThresholdConfidenceGate(thresholds={})

    # --- Confidence gating (optional) ---
    if ablation_yaml.get("use_confidence_gating", True):
        entities = confidence_gate.filter_trusted(entities)
        evidence_provider.update_entities(entities)

    # --- Reconciliation ---
    reconciled_evidence: dict[str, ReconciledEvidence] = {}
    if ablation_yaml.get("use_evidence_reconciliation", True):
        groups: dict[str, list[ExtractedEntity]] = {}
        for entity in entities:
            key = entity.attribute if entity.attribute is not None else entity.entity_type.value
            groups.setdefault(key, []).append(entity)
        for attr, group in groups.items():
            reconciled_evidence[attr] = reconciler.reconcile(group, attr)

    # --- Load rules ---
    rules_dir = configs_dir / "rules"
    loaded_rule_pairs = factory.load_rules(rules_dir)
    rules_dict = {cfg.rule_id: cfg for cfg, _ in loaded_rule_pairs}
    all_rule_ids = list(rules_dict.keys())

    # --- Assessability ---
    assessability_results: list[Any] = []
    assessable_ids: set[str]

    if ablation_yaml.get("use_assessability_engine", True):
        assessability_evaluator = DefaultAssessabilityEvaluator(
            evidence_provider=evidence_provider,
            confidence_gate=confidence_gate,
            reconciler=reconciler,
            rules=rules_dict,
        )
        for rule_id in all_rule_ids:
            result = assessability_evaluator.evaluate(rule_id)
            assessability_results.append(result)
        assessable_ids = {r.rule_id for r in assessability_results if r.status == "ASSESSABLE"}
    else:
        assessable_ids = set(all_rule_ids)

    # --- Rule evaluation ---
    verdicts: list[Any] = []

    if not ablation_yaml.get("use_rule_engine", True):
        return verdicts, assessability_results

    fallback_missing = ReconciledEvidence(
        attribute="__fallback__",
        status=ReconciliationStatus.MISSING,
        sources=[],
    )

    for config, evaluator in loaded_rule_pairs:
        if config.rule_id not in assessable_ids:
            continue
        attrs_list = config.parameters.get("attributes", [])
        primary_attr = (
            config.parameters.get("attribute")
            or config.parameters.get("numerator_attribute")
            or config.parameters.get("attribute_a")
            or (f"proposed_{attrs_list[0]}" if attrs_list else None)
            or config.rule_id
        )
        evidence = reconciled_evidence.get(primary_attr, fallback_missing)
        params_with_id = {**config.parameters, "rule_id": config.rule_id}
        verdict = evaluator.evaluate(evidence, params_with_id)
        verdicts.append(verdict)

    return verdicts, assessability_results


# ---------------------------------------------------------------------------
# Single level runner
# ---------------------------------------------------------------------------


def _run_level(
    level_idx: int,
    config_name: str,
    test_sets: list[Path],
    configs_dir: Path,
    output_dir: Path,
    seed: int,
) -> dict[str, Any]:
    """Run one (degradation_level, config_name) combination across all test sets.

    Returns an aggregate result dict with verdict counts and per-set details.
    """
    import yaml

    from planproof.evaluation.noisy_transformer import DegradationConfig, NoisyEntityTransformer

    v_noise, dropout, c_noise, swap = DEGRADATION_LEVELS_RAW[level_idx]
    deg_cfg = DegradationConfig(
        value_noise_pct=v_noise,
        entity_dropout_pct=dropout,
        confidence_noise_std=c_noise,
        attribute_swap_pct=swap,
    )
    transformer = NoisyEntityTransformer(deg_cfg, seed=seed)

    ablation_helpers = _import_ablation_helpers()

    # Load ablation YAML
    ablation_yaml = ablation_helpers._load_ablation_config(configs_dir, config_name)

    # Load all rule IDs
    from planproof.reasoning.evaluators.attribute_diff import AttributeDiffEvaluator
    from planproof.reasoning.evaluators.boundary_verification import BoundaryVerificationEvaluator
    from planproof.reasoning.evaluators.enum_check import EnumCheckEvaluator
    from planproof.reasoning.evaluators.factory import RuleFactory
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
    RuleFactory.register_evaluator("boundary_verification", BoundaryVerificationEvaluator)
    all_rule_ids = [cfg.rule_id for cfg, _ in factory.load_rules(configs_dir / "rules")]

    aggregate = {
        "level": level_idx,
        "level_label": LEVEL_LABELS[level_idx],
        "config_name": config_name,
        "degradation": {
            "value_noise_pct": v_noise,
            "entity_dropout_pct": dropout,
            "confidence_noise_std": c_noise,
            "attribute_swap_pct": swap,
        },
        "counts": {"PASS": 0, "FAIL_true": 0, "FAIL_false": 0, "NOT_ASSESSABLE": 0, "PARTIALLY_ASSESSABLE": 0},
        "per_set": [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    for test_set_dir in test_sets:
        ground_truth = ablation_helpers.load_ground_truth(test_set_dir)
        set_id: str = ground_truth.get("set_id", test_set_dir.name)
        gt_verdicts: dict[str, str] = {
            v["rule_id"]: v["outcome"]
            for v in ground_truth.get("rule_verdicts", [])
        }

        try:
            verdicts, assessability_results = _run_pipeline_with_noise(
                config_name=config_name,
                ground_truth=ground_truth,
                ablation_yaml=ablation_yaml,
                configs_dir=configs_dir,
                test_set_dir=test_set_dir,
                transformer=transformer,
            )
        except Exception as exc:  # noqa: BLE001
            _log.error("Error on %s / %s / level %d: %s", config_name, set_id, level_idx, exc)
            continue

        evaluated_map = {v.rule_id: str(v.outcome) for v in verdicts}
        assessability_map = {ar.rule_id: ar for ar in assessability_results}

        set_counts = {"PASS": 0, "FAIL_true": 0, "FAIL_false": 0, "NOT_ASSESSABLE": 0, "PARTIALLY_ASSESSABLE": 0}

        for rule_id in all_rule_ids:
            gt = gt_verdicts.get(rule_id, "PASS")
            ar = assessability_map.get(rule_id)

            if rule_id in evaluated_map:
                pred = evaluated_map[rule_id]
            else:
                # Check if PARTIALLY_ASSESSABLE
                if ar and ar.status == "PARTIALLY_ASSESSABLE":
                    pred = "PARTIALLY_ASSESSABLE"
                else:
                    pred = "NOT_ASSESSABLE"

            if pred == "PASS":
                set_counts["PASS"] += 1
            elif pred == "FAIL":
                if gt == "FAIL":
                    set_counts["FAIL_true"] += 1
                else:
                    set_counts["FAIL_false"] += 1
            elif pred == "PARTIALLY_ASSESSABLE":
                set_counts["PARTIALLY_ASSESSABLE"] += 1
            else:
                set_counts["NOT_ASSESSABLE"] += 1

        for k, v in set_counts.items():
            aggregate["counts"][k] += v

        aggregate["per_set"].append({"set_id": set_id, "counts": set_counts})

    return aggregate


# ---------------------------------------------------------------------------
# Save result
# ---------------------------------------------------------------------------


def _save_result(result: dict[str, Any], output_dir: Path) -> Path:
    """Save a robustness result dict to JSON and return the path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    level = result["level"]
    config = result["config_name"]
    deg = result["degradation"]
    label = (
        f"v{int(deg['value_noise_pct'] * 100):02d}"
        f"_d{int(deg['entity_dropout_pct'] * 100):02d}"
        f"_c{int(deg['confidence_noise_std'] * 100):02d}"
    )
    filename = f"level_{level}_{config}_{label}.json"
    dest = output_dir / filename
    dest.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return dest


# ---------------------------------------------------------------------------
# Figure generation
# ---------------------------------------------------------------------------


def generate_figures(results: list[dict[str, Any]], figures_dir: Path) -> None:
    """Generate robustness curve figures from collected results."""
    import matplotlib.pyplot as plt
    import numpy as np

    figures_dir.mkdir(parents=True, exist_ok=True)

    # Dissertation style
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
        "ablation_d": "#F44336",
    }
    CONFIG_LABELS = {
        "full_system": "Full System (with SABLE)",
        "ablation_d": "Ablation D (no SABLE)",
    }

    # Group results by (config_name, level)
    by_config: dict[str, dict[int, dict]] = {}
    for r in results:
        cfg = r["config_name"]
        lvl = r["level"]
        by_config.setdefault(cfg, {})[lvl] = r

    x = list(range(len(DEGRADATION_LEVELS_RAW)))
    x_labels = LEVEL_LABELS

    # ------------------------------------------------------------------
    # Figure 1: False FAILs and true FAILs vs degradation level
    # ------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(9, 5))

    for cfg in ROBUSTNESS_CONFIGS:
        if cfg not in by_config:
            continue
        false_fails = [by_config[cfg].get(lvl, {}).get("counts", {}).get("FAIL_false", 0) for lvl in x]
        true_fails = [by_config[cfg].get(lvl, {}).get("counts", {}).get("FAIL_true", 0) for lvl in x]
        color = CONFIG_COLORS[cfg]
        label = CONFIG_LABELS[cfg]
        ax.plot(x, false_fails, marker="o", color=color, label=f"{label} — false FAILs", linewidth=2)
        ax.plot(x, true_fails, marker="s", color=color, linestyle="--",
                label=f"{label} — true FAILs", linewidth=1.5, alpha=0.7)

    ax.set_xticks(x)
    ax.set_xticklabels(x_labels)
    ax.set_xlabel("Degradation Level")
    ax.set_ylabel("Count (across all test sets)")
    ax.set_title("System Robustness Under Extraction Degradation\n"
                 "False FAILs (solid) and True FAILs (dashed) vs. Noise Level")
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    ax.set_ylim(bottom=0)

    out = figures_dir / "robustness_curves.png"
    fig.savefig(out, dpi=300)
    plt.close(fig)
    print(f"  Saved {out}")

    # ------------------------------------------------------------------
    # Figure 2: F2 score vs degradation level
    # ------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(8, 5))

    for cfg in ROBUSTNESS_CONFIGS:
        if cfg not in by_config:
            continue
        f2_scores = []
        for lvl in x:
            r = by_config[cfg].get(lvl, {})
            counts = r.get("counts", {})
            tp = counts.get("FAIL_true", 0)
            fp = counts.get("FAIL_false", 0)
            # Precision from TP and FP counts.
            # Recall approximation: FN (ground-truth FAILs predicted as PASS/NA) is not
            # tracked separately per level; we treat recall = 1.0 when TP > 0, else 0.0.
            # This is a conservative upper-bound approximation suitable for this figure.
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = 1.0 if tp > 0 else 0.0
            denom = 4 * precision + recall
            f2 = (5 * precision * recall) / denom if denom > 0 else 0.0
            f2_scores.append(f2)

        color = CONFIG_COLORS[cfg]
        label = CONFIG_LABELS[cfg]
        ax.plot(x, f2_scores, marker="o", color=color, label=label, linewidth=2)

    ax.set_xticks(x)
    ax.set_xticklabels(x_labels)
    ax.set_xlabel("Degradation Level")
    ax.set_ylabel("F2 Score (approx.)")
    ax.set_title("F2 Score vs. Extraction Degradation Level\n"
                 "(Full System vs. No-SABLE Ablation)")
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    ax.set_ylim(0, 1.05)

    out = figures_dir / "robustness_f2.png"
    fig.savefig(out, dpi=300)
    plt.close(fig)
    print(f"  Saved {out}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    args = _parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)
        _log.setLevel(logging.INFO)

    # Ensure planproof package is importable
    src_dir = ROOT / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    ablation_helpers = _import_ablation_helpers()

    # Discover test sets
    test_sets = ablation_helpers.discover_test_sets(args.data_dir)
    if not test_sets:
        print(f"ERROR: No test sets found in {args.data_dir}", file=sys.stderr)
        sys.exit(1)
    print(f"Found {len(test_sets)} test sets in {args.data_dir}")

    all_results: list[dict] = []

    for level_idx in range(len(DEGRADATION_LEVELS_RAW)):
        v_noise, dropout, c_noise, _ = DEGRADATION_LEVELS_RAW[level_idx]
        level_label = LEVEL_LABELS[level_idx]
        print(f"\nLevel {level_idx} ({level_label}): noise={v_noise:.0%}, dropout={dropout:.0%}, conf_noise={c_noise:.0%}")

        for config_name in ROBUSTNESS_CONFIGS:
            print(f"  Running {config_name}...", end=" ", flush=True)
            try:
                result = _run_level(
                    level_idx=level_idx,
                    config_name=config_name,
                    test_sets=test_sets,
                    configs_dir=args.configs_dir,
                    output_dir=args.output_dir,
                    seed=args.seed,
                )
                dest = _save_result(result, args.output_dir)
                counts = result["counts"]
                print(
                    f"PASS={counts['PASS']} true_FAIL={counts['FAIL_true']} "
                    f"false_FAIL={counts['FAIL_false']} NA={counts['NOT_ASSESSABLE']} "
                    f"-> {dest.name}"
                )
                all_results.append(result)
            except Exception as exc:  # noqa: BLE001
                print(f"ERROR: {exc}", file=sys.stderr)
                _log.exception("Failed level %d / %s", level_idx, config_name)

    print(f"\nResults saved to {args.output_dir}")

    if args.figures:
        print("\nGenerating robustness figures...")
        try:
            generate_figures(all_results, args.figures_dir)
        except Exception as exc:  # noqa: BLE001
            print(f"Figure generation failed: {exc}", file=sys.stderr)
            _log.exception("Figure generation failed")


if __name__ == "__main__":
    main()
